"""
Object Detection Engine for Argus using ultralytics YOLOv8.

Implements the DetectorWorker class which wraps YOLOv8 inference,
running blocking calls asynchronously inside an executor thread to ensure the
asyncio event loop remains responsive.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from collections.abc import Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from argus.config.settings import DetectionConfig

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[assignment,misc]

logger = structlog.get_logger(__name__)


class Detection(BaseModel):
    """
    Object detection result.

    Attributes:
        box: Bounding box coordinates (x1, y1, x2, y2) as integers.
        confidence: Prediction confidence score in range [0.0, 1.0].
        class_name: Human-readable class name (e.g. 'person').
    """

    model_config = ConfigDict(frozen=True)

    box: tuple[int, int, int, int]
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_name: str = Field(default="person", min_length=1)
    track_id: int | None = Field(
        default=None, description="Tracking ID assigned by object tracker"
    )

    @property
    def x1(self) -> int:
        """Top-left x coordinate."""
        return self.box[0]

    @property
    def y1(self) -> int:
        """Top-left y coordinate."""
        return self.box[1]

    @property
    def x2(self) -> int:
        """Bottom-right x coordinate."""
        return self.box[2]

    @property
    def y2(self) -> int:
        """Bottom-right y coordinate."""
        return self.box[3]

    @property
    def width(self) -> int:
        """Bounding box width."""
        return max(0, self.box[2] - self.box[0])

    @property
    def height(self) -> int:
        """Bounding box height."""
        return max(0, self.box[3] - self.box[1])

    @property
    def area(self) -> int:
        """Bounding box pixel area."""
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        """Center coordinate (center_x, center_y) of bounding box."""
        return (self.box[0] + self.box[2]) // 2, (self.box[1] + self.box[3]) // 2

    @field_validator("box", mode="before")
    @classmethod
    def _validate_box(cls, v: Any) -> tuple[int, int, int, int]:
        """Validate and convert bounding box coordinates to a 4-tuple of ints."""
        # Convert PyTorch tensors or any object with .tolist()
        if hasattr(v, "tolist") and callable(v.tolist):
            v = v.tolist()

        # Unwrap 2D single-box representations (e.g. [[x1, y1, x2, y2]])
        if (
            isinstance(v, (list, tuple))
            and len(v) == 1
            and isinstance(v[0], (Sequence, np.ndarray))
            and not isinstance(v[0], (str, bytes))
        ):
            v = v[0]

        if isinstance(v, (str, bytes)) or not isinstance(v, (Sequence, np.ndarray)):
            raise ValueError(f"box must be a sequence of 4 ints, got {type(v).__name__}")
        if len(v) != 4:
            raise ValueError(
                f"box must have exactly 4 coordinates (x1, y1, x2, y2), got length {len(v)}"
            )

        coords: list[int] = []
        for i, c in enumerate(v):
            if isinstance(c, bool):
                raise ValueError(f"box coordinate at index {i} cannot be a boolean")
            try:
                val = float(c)
            except (ValueError, TypeError, OverflowError) as err:
                raise ValueError(f"box coordinates must be numeric: {err}") from err
            if not math.isfinite(val):
                raise ValueError(f"box coordinate at index {i} must be finite, got {c}")
            try:
                coords.append(int(round(val)))
            except (ValueError, OverflowError) as err:
                raise ValueError(
                    f"box coordinate at index {i} cannot be converted to integer: {err}"
                ) from err

        return (coords[0], coords[1], coords[2], coords[3])

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, v: Any) -> float:
        """Validate and normalize confidence score."""
        if isinstance(v, bool):
            raise ValueError("confidence cannot be a boolean")
        try:
            val = float(v)
        except (ValueError, TypeError, OverflowError) as err:
            raise ValueError(f"confidence must be numeric: {err}") from err
        if not math.isfinite(val):
            raise ValueError(f"confidence must be finite, got {val}")
        if 1.0 < val <= 1.0001:
            val = 1.0
        elif -0.0001 <= val < 0.0:
            val = 0.0
        return val

    @field_validator("class_name")
    @classmethod
    def _validate_class_name(cls, v: str) -> str:
        """Validate that class_name is not empty or whitespace."""
        s = v.strip()
        if not s:
            raise ValueError("class_name cannot be empty or whitespace")
        return s


def select_device(device: str | None = None) -> str:
    """
    Select the optimal execution device for YOLO inference.

    If device is 'auto' or None, auto-detects PyTorch CUDA / MPS / CPU availability.
    If an explicit device string is provided (e.g. 'cuda:0', 'cpu', 'mps'), returns it.

    Args:
        device: Device configuration string or None.

    Returns:
        Resolved device string (e.g. 'cuda:0', 'mps', 'cpu').
    """
    if (
        device is None
        or not str(device).strip()
        or str(device).strip().lower() in ("auto", "none", "null")
    ):
        try:
            import torch

            if torch.cuda.is_available():
                try:
                    device_id = torch.cuda.current_device() if torch.cuda.device_count() > 0 else 0
                    return f"cuda:{device_id}"
                except Exception:
                    return "cuda:0"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception as exc:
            logger.debug(
                "Failed to detect hardware acceleration, falling back to CPU",
                error=str(exc),
            )
        return "cpu"

    dev_str = str(device).strip()
    dev_clean = dev_str.replace(" ", "").lower()
    if (
        dev_clean in ("cpu", "mps", "cuda")
        or dev_clean.startswith(("cuda:", "mps:"))
        or dev_clean.isdigit()
    ):
        return dev_clean
    return dev_str


class DetectorWorker:
    """
    Object detection worker wrapping ultralytics YOLOv8.

    Loads the YOLO model exactly once in __init__ and performs asynchronous inference
    using asyncio.run_in_executor to avoid blocking the asyncio event loop.
    """

    def __init__(
        self,
        model: str | Path = "yolov8n.pt",
        confidence: float | np.floating[Any] = 0.60,
        classes: Sequence[int] | np.ndarray | None = None,
        device: str | None = None,
        executor: Executor | None = None,
    ) -> None:
        """
        Initialize the YOLOv8 detector worker.

        Args:
            model: Path or model name (default 'yolov8n.pt').
            confidence: Minimum confidence threshold (default 0.60).
            classes: List of COCO class IDs to detect (default [0] for person).
            device: Target execution device ('cuda:0', 'cpu', 'mps', 'auto', or None).
            executor: Optional Executor instance for running inference off-thread.
        """
        if not model or not str(model).strip():
            raise ValueError("model must be a valid non-empty model path or name")

        if isinstance(confidence, bool) or not (
            isinstance(confidence, (int, float, np.integer, np.floating))
            and math.isfinite(float(confidence))
            and 0.0 <= float(confidence) <= 1.0
        ):
            raise ValueError(
                f"Confidence threshold must be a float between 0.0 and 1.0, got {confidence}"
            )

        if classes is not None:
            if isinstance(classes, (str, bytes)):
                raise ValueError("classes must be a sequence of non-negative integers, not string")
            parsed_classes: list[int] = []
            try:
                for c in classes:
                    if isinstance(c, bool):
                        raise ValueError("Class ID cannot be a boolean")
                    c_int = int(c)
                    if c_int < 0:
                        raise ValueError(f"Class ID must be non-negative, got {c_int}")
                    parsed_classes.append(c_int)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid classes specification: {exc}") from exc
            if not parsed_classes:
                raise ValueError("classes must contain at least one valid class ID")
            self.classes = sorted(list(set(parsed_classes)))
        else:
            self.classes = [0]

        self.model_name = str(model).strip()
        self.confidence = float(confidence)
        self.device = select_device(device)

        logger.info(
            "Initializing DetectorWorker",
            model=self.model_name,
            device=self.device,
            confidence=self.confidence,
            classes=self.classes,
        )

        if YOLO is None:
            raise ImportError(
                "ultralytics is required for DetectorWorker. "
                "Please install ultralytics with `pip install ultralytics`."
            )

        # The model must be loaded exactly ONCE in __init__, never reloaded per-frame.
        self.model = YOLO(self.model_name)
        self._model = self.model
        if hasattr(self.model, "to") and callable(self.model.to):
            try:
                self.model.to(self.device)
            except Exception as exc:
                logger.warning(
                    "Failed to transfer YOLO model to target device",
                    device=self.device,
                    error=str(exc),
                )

        self._custom_executor = executor is not None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="detector",
        )
        self._closed = False

    @classmethod
    def from_config(cls, config: DetectionConfig, **kwargs: Any) -> DetectorWorker:
        """Create a DetectorWorker configured from a DetectionConfig instance."""
        if not isinstance(config, DetectionConfig):
            raise TypeError(f"config must be a DetectionConfig, got {type(config).__name__}")
        kwargs.setdefault("model", config.model)
        kwargs.setdefault("confidence", config.confidence)
        kwargs.setdefault("classes", config.classes)
        kwargs.setdefault("device", config.device)
        return cls(**kwargs)

    def _to_python_data(self, data: Any) -> Any:
        """Convert PyTorch tensors or NumPy arrays to native Python structures."""
        if (
            getattr(data, "requires_grad", None) is True
            and hasattr(data, "detach")
            and callable(data.detach)
        ):
            with contextlib.suppress(Exception):
                data = data.detach()
        if hasattr(data, "cpu") and callable(data.cpu):
            with contextlib.suppress(Exception):
                data = data.cpu()
        if hasattr(data, "numpy") and callable(data.numpy):
            with contextlib.suppress(Exception):
                data = data.numpy()
        if hasattr(data, "tolist") and callable(data.tolist):
            with contextlib.suppress(Exception):
                return data.tolist()
        return data

    def _parse_results(self, raw_results: Any) -> list[Detection]:
        """
        Parse ultralytics prediction output into a list of Detection objects.

        If person detection (class 0) is requested and no persons are detected,
        returns an empty list [].
        """
        if raw_results is None:
            return []

        # Extract first result object from list, tuple, generator, iterator, or direct object
        if hasattr(raw_results, "boxes"):
            first_result = raw_results
        elif isinstance(raw_results, (list, tuple)):
            if len(raw_results) == 0:
                return []
            first_result = raw_results[0]
        elif hasattr(raw_results, "__iter__") and not isinstance(raw_results, (str, bytes, dict)):
            first_result = next(iter(raw_results), None)
        else:
            first_result = raw_results

        if first_result is None:
            return []

        boxes_obj = getattr(first_result, "boxes", None)
        if boxes_obj is None:
            return []
        with contextlib.suppress(TypeError, AttributeError):
            if len(boxes_obj) == 0:
                return []

        names: dict[Any, str] | list[str] = getattr(first_result, "names", {})

        def resolve_class_name(cls_id: int) -> str:
            name: str | None = None
            if isinstance(names, dict):
                if cls_id in names:
                    name = str(names[cls_id]).strip()
                elif str(cls_id) in names:
                    name = str(names[str(cls_id)]).strip()
            elif isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
                name = str(names[cls_id]).strip()

            if name:
                return name
            return "person" if cls_id == 0 else f"class_{cls_id}"

        xyxy = getattr(boxes_obj, "xyxy", None)
        conf = getattr(boxes_obj, "conf", None)
        cls_ids = getattr(boxes_obj, "cls", None)

        detections: list[Detection] = []
        has_person = False

        if xyxy is not None:
            xyxy_list = self._to_python_data(xyxy)
            conf_list = self._to_python_data(conf) if conf is not None else None
            cls_list = self._to_python_data(cls_ids) if cls_ids is not None else None

            # Handle 1D array/list of 4 coordinates [x1, y1, x2, y2]
            if (
                isinstance(xyxy_list, (list, tuple))
                and len(xyxy_list) == 4
                and all(
                    isinstance(c, (int, float, np.integer, np.floating)) and not isinstance(c, bool)
                    for c in xyxy_list
                )
            ):
                xyxy_list = [xyxy_list]

            if not isinstance(xyxy_list, (list, tuple)) or len(xyxy_list) == 0:
                return []

            # Normalize conf_list to list
            if conf_list is not None:
                if not isinstance(conf_list, (list, tuple)):
                    conf_list = [conf_list]
                conf_list = [
                    c[0] if isinstance(c, (list, tuple)) and len(c) > 0 else c for c in conf_list
                ]

            # Normalize cls_list to list
            if cls_list is not None:
                if not isinstance(cls_list, (list, tuple)):
                    cls_list = [cls_list]
                cls_list = [
                    c[0] if isinstance(c, (list, tuple)) and len(c) > 0 else c for c in cls_list
                ]

            for i, box_coords in enumerate(xyxy_list):
                if (
                    isinstance(box_coords, (list, tuple))
                    and len(box_coords) == 1
                    and isinstance(box_coords[0], (list, tuple, np.ndarray))
                ):
                    box_coords = box_coords[0]

                c_id = 0
                if cls_list is not None and i < len(cls_list):
                    val = cls_list[i]
                    if not isinstance(val, bool):
                        try:
                            c_id = int(val)
                        except (ValueError, TypeError):
                            c_id = 0

                if c_id not in self.classes:
                    continue

                confidence_val = self.confidence
                if conf_list is not None and i < len(conf_list):
                    val = conf_list[i]
                    if not isinstance(val, bool):
                        try:
                            confidence_val = float(val)
                        except (ValueError, TypeError):
                            confidence_val = self.confidence

                if confidence_val < self.confidence - 1e-4:
                    continue

                class_name = resolve_class_name(c_id)

                try:
                    det = Detection(
                        box=box_coords,
                        confidence=confidence_val,
                        class_name=class_name,
                    )
                    detections.append(det)
                    if c_id == 0:
                        has_person = True
                except Exception as exc:
                    logger.warning(
                        "Failed to construct Detection from prediction",
                        error=str(exc),
                        box=box_coords,
                    )

            # R1 Requirement: If no persons (class 0) are detected, it must immediately return [].
            if 0 in self.classes and not has_person:
                return []

            return detections

        # Fallback: iterable of individual box representations
        if hasattr(boxes_obj, "__iter__"):
            for b in boxes_obj:
                b_xyxy = getattr(b, "xyxy", None)
                if b_xyxy is None:
                    continue
                b_xyxy_list = self._to_python_data(b_xyxy)
                if (
                    isinstance(b_xyxy_list, (list, tuple))
                    and len(b_xyxy_list) == 1
                    and isinstance(b_xyxy_list[0], (list, tuple))
                ):
                    b_xyxy_list = b_xyxy_list[0]

                b_conf = self._to_python_data(getattr(b, "conf", [self.confidence]))
                if isinstance(b_conf, (list, tuple)) and len(b_conf) > 0:
                    b_conf = b_conf[0]
                b_cls = self._to_python_data(getattr(b, "cls", [0]))
                if isinstance(b_cls, (list, tuple)) and len(b_cls) > 0:
                    b_cls = b_cls[0]

                c_id = 0
                if not isinstance(b_cls, bool):
                    try:
                        c_id = int(b_cls)
                    except (ValueError, TypeError):
                        c_id = 0

                if c_id not in self.classes:
                    continue

                confidence_val = self.confidence
                if not isinstance(b_conf, bool):
                    try:
                        confidence_val = float(b_conf)
                    except (ValueError, TypeError):
                        confidence_val = self.confidence

                if confidence_val < self.confidence - 1e-4:
                    continue

                class_name = resolve_class_name(c_id)

                try:
                    det = Detection(
                        box=b_xyxy_list,
                        confidence=confidence_val,
                        class_name=class_name,
                    )
                    detections.append(det)
                    if c_id == 0:
                        has_person = True
                except Exception as exc:
                    logger.warning(
                        "Failed to construct Detection from fallback box",
                        error=str(exc),
                        box=b_xyxy_list,
                    )

            if 0 in self.classes and not has_person:
                return []

            return detections

        return []

    def _predict_sync(self, frame: np.ndarray) -> list[Detection]:
        """
        Execute synchronous blocking inference inside the executor thread.

        Calls model.predict(frame, classes=self.classes, conf=self.confidence, verbose=False)
        and parses detections.
        """
        if (
            frame is None
            or not isinstance(frame, np.ndarray)
            or frame.size == 0
            or frame.ndim not in (2, 3)
            or not np.issubdtype(frame.dtype, np.number)
        ):
            return []

        try:
            raw_results = self.model.predict(
                frame,
                classes=self.classes,
                conf=self.confidence,
                verbose=False,
            )
            return self._parse_results(raw_results)
        except Exception as exc:
            logger.error("YOLO inference failed", error=str(exc))
            return []

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Asynchronously run object detection on the provided video frame.

        Runs the blocking YOLO model.predict call inside an asyncio.run_in_executor
        to prevent blocking the main asyncio event loop.

        Args:
            frame: Video frame as a NumPy array.

        Returns:
            List of Detection objects. If no persons (class 0) are detected, returns [].
        """
        if (
            frame is None
            or not isinstance(frame, np.ndarray)
            or frame.size == 0
            or frame.ndim not in (2, 3)
            or not np.issubdtype(frame.dtype, np.number)
        ):
            return []

        if self._closed:
            raise RuntimeError("DetectorWorker is closed and cannot process frames")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._predict_sync, frame)

    def close(self) -> None:
        """Shut down the internal executor if created by this worker."""
        self._closed = True
        if not self._custom_executor and self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    async def stop(self) -> None:
        """Asynchronously close the detector worker and release resources."""
        self.close()

    def __enter__(self) -> DetectorWorker:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> DetectorWorker:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
