"""
Face Recognition Engine for Argus using InsightFace and FAISS.

Extracts facial embeddings from detected objects and searches an EmbeddingDB
for identity matching, executing off-thread via asyncio.run_in_executor to avoid
blocking the event loop.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any

import numpy as np
import structlog
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from argus.config.settings import RecognitionConfig, Settings
from argus.core.detector import Detection
from argus.intelligence.embeddings import EmbeddingDB

logger = structlog.get_logger(__name__)

try:
    import insightface
    from insightface.app import FaceAnalysis
except ImportError:
    insightface = None  # type: ignore[assignment]
    FaceAnalysis = None  # type: ignore[assignment,misc]

try:
    import onnxruntime as ort
except ImportError:
    ort = None  # type: ignore[assignment]


def resolve_providers(requested_providers: Sequence[str] | None = None) -> list[str]:
    """
    Resolve execution providers, safely failing over to CPU if CUDA is unavailable.

    Args:
        requested_providers: Optional prioritized list of provider names.

    Returns:
        List of verified available ONNX execution providers.
    """
    available_providers: list[str] = []
    if ort is not None and hasattr(ort, "get_available_providers"):
        try:
            available_providers = ort.get_available_providers()
        except Exception as exc:
            logger.warning("Failed to query ONNX available providers", error=str(exc))

    if not available_providers:
        available_providers = ["CPUExecutionProvider"]

    default_priority = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    targets = list(requested_providers) if requested_providers is not None else default_priority

    resolved = [p for p in targets if p in available_providers]
    if not resolved:
        logger.info(
            "Requested ONNX providers unavailable, falling back to CPU",
            requested=targets,
            available=available_providers,
        )
        resolved = ["CPUExecutionProvider"]
    elif "CUDAExecutionProvider" in targets and "CUDAExecutionProvider" not in resolved:
        logger.info(
            "CUDA provider unavailable, failing over to CPUExecutionProvider",
            available=available_providers,
        )

    return resolved


class FaceMatch(BaseModel):
    """
    Result of face recognition on a detected person/object.

    Attributes:
        detection: Original YOLO Detection object.
        embedding: 512-dim float32 embedding vector if a face was detected, else None.
        similarity: Cosine similarity score [0.0, 1.0] against closest enrolled face profile.
        is_known: True if similarity > similarity_threshold and profile_id is not None.
        profile_id: Database ID of the matched face profile, or None.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    detection: Detection
    embedding: np.ndarray | None = Field(default=None)
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    is_known: bool = Field(default=False)
    profile_id: int | None = Field(default=None)

    @field_validator("embedding", mode="before")
    @classmethod
    def _validate_embedding(cls, v: Any) -> np.ndarray | None:
        """Validate and convert embedding to 1D float32 numpy array."""
        if v is None:
            return None
        if isinstance(v, (np.ndarray, list, tuple)):
            arr = np.asarray(v, dtype=np.float32).flatten()
            if not np.all(np.isfinite(arr)):
                raise ValueError("embedding cannot contain NaN or Inf values")
            if arr.size != 512:
                raise ValueError(f"embedding must have dimension 512, got {arr.size}")
            # Normalize -0.0 to 0.0 for consistent byte-level hashing
            return np.where(arr == 0.0, 0.0, arr).astype(np.float32)
        raise ValueError(f"embedding must be a numpy array or sequence, got {type(v).__name__}")

    @field_serializer("embedding", when_used="json")
    def _serialize_embedding(self, v: np.ndarray | None) -> list[float] | None:
        """Serialize numpy array embedding to list of floats for JSON export."""
        if v is None:
            return None
        return v.tolist()

    @model_validator(mode="after")
    def _validate_known_consistency(self) -> FaceMatch:
        """Validate logical consistency between is_known, profile_id, and embedding."""
        if self.is_known and self.profile_id is None:
            raise ValueError("is_known cannot be True when profile_id is None")
        if self.is_known and self.embedding is None:
            raise ValueError("is_known cannot be True when embedding is None")
        return self

    def __eq__(self, other: object) -> bool:
        """Safe equality comparison handling numpy array embeddings."""
        if not isinstance(other, FaceMatch):
            return False
        if self.detection != other.detection:
            return False
        if (
            self.similarity != other.similarity
            or self.is_known != other.is_known
            or self.profile_id != other.profile_id
        ):
            return False
        if (self.embedding is None) != (other.embedding is None):
            return False
        if self.embedding is not None and other.embedding is not None:
            return bool(np.array_equal(self.embedding, other.embedding))
        return True

    def __hash__(self) -> int:
        """Safe hash calculation handling numpy array embeddings."""
        emb_bytes = self.embedding.tobytes() if self.embedding is not None else None
        return hash(
            (
                self.detection,
                emb_bytes,
                self.similarity,
                self.is_known,
                self.profile_id,
            )
        )


class FaceRecognizer:
    """
    Face recognizer wrapping insightface.app.FaceAnalysis.

    Crops faces from detected bounding boxes, extracts ArcFace 512-dim embeddings,
    and searches the provided EmbeddingDB for matching face profiles.
    """

    def __init__(
        self,
        db: EmbeddingDB | None = None,
        similarity_threshold: float = 0.60,
        app: Any | None = None,
        providers: Sequence[str] | None = None,
        executor: Executor | None = None,
        ctx_id: int = 0,
        det_thresh: float = 0.5,
        det_size: tuple[int, int] = (640, 640),
        model_name: str = "buffalo_l",
    ) -> None:
        """
        Initialize the FaceRecognizer.

        Args:
            db: Optional EmbeddingDB instance for vector similarity search.
            similarity_threshold: Cosine similarity threshold for identifying known faces.
            app: Optional pre-configured FaceAnalysis instance or mock.
            providers: Execution providers (e.g. ['CUDAExecutionProvider', 'CPUExecutionProvider']).
            executor: Optional Executor for running inference off-thread.
            ctx_id: GPU device ID (>=0) or CPU device (-1).
            det_thresh: Face detection threshold for InsightFace.
            det_size: Input image resolution (width, height) for face detection.
            model_name: InsightFace model pack name (default 'buffalo_l').
        """
        if isinstance(similarity_threshold, bool) or not (0.0 <= similarity_threshold <= 1.0):
            raise ValueError(
                f"similarity_threshold must be between 0.0 and 1.0, got {similarity_threshold}"
            )

        self.db = db
        self.similarity_threshold = float(similarity_threshold)
        self.providers = resolve_providers(providers)

        if app is not None:
            self.app = app
        else:
            if FaceAnalysis is None:
                raise ImportError(
                    "insightface is required for FaceRecognizer. "
                    "Please install insightface with `pip install insightface`."
                )
            logger.info(
                "Initializing FaceAnalysis",
                model=model_name,
                providers=self.providers,
            )
            self.app = FaceAnalysis(name=model_name, providers=self.providers)
            self.app.prepare(ctx_id=ctx_id, det_thresh=det_thresh, det_size=det_size)

        self._custom_executor = executor is not None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="recognizer",
        )
        self._closed = False

    @classmethod
    def from_config(
        cls,
        config: RecognitionConfig | Settings | dict[str, Any],
        db: EmbeddingDB | None = None,
        **kwargs: Any,
    ) -> FaceRecognizer:
        """
        Create a FaceRecognizer instance configured from a RecognitionConfig, Settings, or dict.
        """
        if isinstance(config, Settings):
            config = config.recognition
        elif isinstance(config, dict):
            config = RecognitionConfig(**config)

        if not isinstance(config, RecognitionConfig):
            raise TypeError(f"config must be a RecognitionConfig, got {type(config).__name__}")
        kwargs.setdefault("similarity_threshold", config.similarity_threshold)
        return cls(db=db, **kwargs)

    def _extract_embedding_from_crop(self, crop: np.ndarray) -> np.ndarray | None:
        """
        Run InsightFace on a cropped image and extract the primary face embedding.

        Handles InsightFace Face objects, direct numpy arrays, and mock outputs.
        Ensures contiguous memory layout, uint8 channel formatting, and finite values.
        """
        if crop is None or crop.size == 0:
            return None

        # Normalize channel layout for InsightFace (expects 3-channel BGR)
        if crop.ndim == 2:
            crop = np.stack([crop, crop, crop], axis=-1)
        elif crop.ndim == 3 and crop.shape[2] == 1:
            crop = np.repeat(crop, 3, axis=-1)
        elif crop.ndim == 3 and crop.shape[2] == 4:
            crop = crop[:, :, :3]
        elif crop.ndim != 3 or crop.shape[2] != 3:
            return None

        # Normalize dtype to uint8 for InsightFace / OpenCV
        if crop.dtype != np.uint8:
            if np.issubdtype(crop.dtype, np.floating):
                max_val = float(np.nanmax(crop)) if crop.size > 0 else 1.0
                min_val = float(np.nanmin(crop)) if crop.size > 0 else 0.0
                if min_val >= 0.0 and max_val <= 1.0:
                    crop = np.clip(crop * 255.0, 0, 255).astype(np.uint8)
                else:
                    crop = np.clip(crop, 0, 255).astype(np.uint8)
            elif np.issubdtype(crop.dtype, np.integer):
                crop = np.clip(crop, 0, 255).astype(np.uint8)
            elif crop.dtype == bool:
                crop = crop.astype(np.uint8) * 255
            else:
                return None

        # Ensure contiguous memory layout for C++/ONNX bindings AFTER channel and dtype normalization
        crop = np.ascontiguousarray(crop)

        try:
            raw_output = self.app.get(crop)
        except Exception as exc:
            logger.warning("Error during InsightFace feature extraction", error=str(exc))
            return None

        if raw_output is None:
            return None

        # Direct numpy array returned (e.g. from a simplified mock)
        if isinstance(raw_output, np.ndarray):
            if raw_output.size == 512 and np.all(np.isfinite(raw_output)):
                return np.asarray(raw_output, dtype=np.float32).flatten()
            return None

        # Sequence of faces / objects
        if isinstance(raw_output, (list, tuple)):
            if len(raw_output) == 0:
                return None

            # Helper to extract bounding box area
            def _get_bbox_area(bbox: Any) -> float:
                if bbox is not None and len(bbox) >= 4:
                    try:
                        b0, b1, b2, b3 = (
                            float(bbox[0]),
                            float(bbox[1]),
                            float(bbox[2]),
                            float(bbox[3]),
                        )
                        if (
                            math.isfinite(b0)
                            and math.isfinite(b1)
                            and math.isfinite(b2)
                            and math.isfinite(b3)
                        ):
                            return max(0.0, b2 - b0) * max(0.0, b3 - b1)
                    except (TypeError, ValueError):
                        return 0.0
                return 0.0

            def _is_valid_512_dim(e: Any) -> bool:
                if e is None:
                    return False
                try:
                    arr = np.asarray(e, dtype=np.float32)
                    return bool(arr.size == 512 and np.all(np.isfinite(arr)))
                except Exception:
                    return False

            # 1. Candidate list of numpy arrays
            array_candidates = [
                arr
                for arr in raw_output
                if isinstance(arr, np.ndarray) and arr.size == 512 and np.all(np.isfinite(arr))
            ]
            if array_candidates:
                return np.asarray(array_candidates[0], dtype=np.float32).flatten()

            # 2. Candidate list of Face objects (hasattr embedding or normed_embedding)
            face_candidates: list[tuple[float, Any]] = []
            for item in raw_output:
                emb = getattr(item, "embedding", None)
                if emb is None:
                    emb = getattr(item, "normed_embedding", None)
                if _is_valid_512_dim(emb):
                    bbox = getattr(item, "bbox", None)
                    area = _get_bbox_area(bbox)
                    face_candidates.append((area, emb))

            if face_candidates:
                face_candidates.sort(key=lambda x: x[0], reverse=True)
                return np.asarray(face_candidates[0][1], dtype=np.float32).flatten()

            # 3. Candidate list of dicts with 'embedding' or 'normed_embedding' key
            dict_candidates: list[tuple[float, Any]] = []
            for item in raw_output:
                if isinstance(item, dict):
                    emb = item.get("embedding")
                    if emb is None:
                        emb = item.get("normed_embedding")
                    if _is_valid_512_dim(emb):
                        area = _get_bbox_area(item.get("bbox"))
                        dict_candidates.append((area, emb))

            if dict_candidates:
                dict_candidates.sort(key=lambda x: x[0], reverse=True)
                return np.asarray(dict_candidates[0][1], dtype=np.float32).flatten()

        return None

    def _process_frame_sync(
        self,
        frame: np.ndarray,
        detections: list[Detection],
    ) -> list[FaceMatch]:
        """
        Synchronous processing loop executed within the thread pool executor.
        """
        h, w = frame.shape[:2]
        matches: list[FaceMatch] = []

        for det in detections:
            # Clip bounding box coordinates to frame boundaries
            x1 = max(0, min(det.x1, w))
            y1 = max(0, min(det.y1, h))
            x2 = max(0, min(det.x2, w))
            y2 = max(0, min(det.y2, h))

            if x2 <= x1 or y2 <= y1:
                matches.append(
                    FaceMatch(
                        detection=det,
                        embedding=None,
                        similarity=0.0,
                        is_known=False,
                        profile_id=None,
                    )
                )
                continue

            crop = frame[y1:y2, x1:x2]
            embedding = self._extract_embedding_from_crop(crop)

            if embedding is None:
                matches.append(
                    FaceMatch(
                        detection=det,
                        embedding=None,
                        similarity=0.0,
                        is_known=False,
                        profile_id=None,
                    )
                )
                continue

            # Query the embedding database
            if self.db is not None:
                matched_id, similarity = self.db.find_closest(embedding)
            else:
                matched_id, similarity = None, 0.0

            # True if similarity meets or exceeds configurable threshold and profile exists
            is_known = bool(matched_id is not None and similarity >= self.similarity_threshold)
            profile_id = matched_id if is_known else None

            matches.append(
                FaceMatch(
                    detection=det,
                    embedding=embedding,
                    similarity=similarity,
                    is_known=is_known,
                    profile_id=profile_id,
                )
            )

        return matches

    async def recognize(
        self,
        frame: np.ndarray,
        detections: list[Detection],
    ) -> list[FaceMatch]:
        """
        Recognize faces in the given frame for the provided detections.

        Runs blocking InsightFace extraction in a thread pool executor.

        Args:
            frame: Input video frame as a numpy array (H, W, C).
            detections: List of Detection objects from the object detector.

        Returns:
            List of FaceMatch objects corresponding to the input detections.
        """
        if self._closed:
            raise RuntimeError("FaceRecognizer is closed")

        if (
            frame is None
            or frame.size == 0
            or frame.ndim not in (2, 3)
            or not np.issubdtype(frame.dtype, np.number)
            or not detections
        ):
            return []

        loop = asyncio.get_running_loop()
        matches = await loop.run_in_executor(
            self._executor,
            self._process_frame_sync,
            frame,
            detections,
        )
        return matches

    def close(self) -> None:
        """Release executor resources."""
        if not self._closed:
            self._closed = True
            if not self._custom_executor and isinstance(self._executor, ThreadPoolExecutor):
                self._executor.shutdown(wait=False, cancel_futures=True)
            logger.info("FaceRecognizer closed")

    async def stop(self) -> None:
        """Asynchronously stop recognizer and release executor resources."""
        self.close()

    def __enter__(self) -> FaceRecognizer:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> FaceRecognizer:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
