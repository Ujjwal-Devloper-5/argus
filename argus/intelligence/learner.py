"""
Argus AutoLearner — Makes Argus smarter over time by learning unknown faces.

Every time an UNKNOWN face is detected:
1. Computes a stable hash from the embedding (absorbs float noise)
2. Tracks appearance count in DB via UnknownFaceTracker
3. Scores face crop quality (sharpness via Laplacian variance)
4. Saves the best quality crop seen for this face
5. At threshold: sends Telegram prompt "Remember this person?"
6. Temporal pattern analysis: flags suspicious timing (3am repeat visitors)
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


def compute_face_hash(embedding: np.ndarray, precision: int = 2) -> str:
    """
    Compute a stable hash from a face embedding.
    Rounds to `precision` decimal places to absorb float noise so the
    same physical face always maps to the same hash across frames.
    """
    rounded = np.round(np.asarray(embedding, dtype=np.float32), decimals=precision)
    return hashlib.sha256(rounded.tobytes()).hexdigest()[:16]


def score_face_quality(face_img: np.ndarray) -> float:
    """
    Score image sharpness using Laplacian variance.
    Higher = sharper. Returns 0.0-1.0 (normalized, capped at 1.0).
    """
    if face_img is None or face_img.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY) if face_img.ndim == 3 else face_img
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return min(1.0, variance / 500.0)


class AutoLearner:
    """
    Tracks unknown faces and learns who belongs in the monitored area.

    All dependencies are injected — no global singletons.
    """

    def __init__(
        self,
        session_factory,     # async context manager yielding AsyncSession
        alert_manager,       # AlertManager (used to send Telegram prompts)
        settings,            # Settings instance
        embedding_db=None,   # Optional: EmbeddingDB for live face enrollment
    ) -> None:
        self._session_factory = session_factory
        self._alert_manager = alert_manager
        self._settings = settings
        self._embedding_db = embedding_db
        # In-memory cache: face_hash -> (best_quality_score, best_face_img)
        self._quality_cache: dict[str, tuple[float, np.ndarray]] = {}
        self._lock = asyncio.Lock()

    async def track_unknown(
        self,
        face_match,          # FaceMatch from recognizer (is_known must be False)
        camera_name: str,
        frame: np.ndarray | None = None,
    ) -> None:
        """
        Main entry point. Call this every time an unknown face is detected.
        Never raises — all errors are logged and swallowed.
        """
        if face_match.is_known:
            return

        embedding = np.asarray(face_match.embedding, dtype=np.float32)
        face_hash = compute_face_hash(embedding)

        # Decode face crop and score its quality
        face_img = self._decode_face_crop(face_match.face_crop, frame)
        quality = score_face_quality(face_img) if face_img is not None else 0.0

        # Update best quality cache
        async with self._lock:
            prev_quality, _ = self._quality_cache.get(face_hash, (0.0, None))
            if quality > prev_quality and face_img is not None:
                self._quality_cache[face_hash] = (quality, face_img.copy())

        cfg = self._settings.recognition.auto_learn
        if not cfg.enabled:
            return

        try:
            async with self._session_factory() as session:
                from argus.database import repository

                tracker = await repository.get_or_create_unknown_tracker(session, face_hash)

                # Skip if already prompted or user chose to ignore
                if tracker.prompted_user or getattr(tracker, "is_ignored", False):
                    await session.commit()
                    return

                logger.debug(
                    "Unknown face tracked",
                    face_hash=face_hash,
                    count=tracker.appearance_count,
                    threshold=cfg.appearances_before_prompt,
                    camera=camera_name,
                    quality=round(quality, 3),
                )

                if tracker.appearance_count >= cfg.appearances_before_prompt:
                    thumbnail_path = await self._save_best_thumbnail(face_hash)
                    await repository.mark_tracker_prompted(session, tracker.id, thumbnail_path)
                    pattern_note = self._analyze_temporal_pattern(tracker)
                    await self._send_learn_prompt(
                        face_hash=face_hash,
                        appearance_count=tracker.appearance_count,
                        camera_name=camera_name,
                        thumbnail_path=thumbnail_path,
                        pattern_note=pattern_note,
                        similarity=face_match.similarity,
                    )
                    logger.info(
                        "Auto-learn prompt sent",
                        face_hash=face_hash,
                        appearances=tracker.appearance_count,
                        camera=camera_name,
                        pattern=pattern_note,
                    )

                await session.commit()

        except Exception as exc:
            logger.warning("AutoLearner.track_unknown error", error=str(exc), face_hash=face_hash)

    def _decode_face_crop(self, face_crop_bytes: bytes | None, fallback_frame: np.ndarray | None) -> np.ndarray | None:
        """Decode JPEG face crop bytes to numpy array, falling back to full frame."""
        if face_crop_bytes:
            arr = np.frombuffer(face_crop_bytes, dtype=np.uint8)
            if arr.size > 0:
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return img
        return fallback_frame

    async def _save_best_thumbnail(self, face_hash: str) -> str:
        """Write the best quality face crop for this hash to disk."""
        out_dir = Path("data/unknown_faces")
        out_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = out_dir / f"{face_hash}_sample.jpg"

        async with self._lock:
            entry = self._quality_cache.get(face_hash)

        if entry is not None:
            _, best_img = entry
            cv2.imwrite(str(thumb_path), best_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            placeholder = np.zeros((100, 100, 3), dtype=np.uint8)
            cv2.imwrite(str(thumb_path), placeholder)

        return str(thumb_path)

    def _analyze_temporal_pattern(self, tracker) -> str:
        """Return a human-readable note about suspicious timing patterns."""
        try:
            first: datetime = tracker.first_seen
            last: datetime = tracker.last_seen
            count: int = tracker.appearance_count
            days_active = max(1, (last - first).days + 1)
            freq = count / days_active
            notes = []
            if first.hour >= 22 or first.hour <= 5:
                notes.append("⚠️ First appeared late at night")
            if freq > 3:
                notes.append(f"⚠️ High frequency: ~{freq:.1f}x/day")
            if days_active > 3:
                notes.append(f"📅 Recurring over {days_active} days")
            return " | ".join(notes) if notes else "Normal activity pattern"
        except Exception:
            return ""

    async def _send_learn_prompt(
        self,
        face_hash: str,
        appearance_count: int,
        camera_name: str,
        thumbnail_path: str,
        pattern_note: str,
        similarity: float,
    ) -> None:
        """Dispatch the auto-learn prompt via AlertManager."""
        try:
            if hasattr(self._alert_manager, "send_learn_prompt"):
                await self._alert_manager.send_learn_prompt(
                    face_hash=face_hash,
                    appearance_count=appearance_count,
                    camera_name=camera_name,
                    thumbnail_path=thumbnail_path,
                    pattern_note=pattern_note,
                    similarity=similarity,
                )
            else:
                logger.info(
                    "AUTO-LEARN threshold reached",
                    face_hash=face_hash,
                    appearances=appearance_count,
                    camera=camera_name,
                    pattern=pattern_note,
                    thumbnail=thumbnail_path,
                )
        except Exception as exc:
            logger.warning("Failed to send auto-learn prompt", error=str(exc))
