"""
Argus Pipeline Orchestrator — the beating heart of the Argus system.

Wires together every subsystem (streaming, detection, tracking, recognition,
LLM analysis, recording, alerting, storage) into a single coherent pipeline.

Design principles:
  - All dependencies INJECTED — no global singletons, fully testable.
  - The event loop is NEVER blocked — all heavy work runs in executors.
  - Every unknown face triggers CONCURRENT Laya gate + LLM + recording
    via asyncio.gather.
  - Kafka is used for durable event publishing (argus.events) and upload
    queuing (argus.uploads).
  - Graceful degradation: any subsystem failure is logged and skipped;
    the pipeline never crashes.
  - Structured JSON logging at every decision point for full observability.

Kafka argus.events message schema:
  {
    "event_id":              int | null,
    "camera":                str,
    "face_hash":             str,
    "is_suspicious":         bool,
    "escalated_by_laya":     bool,
    "confidence":            float,
    "llm_description":       str,
    "action_recommendation": str,
    "clip_path":             str | null,
    "thumbnail_path":        str | null,
    "triggered_at":          str (ISO-8601 UTC),
  }
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import structlog

from argus.alerts.models import Alert, AlertKind, AlertSeverity
from argus.intelligence.base import SAFE_FALLBACK

if TYPE_CHECKING:
    from argus.alerts.manager import AlertManager
    from argus.config.settings import CameraConfig, Settings
    from argus.core.detector import Detection, DetectorWorker
    from argus.core.motion import MotionFilter
    from argus.core.recognizer import FaceMatch, FaceRecognizer
    from argus.core.recorder import EventRecorder
    from argus.core.stream import StreamWorker
    from argus.core.tracker import SortTracker
    from argus.intelligence.base import LLMProvider
    from argus.intelligence.laya import LayaDecisionGate
    from argus.intelligence.learner import AutoLearner
    from argus.kafka.producer import ArgusProducer
    from argus.storage.manager import StorageManager

logger = structlog.get_logger(__name__)

# Seconds after last detection before the clip recording is stopped
_POST_EVENT_SECONDS = 10


class EventOrchestrator:
    """
    Per-camera pipeline coordinator.

    One EventOrchestrator instance runs per configured camera.
    It owns the full processing chain for that camera's frame stream.

    Lifecycle:
        orch = EventOrchestrator(...)
        await orch.start()   # warm up DB record
        await orch.run()     # runs forever, consuming frames from stream queue
        await orch.stop()    # signal graceful exit
    """

    def __init__(
        self,
        camera: CameraConfig,
        stream_worker: StreamWorker,
        motion_filter: MotionFilter,
        detector: DetectorWorker,
        tracker: SortTracker,
        recognizer: FaceRecognizer,
        recorder: EventRecorder,
        alert_manager: AlertManager,
        learner: AutoLearner,
        llm_provider: LLMProvider,
        laya_gate: LayaDecisionGate | None,
        kafka_producer: ArgusProducer | None,
        storage_manager: StorageManager | None,
        session_factory,
        settings: Settings,
    ) -> None:
        self._camera = camera
        self._stream = stream_worker
        self._motion = motion_filter
        self._detector = detector
        self._tracker = tracker
        self._recognizer = recognizer
        self._recorder = recorder
        self._alert_manager = alert_manager
        self._learner = learner
        self._llm = llm_provider
        self._laya = laya_gate
        self._producer = kafka_producer
        self._storage = storage_manager
        self._session_factory = session_factory
        self._settings = settings

        # Runtime state
        self._running = False
        self._camera_db_id: int | None = None
        self._frame_count: int = 0
        self._event_count: int = 0
        self._recording_active: bool = False
        self._last_detection_ts: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Ensure camera DB record exists, mark orchestrator as running."""
        async with self._session_factory() as session:
            from argus.database import repository
            cam = await repository.get_or_create_camera(
                session,
                name=self._camera.name,
                rtsp_url=self._camera.rtsp_url,
            )
            await session.commit()
            self._camera_db_id = cam.id

        self._running = True
        logger.info(
            "EventOrchestrator started",
            camera=self._camera.name,
            camera_db_id=self._camera_db_id,
        )

    async def stop(self) -> None:
        """Signal the run loop to exit on next iteration."""
        self._running = False
        logger.info("EventOrchestrator stopping", camera=self._camera.name)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main frame-processing loop.

        Pulls frames from the StreamWorker queue and drives the full
        detection → tracking → recognition → analysis → alert pipeline.
        Runs until stop() is called.
        """
        log = logger.bind(camera=self._camera.name)
        log.info("Pipeline run loop started")

        while self._running:
            # Non-blocking queue poll — avoids blocking forever on empty queue
            try:
                frame: np.ndarray = await asyncio.wait_for(
                    self._stream.queue.get(), timeout=1.0
                )
            except TimeoutError:
                # No frame available — check if recording should auto-stop
                await self._check_recording_timeout()
                continue

            self._frame_count += 1

            # ── Stage 1: Motion pre-filter (cheap CPU, eliminates ~90% of frames) ──
            has_motion = await self._motion.has_motion_async(frame)
            if not has_motion:
                await self._check_recording_timeout()
                continue

            # ── Stage 2: Object detection (YOLO on GPU/CPU) ──────────────────────
            detections = await self._safe_detect(frame)
            persons = [d for d in detections if d.class_name == "person"]
            if not persons:
                await self._check_recording_timeout()
                continue

            log.debug("Persons detected", count=len(persons), frame=self._frame_count)

            # ── Stage 3: SORT tracking (persistent track IDs) ────────────────────
            tracked = await self._safe_track(persons)

            # ── Stage 4: Face recognition (InsightFace + FAISS) ──────────────────
            face_matches = await self._safe_recognize(frame, tracked)

            # ── Stage 5: Buffer frame for pre-event clip ──────────────────────────
            self._last_detection_ts = time.monotonic()

            # ── Stage 6: Process each face match ─────────────────────────────────
            for match in face_matches:
                if match.is_known:
                    await self._handle_known_face(match)
                else:
                    # Unknown face — trigger full event pipeline
                    await self._handle_unknown_face(frame, match)

            # If persons detected but no face match, still start recording
            if persons and not face_matches and not self._recording_active:
                with contextlib.suppress(Exception):
                    await self._recorder.start_recording([frame])
                    self._recording_active = True

        log.info(
            "Pipeline run loop exited",
            frames_processed=self._frame_count,
            events_triggered=self._event_count,
        )

    # ------------------------------------------------------------------
    # Pipeline stages — error-safe wrappers
    # ------------------------------------------------------------------

    async def _safe_detect(self, frame: np.ndarray) -> list[Detection]:
        try:
            return await self._detector.detect(frame)
        except Exception as exc:
            logger.warning("Detection error", camera=self._camera.name, error=str(exc))
            return []

    async def _safe_track(self, detections: list[Detection]) -> list[Detection]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._tracker.update, detections)
        except Exception as exc:
            logger.warning("Tracker error", camera=self._camera.name, error=str(exc))
            return detections  # fail-open: return untracked detections

    async def _safe_recognize(
        self, frame: np.ndarray, detections: list[Detection]
    ) -> list[FaceMatch]:
        try:
            return await self._recognizer.recognize(frame, detections)
        except Exception as exc:
            logger.warning("Recognition error", camera=self._camera.name, error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Known face handler
    # ------------------------------------------------------------------

    async def _handle_known_face(self, match: FaceMatch) -> None:
        """Update last_seen for a recognised person — no alert needed."""
        if match.profile_id is None:
            return
        with contextlib.suppress(Exception):
            async with self._session_factory() as session:
                from argus.database import repository
                await repository.update_face_last_seen(
                    session, profile_id=match.profile_id
                )
                await session.commit()
            logger.debug(
                "Known person updated",
                camera=self._camera.name,
                profile_id=match.profile_id,
                similarity=round(match.similarity, 3),
            )

    # ------------------------------------------------------------------
    # Unknown face handler — the full event pipeline
    # ------------------------------------------------------------------

    async def _handle_unknown_face(
        self, frame: np.ndarray, match: FaceMatch
    ) -> None:
        """
        Full event pipeline for an unknown face:
          1.  Save face thumbnail
          2a. Laya 421M fast gate (async, ~33ms)
          2b. Full LLM vision analysis (concurrent with Laya)
          2c. Start/continue clip recording (concurrent)
          3.  Persist Event + Clip to database
          4.  Publish to argus.events Kafka topic
          5.  Build and dispatch Alert via AlertManager
          6.  AutoLearner face tracking
          7.  Enqueue clip for cloud upload (argus.uploads)
        """
        self._event_count += 1
        log = logger.bind(
            camera=self._camera.name,
            event_num=self._event_count,
        )
        log.info("Unknown face detected", similarity=round(match.similarity, 3))

        # ── 1. Save thumbnail ──────────────────────────────────────────────
        thumbnail_path = await self._save_thumbnail(frame)

        # ── 2. Run Laya gate + LLM analysis + clip recording concurrently ─
        laya_task = asyncio.create_task(
            self._run_laya(match), name=f"laya-{self._camera.name}"
        )
        llm_task = asyncio.create_task(
            self._run_llm(frame, match), name=f"llm-{self._camera.name}"
        )
        record_task = asyncio.create_task(
            self._ensure_recording(frame), name=f"record-{self._camera.name}"
        )

        laya_decision = await laya_task  # fast — don't block the gather

        (llm_result, clip_path) = await asyncio.gather(
            llm_task, record_task, return_exceptions=True
        )

        # Safely unwrap — any exception → fallback
        if isinstance(llm_result, Exception):
            log.warning("LLM analysis failed", error=str(llm_result))
            llm_result = SAFE_FALLBACK

        if isinstance(clip_path, Exception):
            log.warning("Recording failed", error=str(clip_path))
            clip_path = None

        escalated = laya_decision is not None and laya_decision.escalate_to_llm
        is_suspicious = llm_result.is_suspicious or escalated

        # ── 3. Persist to DB ───────────────────────────────────────────────
        event_id = await self._persist_event(
            match=match,
            llm_result=llm_result,
            thumbnail_path=thumbnail_path,
            clip_path=str(clip_path) if clip_path else None,
            is_suspicious=is_suspicious,
        )

        # ── 4. Publish to Kafka argus.events ───────────────────────────────
        await self._publish_to_kafka(
            event_id=event_id,
            match=match,
            llm_result=llm_result,
            clip_path=str(clip_path) if clip_path else None,
            thumbnail_path=thumbnail_path,
            is_suspicious=is_suspicious,
            escalated_by_laya=escalated,
        )

        # ── 5. Dispatch Alert ──────────────────────────────────────────────
        await self._dispatch_alert(
            match=match,
            llm_result=llm_result,
            thumbnail_path=thumbnail_path,
            is_suspicious=is_suspicious,
        )

        # ── 6. AutoLearner ─────────────────────────────────────────────────
        with contextlib.suppress(Exception):
            await self._learner.track_unknown(
                face_match=match,
                camera_name=self._camera.name,
                frame=frame,
            )

        # ── 7. Cloud upload via Kafka argus.uploads ────────────────────────
        if clip_path and self._storage and event_id:
            with contextlib.suppress(Exception):
                await self._storage.enqueue(
                    local_path=clip_path,
                    event_id=event_id,
                    camera_name=self._camera.name,
                )

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    async def _run_laya(self, match: FaceMatch):
        """Run fast Laya 421M gate. Returns LayaDecision or None on failure."""
        if self._laya is None:
            return None
        try:
            return await self._laya.decide(
                description=f"Unknown person detected on camera {self._camera.name}",
                camera_name=self._camera.name,
                face_is_known=False,
                similarity_score=match.similarity,
                detection_confidence=0.9,
            )
        except Exception as exc:
            logger.warning("Laya gate error", camera=self._camera.name, error=str(exc))
            return None

    async def _run_llm(self, frame: np.ndarray, match: FaceMatch):
        """Run the full LLM vision analysis."""
        try:
            context = (
                f"Camera: {self._camera.name}. "
                f"Unknown person. "
                f"Nearest face similarity: {match.similarity:.1%}. "
                f"Time: {datetime.now(UTC).strftime('%H:%M UTC')}."
            )
            return await self._llm.analyze(frame, context=context)
        except Exception as exc:
            logger.warning("LLM error", camera=self._camera.name, error=str(exc))
            return SAFE_FALLBACK

    async def _ensure_recording(self, frame: np.ndarray) -> Path | None:
        """Start recording if not already active. Returns output_path."""
        try:
            if not self._recording_active:
                await self._recorder.start_recording([frame])
                self._recording_active = True
                logger.info("Recording started", camera=self._camera.name)
            return self._recorder.current_output_path
        except Exception as exc:
            logger.warning("Recording error", camera=self._camera.name, error=str(exc))
            return None

    async def _check_recording_timeout(self) -> None:
        """Stop active recording if no person detected for POST_EVENT_SECONDS."""
        if not self._recording_active:
            return
        if time.monotonic() - self._last_detection_ts > _POST_EVENT_SECONDS:
            with contextlib.suppress(Exception):
                await self._recorder.stop_recording()
            self._recording_active = False
            logger.info("Recording stopped (post-event timeout)", camera=self._camera.name)

    async def _save_thumbnail(self, frame: np.ndarray) -> str | None:
        """Save a JPEG thumbnail of the current frame."""
        try:
            import cv2
            thumb_dir = Path(self._settings.thumbnails_path)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
            thumb_path = thumb_dir / f"{self._camera.name}_{ts}.jpg"
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: cv2.imwrite(str(thumb_path), frame)
            )
            return str(thumb_path)
        except Exception as exc:
            logger.warning("Thumbnail save failed", camera=self._camera.name, error=str(exc))
            return None

    async def _persist_event(
        self,
        match: FaceMatch,
        llm_result,
        thumbnail_path: str | None,
        clip_path: str | None,
        is_suspicious: bool,
    ) -> int | None:
        """Write Event + Clip records to the database. Returns event_id."""
        try:
            async with self._session_factory() as session:
                from argus.database import repository

                event = await repository.create_event(
                    session,
                    camera_id=self._camera_db_id,
                    face_profile_id=None,
                    thumbnail_path=thumbnail_path,
                    similarity_score=match.similarity,
                )
                await repository.update_event_with_analysis(
                    session,
                    event_id=event.id,
                    llm_analysis=llm_result.description,
                    is_suspicious=is_suspicious,
                    alert_sent=True,
                )
                if clip_path:
                    clip_file = Path(clip_path)
                    await repository.create_clip(
                        session,
                        event_id=event.id,
                        local_path=clip_path,
                        duration_seconds=0.0,
                        file_size_bytes=clip_file.stat().st_size if clip_file.exists() else 0,
                    )
                await session.commit()
                logger.info(
                    "Event persisted",
                    event_id=event.id,
                    camera=self._camera.name,
                    is_suspicious=is_suspicious,
                )
                return event.id
        except Exception as exc:
            logger.error(
                "Failed to persist event",
                camera=self._camera.name,
                error=str(exc),
            )
            return None

    async def _publish_to_kafka(
        self,
        event_id: int | None,
        match: FaceMatch,
        llm_result,
        clip_path: str | None,
        thumbnail_path: str | None,
        is_suspicious: bool,
        escalated_by_laya: bool,
    ) -> None:
        """Publish event to argus.events Kafka topic."""
        if not self._producer or not self._producer.is_started:
            return
        with contextlib.suppress(Exception):
            from argus.kafka.topics import ArgusTopics

            embedding = match.embedding
            face_hash = ""
            if embedding is not None:
                from argus.intelligence.learner import compute_face_hash
                face_hash = compute_face_hash(np.asarray(embedding, dtype=np.float32))

            await self._producer.publish(
                topic=ArgusTopics.EVENTS,
                key=str(event_id or self._camera.name),
                value={
                    "event_id": event_id,
                    "camera": self._camera.name,
                    "face_hash": face_hash,
                    "is_suspicious": is_suspicious,
                    "escalated_by_laya": escalated_by_laya,
                    "confidence": llm_result.confidence,
                    "llm_description": llm_result.description,
                    "action_recommendation": llm_result.action_recommendation,
                    "clip_path": clip_path,
                    "thumbnail_path": thumbnail_path,
                    "triggered_at": datetime.now(UTC).isoformat(),
                },
            )

    async def _dispatch_alert(
        self,
        match: FaceMatch,
        llm_result,
        thumbnail_path: str | None,
        is_suspicious: bool,
    ) -> None:
        """Build and enqueue an Alert to the AlertManager."""
        try:
            severity = (
                AlertSeverity.CRITICAL if is_suspicious else AlertSeverity.WARNING
            )
            thumb_bytes: bytes | None = None
            if thumbnail_path:
                p = Path(thumbnail_path)
                if p.exists():
                    loop = asyncio.get_running_loop()
                    thumb_bytes = await loop.run_in_executor(None, p.read_bytes)

            alert = Alert(
                kind=AlertKind.UNKNOWN_FACE,
                severity=severity,
                title=(
                    "🚨 Suspicious Activity Detected"
                    if is_suspicious
                    else "⚠️ Unknown Person Detected"
                ),
                body=llm_result.description,
                camera_name=self._camera.name,
                thumbnail=thumb_bytes,
                metadata={
                    "similarity": round(match.similarity, 3),
                    "action": llm_result.action_recommendation,
                    "confidence": round(llm_result.confidence, 3),
                },
            )
            await self._alert_manager.send(alert)
            logger.info(
                "Alert dispatched",
                camera=self._camera.name,
                severity=severity.value,
            )
        except Exception as exc:
            logger.warning(
                "Alert dispatch failed",
                camera=self._camera.name,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Health / observability
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Runtime statistics for health monitoring."""
        return {
            "camera": self._camera.name,
            "frames_processed": self._frame_count,
            "events_triggered": self._event_count,
            "recording_active": self._recording_active,
            "running": self._running,
        }
