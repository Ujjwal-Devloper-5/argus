"""
Unit tests for the YOLOv8 Object Detection Engine (argus.core.detector).

Tests verify:
1. Detection Pydantic model validation, type conversions, and boundary checks.
2. Hardware acceleration auto-detection (CUDA, MPS, CPU).
3. DetectorWorker initialization (loading YOLO exactly once).
4. Detection inference with mocked YOLO predictions, blank frames, random noise, and empty inputs.
5. Strict typing and attribute matching of returned Detection objects.
6. Non-blocking behavior of the async executor during inference.
7. Lifecycle management and clean teardown.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from argus.config.settings import DetectionConfig
from argus.core.detector import Detection, DetectorWorker, select_device

# ===========================================================================
# 1. Detection Pydantic Model Tests
# ===========================================================================


class TestDetectionModel:
    """Tests for the Detection Pydantic model."""

    def test_valid_detection_creation(self) -> None:
        """Verify normal creation with expected integer box coordinates."""
        det = Detection(box=(10, 20, 100, 200), confidence=0.85, class_name="person")
        assert det.box == (10, 20, 100, 200)
        assert isinstance(det.box, tuple)
        assert all(isinstance(c, int) for c in det.box)
        assert det.confidence == pytest.approx(0.85)
        assert det.class_name == "person"

    def test_float_coordinates_converted_to_ints(self) -> None:
        """Verify that floating point coordinates are rounded to integers."""
        det = Detection(box=[10.4, 20.6, 99.7, 200.2], confidence=0.75, class_name="person")
        assert det.box == (10, 21, 100, 200)
        assert all(isinstance(c, int) for c in det.box)

    def test_numpy_array_coordinates_converted_to_ints(self) -> None:
        """Verify coordinates passed as a numpy array are properly converted."""
        coords = np.array([5.0, 15.0, 50.0, 80.0])
        det = Detection(box=coords, confidence=0.90, class_name="person")
        assert det.box == (5, 15, 50, 80)
        assert isinstance(det.box, tuple)

    def test_default_class_name(self) -> None:
        """Verify default class_name is 'person'."""
        det = Detection(box=(0, 0, 50, 50), confidence=0.65)
        assert det.class_name == "person"

    def test_invalid_box_length(self) -> None:
        """Verify box with length != 4 raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(10, 20, 30), confidence=0.8)

        with pytest.raises(ValidationError):
            Detection(box=(10, 20, 30, 40, 50), confidence=0.8)

    def test_invalid_box_non_numeric(self) -> None:
        """Verify non-numeric coordinates raise ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=("a", "b", "c", "d"), confidence=0.8)

    def test_invalid_box_non_sequence(self) -> None:
        """Verify non-sequence box raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=1234, confidence=0.8)  # type: ignore[arg-type]

    def test_invalid_confidence_out_of_bounds(self) -> None:
        """Verify confidence outside [0.0, 1.0] raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=-0.1)

        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=1.5)

    def test_invalid_confidence_non_finite(self) -> None:
        """Verify NaN or Inf confidence raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=float("nan"))

        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=float("inf"))

    def test_invalid_confidence_non_numeric(self) -> None:
        """Verify non-numeric confidence raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence="not_a_number")  # type: ignore[arg-type]

    def test_confidence_micro_clamping(self) -> None:
        """Verify micro rounding offsets at boundaries [0, 1] are normalized."""
        det_high = Detection(box=(0, 0, 10, 10), confidence=1.00005)
        assert det_high.confidence == 1.0

        det_low = Detection(box=(0, 0, 10, 10), confidence=-0.00005)
        assert det_low.confidence == 0.0

    def test_empty_class_name_rejected(self) -> None:
        """Verify empty string class_name raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=0.8, class_name="")

    def test_infinite_coordinate_raises_validation_error(self) -> None:
        """Verify infinite coordinates raise ValidationError instead of unhandled OverflowError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, float("inf"), 10), confidence=0.5)

        with pytest.raises(ValidationError):
            Detection(box=(float("-inf"), 0, 10, 10), confidence=0.5)

    def test_nan_coordinate_raises_validation_error(self) -> None:
        """Verify NaN coordinates raise ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, float("nan"), 10), confidence=0.5)

    def test_boolean_coordinate_rejected(self) -> None:
        """Verify boolean coordinates are rejected as non-numeric."""
        with pytest.raises(ValidationError):
            Detection(box=(True, False, 10, 20), confidence=0.5)

    def test_boolean_confidence_rejected(self) -> None:
        """Verify boolean confidence (True/False) is rejected."""
        with pytest.raises(ValidationError):
            Detection(box=(10, 20, 30, 40), confidence=True)

        with pytest.raises(ValidationError):
            Detection(box=(10, 20, 30, 40), confidence=False)

    def test_box_from_torch_tensor(self) -> None:
        """Verify box can be constructed from a PyTorch tensor."""
        try:
            import torch

            t_box = torch.tensor([15.0, 25.0, 105.0, 205.0])
            det = Detection(box=t_box, confidence=0.8)
            assert det.box == (15, 25, 105, 205)
        except ImportError:
            pytest.skip("PyTorch not installed")

    def test_box_from_arbitrary_sequence(self) -> None:
        """Verify box can be constructed from collections.deque or custom sequence."""
        from collections import deque

        seq = deque([10, 20, 30, 40])
        det = Detection(box=seq, confidence=0.8)
        assert det.box == (10, 20, 30, 40)

    def test_model_serialization(self) -> None:
        """Verify serialization via model_dump."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.95, class_name="person")
        data = det.model_dump()
        assert data == {
            "box": (10, 20, 30, 40),
            "confidence": 0.95,
            "class_name": "person",
        }

    def test_detection_is_hashable_and_frozen(self) -> None:
        """Verify Detection is immutable (frozen=True) and can be hashed/added to sets."""
        det1 = Detection(box=(10, 20, 30, 40), confidence=0.85, class_name="person")
        det2 = Detection(box=(10, 20, 30, 40), confidence=0.85, class_name="person")
        det3 = Detection(box=(50, 60, 70, 80), confidence=0.90, class_name="person")

        assert hash(det1) == hash(det2)
        det_set = {det1, det2, det3}
        assert len(det_set) == 2
        assert det1 in det_set

        with pytest.raises(ValidationError):
            det1.confidence = 0.99  # type: ignore[misc]

    def test_detection_coordinate_properties(self) -> None:
        """Verify bounding box properties: x1, y1, x2, y2, width, height, area."""
        det = Detection(box=(15, 25, 115, 225), confidence=0.85, class_name="person")
        assert det.x1 == 15
        assert det.y1 == 25
        assert det.x2 == 115
        assert det.y2 == 225
        assert det.width == 100
        assert det.height == 200
        assert det.area == 20000

    def test_detection_center_property(self) -> None:
        """Verify center coordinate property calculation."""
        det = Detection(box=(10, 20, 110, 220), confidence=0.85, class_name="person")
        assert det.center == (60, 120)

    def test_2d_bounding_box_unwrapped(self) -> None:
        """Verify 2D single-box arrays/lists from PyTorch/NumPy are safely unwrapped."""
        # 2D Python list
        det_list = Detection(box=[[10, 20, 30, 40]], confidence=0.80)
        assert det_list.box == (10, 20, 30, 40)

        # 2D NumPy array
        det_np = Detection(box=np.array([[10, 20, 30, 40]]), confidence=0.80)
        assert det_np.box == (10, 20, 30, 40)

        # 2D PyTorch tensor if installed
        try:
            import torch

            det_torch = Detection(box=torch.tensor([[10, 20, 30, 40]]), confidence=0.80)
            assert det_torch.box == (10, 20, 30, 40)
        except ImportError:
            pass

    def test_whitespace_class_name_rejected(self) -> None:
        """Verify whitespace-only class_name raises ValidationError."""
        with pytest.raises(ValidationError):
            Detection(box=(0, 0, 10, 10), confidence=0.8, class_name="   ")

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Verify leading and trailing whitespace in class_name is stripped."""
        det = Detection(box=(0, 0, 10, 10), confidence=0.8, class_name="  person  ")
        assert det.class_name == "person"


# ===========================================================================
# 2. Hardware / Device Selection Tests
# ===========================================================================


class TestDeviceSelection:
    """Tests for hardware acceleration auto-detection."""

    def test_explicit_cpu(self) -> None:
        assert select_device("cpu") == "cpu"

    def test_explicit_cuda(self) -> None:
        assert select_device("cuda:0") == "cuda:0"
        assert select_device("cuda:1") == "cuda:1"

    def test_explicit_mps(self) -> None:
        assert select_device("mps") == "mps"

    def test_auto_detect_cuda_available(self) -> None:
        """Verify auto selects cuda when available."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.cuda.current_device.return_value = 0

        with patch.dict("sys.modules", {"torch": mock_torch}):
            dev = select_device("auto")
            assert dev == "cuda:0"

    def test_auto_detect_mps_available_when_cuda_not(self) -> None:
        """Verify auto selects mps when cuda is unavailable but mps is available."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            dev = select_device("auto")
            assert dev == "mps"

    def test_auto_detect_fallback_to_cpu(self) -> None:
        """Verify auto falls back to cpu when no GPU is available."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            dev = select_device("auto")
            assert dev == "cpu"

    def test_auto_detect_none_or_empty_arg(self) -> None:
        """Verify None and empty strings trigger auto-detection."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert select_device(None) == "cpu"
            assert select_device("") == "cpu"
            assert select_device("   ") == "cpu"

    def test_auto_detect_handles_torch_import_error(self) -> None:
        """Verify graceful fallback to cpu if torch raises an exception."""
        with patch.dict("sys.modules", {"torch": None}):
            dev = select_device("auto")
            assert dev == "cpu"

    def test_auto_detect_none_and_null_strings(self) -> None:
        """Verify 'none' and 'null' strings trigger auto-detection."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.backends.mps.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert select_device("none") == "cpu"
            assert select_device("null") == "cpu"

    def test_select_device_case_normalization(self) -> None:
        """Verify casing of explicit devices is normalized."""
        assert select_device("CPU") == "cpu"
        assert select_device("CUDA") == "cuda"
        assert select_device("CUDA:0 ") == "cuda:0"
        assert select_device("MPS") == "mps"

    def test_select_device_cuda_current_device_exception(self) -> None:
        """Verify fallback to cuda:0 if current_device() fails when CUDA is available."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.current_device.side_effect = RuntimeError("Driver mismatch")

        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert select_device("auto") == "cuda:0"

    def test_select_device_whitespace_and_custom_devices(self) -> None:
        """Verify whitespace removal and MPS/numeric/custom device resolution."""
        assert select_device("cuda: 0") == "cuda:0"
        assert select_device("CUDA: 1 ") == "cuda:1"
        assert select_device("MPS:0") == "mps:0"
        assert select_device("0") == "0"
        assert select_device("custom_npu") == "custom_npu"


# ===========================================================================
# 3. DetectorWorker Initialization Tests
# ===========================================================================


class TestDetectorWorkerInit:
    """Tests for initialization of DetectorWorker."""

    def test_model_loaded_once_in_init(self) -> None:
        """Verify YOLO model is instantiated exactly once during __init__."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(model="custom_model.pt", device="cpu")
            assert mock_yolo_cls.call_count == 1
            mock_yolo_cls.assert_called_once_with("custom_model.pt")
            assert worker.model is mock_model
            mock_model.to.assert_called_once_with("cpu")
            worker.close()

    def test_from_config(self) -> None:
        """Verify initialization via DetectionConfig."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_yolo_cls.return_value = mock_model

            cfg = DetectionConfig(
                model="yolov8s.pt",
                confidence=0.70,
                classes=[0],
                device="cpu",
            )
            worker = DetectorWorker.from_config(cfg)
            assert worker.model_name == "yolov8s.pt"
            assert worker.confidence == 0.70
            assert worker.classes == [0]
            assert worker.device == "cpu"
            mock_yolo_cls.assert_called_once_with("yolov8s.pt")
            worker.close()

    def test_from_config_invalid_type(self) -> None:
        """Verify TypeError when non-DetectionConfig is passed to from_config."""
        with pytest.raises(TypeError):
            DetectorWorker.from_config("not_a_config")  # type: ignore[arg-type]

    def test_invalid_confidence_raises_value_error(self) -> None:
        """Verify invalid confidence raises ValueError."""
        with pytest.raises(ValueError):
            DetectorWorker(confidence=-0.1)
        with pytest.raises(ValueError):
            DetectorWorker(confidence=1.5)
        with pytest.raises(ValueError):
            DetectorWorker(confidence=float("nan"))

    def test_device_transfer_failure_is_handled_gracefully(self) -> None:
        """Verify failure in model.to() does not prevent worker initialization."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_model.to.side_effect = RuntimeError("CUDA device not found")
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(device="cuda:0")
            assert worker.model is mock_model
            worker.close()

    def test_missing_ultralytics_raises_import_error(self) -> None:
        """Verify ImportError if YOLO is None."""
        with (
            patch("argus.core.detector.YOLO", None),
            pytest.raises(ImportError, match="ultralytics is required"),
        ):
            DetectorWorker()

    def test_numpy_float_confidence_accepted(self) -> None:
        """Verify numpy floating scalars are accepted for confidence."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            w1 = DetectorWorker(confidence=np.float32(0.65))
            assert w1.confidence == pytest.approx(0.65)
            w1.close()

            w2 = DetectorWorker(confidence=np.float64(0.82))
            assert w2.confidence == pytest.approx(0.82)
            w2.close()

    def test_empty_or_whitespace_model_rejected(self) -> None:
        """Verify empty, whitespace, or None model strings raise ValueError."""
        with patch("argus.core.detector.YOLO"):
            with pytest.raises(ValueError, match="model must be a valid non-empty"):
                DetectorWorker(model="")
            with pytest.raises(ValueError, match="model must be a valid non-empty"):
                DetectorWorker(model="   ")
            with pytest.raises(ValueError, match="model must be a valid non-empty"):
                DetectorWorker(model=None)  # type: ignore[arg-type]

    def test_invalid_classes_rejected(self) -> None:
        """Verify booleans, negative integers, and invalid types in classes are rejected."""
        with patch("argus.core.detector.YOLO"):
            with pytest.raises(ValueError):
                DetectorWorker(classes=[True, False])
            with pytest.raises(ValueError):
                DetectorWorker(classes=[-1])
            with pytest.raises(ValueError):
                DetectorWorker(classes="0,1")  # type: ignore[arg-type]
            with pytest.raises(ValueError):
                DetectorWorker(classes=["person"])  # type: ignore[list-item]

    def test_classes_as_numpy_array_and_deduplication(self) -> None:
        """Verify numpy array of class IDs is parsed and deduplicated."""
        with patch("argus.core.detector.YOLO"):
            worker = DetectorWorker(classes=np.array([2, 0, 2]))
            assert worker.classes == [0, 2]
            worker.close()

    def test_empty_classes_sequence_rejected(self) -> None:
        """Verify empty classes sequence (list, tuple, numpy array) raises ValueError."""
        with patch("argus.core.detector.YOLO"):
            with pytest.raises(ValueError, match="at least one valid class ID"):
                DetectorWorker(classes=[])
            with pytest.raises(ValueError, match="at least one valid class ID"):
                DetectorWorker(classes=())
            with pytest.raises(ValueError, match="at least one valid class ID"):
                DetectorWorker(classes=np.array([]))

    def test_model_path_instance_accepted(self) -> None:
        """Verify pathlib.Path object is accepted as model argument."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            worker = DetectorWorker(model=Path("/models/custom_yolo.pt"))
            assert worker.model_name == "/models/custom_yolo.pt"
            mock_yolo_cls.assert_called_once_with("/models/custom_yolo.pt")
            worker.close()


# ===========================================================================
# 4. DetectorWorker Detection Tests
# ===========================================================================


class TestDetectorWorkerDetect:
    """Tests for async detect method."""

    def _create_mock_yolo_result(
        self,
        xyxy: Any,
        conf: Any,
        cls: Any,
        names: dict[Any, str] | list[str] | None = None,
    ) -> MagicMock:
        """Helper to create a structured YOLO prediction result mock."""
        mock_result = MagicMock()
        mock_boxes = MagicMock()

        mock_boxes.xyxy = xyxy
        mock_boxes.conf = conf
        mock_boxes.cls = cls
        if hasattr(xyxy, "__len__"):
            mock_boxes.__len__ = MagicMock(return_value=len(xyxy))

        mock_result.boxes = mock_boxes
        mock_result.names = names if names is not None else {0: "person", 1: "bicycle", 2: "car"}
        return mock_result

    @pytest.mark.asyncio
    async def test_successful_person_detection(self) -> None:
        """
        Mock the YOLO class to simulate a successful detection.
        Assert that returned objects are strictly of type Detection,
        and that bounding box and confidence match the mocked output.
        """
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[100.0, 150.0, 300.0, 450.0]],
                conf=[0.88],
                cls=[0],
                names={0: "person"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(confidence=0.60, device="cpu")
            frame = np.ones((480, 640, 3), dtype=np.uint8) * 128

            detections = await worker.detect(frame)

            # Assert model was loaded once in __init__, not during detect
            assert mock_yolo_cls.call_count == 1
            # Assert predict called with expected parameters
            mock_model.predict.assert_called_once_with(
                frame,
                classes=[0],
                conf=0.60,
                verbose=False,
            )

            # Assertions on returned objects
            assert len(detections) == 1
            det = detections[0]
            assert isinstance(det, Detection)
            assert det.box == (100, 150, 300, 450)
            assert isinstance(det.box, tuple)
            assert all(isinstance(c, int) for c in det.box)
            assert det.confidence == pytest.approx(0.88)
            assert det.class_name == "person"

            worker.close()

    @pytest.mark.asyncio
    async def test_multiple_person_detections(self) -> None:
        """Verify multiple person detections are parsed correctly."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[
                    [10.0, 20.0, 100.0, 200.0],
                    [200.0, 150.0, 400.0, 450.0],
                ],
                conf=[0.92, 0.76],
                cls=[0, 0],
                names={0: "person"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 2
            assert all(isinstance(d, Detection) for d in detections)
            assert detections[0].box == (10, 20, 100, 200)
            assert detections[0].confidence == pytest.approx(0.92)
            assert detections[1].box == (200, 150, 400, 450)
            assert detections[1].confidence == pytest.approx(0.76)

            worker.close()

    @pytest.mark.asyncio
    async def test_blank_image_returns_empty_list(self) -> None:
        """
        Provide a mock numpy array (blank image) and assert that it gracefully
        returns an empty list when no detections are found.
        """
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            # YOLO returns empty boxes for a blank image
            mock_result = self._create_mock_yolo_result(
                xyxy=[],
                conf=[],
                cls=[],
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            detections = await worker.detect(blank_frame)
            assert detections == []
            assert isinstance(detections, list)

            worker.close()

    @pytest.mark.asyncio
    async def test_random_noise_frame_returns_empty_list(self) -> None:
        """
        Provide a random noise frame and assert that it gracefully returns []
        when no persons are detected.
        """
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(xyxy=[], conf=[], cls=[])
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            noise_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)

            detections = await worker.detect(noise_frame)
            assert detections == []
            assert isinstance(detections, list)

            worker.close()

    @pytest.mark.asyncio
    async def test_no_persons_detected_returns_empty_list(self) -> None:
        """
        Assert that if detections occur but none are person (class 0),
        an empty list [] is immediately returned.
        """
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            # Only car (class 2) detected
            mock_result = self._create_mock_yolo_result(
                xyxy=[[50.0, 50.0, 200.0, 200.0]],
                conf=[0.95],
                cls=[2],
                names={0: "person", 2: "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            detections = await worker.detect(frame)
            assert detections == []

            worker.close()

    @pytest.mark.asyncio
    async def test_filters_non_person_when_mixed_classes_present(self) -> None:
        """Verify that non-person detections are excluded while person detections are kept."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[
                    [10.0, 10.0, 50.0, 50.0],  # car (class 2)
                    [100.0, 100.0, 250.0, 300.0],  # person (class 0)
                    [300.0, 300.0, 350.0, 350.0],  # dog (class 16)
                ],
                conf=[0.90, 0.82, 0.70],
                cls=[2, 0, 16],
                names={0: "person", 2: "car", 16: "dog"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            detections = await worker.detect(frame)
            assert len(detections) == 1
            assert detections[0].class_name == "person"
            assert detections[0].box == (100, 100, 250, 300)
            assert detections[0].confidence == pytest.approx(0.82)

            worker.close()

    @pytest.mark.asyncio
    async def test_names_as_list_instead_of_dict(self) -> None:
        """Verify class name lookup when result.names is a list."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[10.0, 20.0, 30.0, 40.0]],
                conf=[0.90],
                cls=[0],
                names=["person", "bicycle", "car"],
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)
            assert len(detections) == 1
            assert detections[0].class_name == "person"
            worker.close()

    @pytest.mark.asyncio
    async def test_tensor_conversion_helpers(self) -> None:
        """Verify _to_python_data handles PyTorch / NumPy mocks with cpu(), numpy(), tolist()."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            worker = DetectorWorker()

            # Mock tensor with cpu().numpy().tolist()
            mock_tensor = MagicMock()
            mock_cpu = MagicMock()
            mock_numpy = MagicMock()
            mock_tensor.cpu.return_value = mock_cpu
            mock_cpu.numpy.return_value = mock_numpy
            mock_numpy.tolist.return_value = [1, 2, 3]

            res = worker._to_python_data(mock_tensor)
            assert res == [1, 2, 3]
            worker.close()

    @pytest.mark.asyncio
    async def test_empty_or_none_frame_returns_empty_list(self) -> None:
        """Verify that None, empty arrays, or non-numpy inputs return [] immediately."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_yolo_cls.return_value = mock_model
            worker = DetectorWorker()

            # None frame
            assert await worker.detect(None) == []  # type: ignore[arg-type]

            # Zero-sized numpy array
            empty_frame = np.empty((0, 0, 3), dtype=np.uint8)
            assert await worker.detect(empty_frame) == []

            # Non-numpy input
            assert await worker.detect("invalid") == []  # type: ignore[arg-type]

            # Direct call to _predict_sync with empty frame
            assert worker._predict_sync(None) == []  # type: ignore[arg-type]
            assert worker._predict_sync(empty_frame) == []

            # Model predict should never have been called
            mock_model.predict.assert_not_called()
            worker.close()

    def test_parse_results_edge_cases(self) -> None:
        """Verify edge cases in _parse_results directly."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            worker = DetectorWorker()

            # Empty raw results
            assert worker._parse_results([]) == []
            assert worker._parse_results(None) == []
            assert worker._parse_results([None]) == []

            # Result with boxes=None
            mock_res_no_boxes = MagicMock()
            mock_res_no_boxes.boxes = None
            assert worker._parse_results([mock_res_no_boxes]) == []

            # Result with boxes.xyxy=None and not iterable
            mock_res_bad_boxes = MagicMock()
            mock_res_bad_boxes.boxes = MagicMock()
            mock_res_bad_boxes.boxes.xyxy = None
            mock_res_bad_boxes.boxes.__iter__.return_value = []
            assert worker._parse_results([mock_res_bad_boxes]) == []

            # Fallback with invalid box coords logged gracefully
            mock_res_fallback = MagicMock()
            bad_box = MagicMock()
            bad_box.xyxy = [1, 2]  # invalid 2 coords
            bad_box.conf = [0.9]
            bad_box.cls = [0]
            mock_res_fallback.boxes = [bad_box]
            mock_res_fallback.names = {0: "person"}
            assert worker._parse_results([mock_res_fallback]) == []

            # Corrupted cls and conf in xyxy path
            mock_res_corrupt = MagicMock()
            corrupt_boxes = MagicMock()
            corrupt_boxes.xyxy = [[10.0, 20.0, 30.0, 40.0]]
            corrupt_boxes.conf = ["not_a_float"]
            corrupt_boxes.cls = ["not_an_int"]
            corrupt_boxes.__len__ = MagicMock(return_value=1)
            mock_res_corrupt.boxes = corrupt_boxes
            mock_res_corrupt.names = {0: "person"}
            dets_corrupt = worker._parse_results([mock_res_corrupt])
            assert len(dets_corrupt) == 1
            assert dets_corrupt[0].confidence == worker.confidence

            # Fallback with xyxy=None, nested list [[x1, y1, x2, y2]], corrupt cls/conf, and unrequested class
            box_none_xyxy = MagicMock()
            box_none_xyxy.xyxy = None

            box_nested = MagicMock()
            box_nested.xyxy = [[10.0, 20.0, 30.0, 40.0]]
            box_nested.conf = ["not_a_float"]
            box_nested.cls = ["not_an_int"]

            box_unrequested = MagicMock()
            box_unrequested.xyxy = [50.0, 60.0, 70.0, 80.0]
            box_unrequested.conf = [0.9]
            box_unrequested.cls = [99]  # not in worker.classes [0]

            mock_res_fallback_complex = MagicMock()
            mock_res_fallback_complex.boxes = [box_none_xyxy, box_unrequested, box_nested]
            mock_res_fallback_complex.names = {0: "person"}
            dets_fallback = worker._parse_results([mock_res_fallback_complex])
            assert len(dets_fallback) == 1
            assert dets_fallback[0].box == (10, 20, 30, 40)

            worker.close()

    @pytest.mark.asyncio
    async def test_closed_worker_raises_runtime_error(self) -> None:
        """Verify detect() raises RuntimeError if called on a closed worker."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            worker = DetectorWorker()
            worker.close()

            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            with pytest.raises(RuntimeError, match="closed"):
                await worker.detect(frame)

    @pytest.mark.asyncio
    async def test_fallback_box_iterable_parsing(self) -> None:
        """Verify fallback parsing when boxes is a list of individual box objects."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            box_item = MagicMock()
            box_item.xyxy = [10.0, 20.0, 30.0, 40.0]
            box_item.conf = [0.85]
            box_item.cls = [0]

            mock_result = MagicMock()
            mock_result.boxes = [box_item]
            mock_result.names = {0: "person"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (10, 20, 30, 40)
            assert detections[0].confidence == pytest.approx(0.85)

            worker.close()

    @pytest.mark.asyncio
    async def test_1d_xyxy_array_and_scalar_conf_and_cls(self) -> None:
        """Verify that 1D xyxy array and scalar conf/cls are correctly parsed."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = MagicMock()
            mock_boxes = MagicMock()
            mock_boxes.xyxy = np.array([100.0, 150.0, 300.0, 450.0])
            mock_boxes.conf = 0.88
            mock_boxes.cls = 0
            mock_boxes.__len__ = MagicMock(return_value=1)
            mock_result.boxes = mock_boxes
            mock_result.names = {0: "person"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (100, 150, 300, 450)
            assert detections[0].confidence == pytest.approx(0.88)
            assert detections[0].class_name == "person"
            worker.close()

    @pytest.mark.asyncio
    async def test_multiclass_configured_with_person_and_car(self) -> None:
        """Verify multiclass detection when configured with both person and car."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[
                    [10.0, 20.0, 30.0, 40.0],
                    [50.0, 60.0, 70.0, 80.0],
                ],
                conf=[0.90, 0.85],
                cls=[0, 2],
                names={0: "person", 2: "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 2])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 2
            assert detections[0].class_name == "person"
            assert detections[0].box == (10, 20, 30, 40)
            assert detections[1].class_name == "car"
            assert detections[1].box == (50, 60, 70, 80)
            worker.close()

    @pytest.mark.asyncio
    async def test_multiclass_car_present_but_no_person_returns_empty_list(self) -> None:
        """Verify that if person is in classes but no person is detected, [] is returned."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[50.0, 60.0, 70.0, 80.0]],
                conf=[0.85],
                cls=[2],
                names={0: "person", 2: "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 2])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert detections == []
            worker.close()

    @pytest.mark.asyncio
    async def test_multiclass_configured_with_car_only(self) -> None:
        """Verify detection when explicitly configured with non-person classes only."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[50.0, 60.0, 70.0, 80.0]],
                conf=[0.85],
                cls=[2],
                names={2: "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[2])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].class_name == "car"
            assert detections[0].box == (50, 60, 70, 80)
            worker.close()

    @pytest.mark.asyncio
    async def test_invalid_frame_dimensions_ndim(self) -> None:
        """Verify that 1D or 4D numpy arrays return [] without calling predict."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_yolo_cls.return_value = mock_model
            worker = DetectorWorker()

            # 1D array
            assert await worker.detect(np.zeros(10)) == []
            # 4D array
            assert await worker.detect(np.zeros((2, 2, 2, 2))) == []

            mock_model.predict.assert_not_called()
            worker.close()

    @pytest.mark.asyncio
    async def test_predict_exception_handled_gracefully(self) -> None:
        """Verify that exceptions raised by model.predict are caught and return []."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_model.predict.side_effect = RuntimeError("Simulated YOLO inference failure")
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert detections == []
            worker.close()

    @pytest.mark.asyncio
    async def test_pytorch_tensor_with_requires_grad(self) -> None:
        """Verify that PyTorch tensors with requires_grad=True are detached and parsed."""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not installed")

        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = MagicMock()
            mock_boxes = MagicMock()
            mock_boxes.xyxy = torch.tensor([[10.0, 20.0, 100.0, 200.0]], requires_grad=True)
            mock_boxes.conf = torch.tensor([0.92], requires_grad=True)
            mock_boxes.cls = torch.tensor([0.0], requires_grad=True)
            mock_boxes.__len__ = MagicMock(return_value=1)
            mock_result.boxes = mock_boxes
            mock_result.names = {0: "person"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (10, 20, 100, 200)
            assert detections[0].confidence == pytest.approx(0.92)
            worker.close()

    @pytest.mark.asyncio
    async def test_names_dict_with_string_keys(self) -> None:
        """Verify that names dictionary with string keys (e.g. from JSON/YAML) maps correctly."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[10.0, 20.0, 100.0, 200.0], [50.0, 60.0, 150.0, 250.0]],
                conf=[0.90, 0.85],
                cls=[0, 2],
                names={"0": "person", "2": "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 2])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 2
            assert detections[0].class_name == "person"
            assert detections[1].class_name == "car"
            worker.close()

    @pytest.mark.asyncio
    async def test_generator_raw_results_parsed(self) -> None:
        """Verify that generator returned by predict (e.g. stream=True) is parsed."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[15.0, 25.0, 105.0, 205.0]],
                conf=[0.88],
                cls=[0],
                names={0: "person"},
            )
            mock_model.predict.return_value = (r for r in [mock_result])
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (15, 25, 105, 205)
            worker.close()

    @pytest.mark.asyncio
    async def test_single_result_raw_results_parsed(self) -> None:
        """Verify that an unwrapped single Result object is parsed."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[20.0, 30.0, 120.0, 220.0]],
                conf=[0.91],
                cls=[0],
                names={0: "person"},
            )
            mock_model.predict.return_value = mock_result
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (20, 30, 120, 220)
            worker.close()

    @pytest.mark.asyncio
    async def test_corrupt_person_box_dropped_and_returns_empty_list(self) -> None:
        """Verify corrupt person box is dropped; if no valid person remains, returns []."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[float("nan"), 20.0, 100.0, 200.0], [50.0, 60.0, 150.0, 250.0]],
                conf=[0.90, 0.85],
                cls=[0, 2],
                names={0: "person", 2: "car"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 2])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            # Corrupt person box failed validation -> 0 valid persons -> returns []
            assert detections == []
            worker.close()

    @pytest.mark.asyncio
    async def test_partial_box_corruption_keeps_valid_person(self) -> None:
        """Verify valid detections are kept when another box in the same frame is corrupt."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[float("nan"), 20.0, 100.0, 200.0], [10.0, 20.0, 100.0, 200.0]],
                conf=[0.90, 0.88],
                cls=[0, 0],
                names={0: "person"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0])
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (10, 20, 100, 200)
            worker.close()

    @pytest.mark.asyncio
    async def test_boolean_frame_dtype_rejected(self) -> None:
        """Verify that non-numeric (e.g. boolean) arrays return [] without predict call."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            bool_frame = np.zeros((100, 100, 3), dtype=bool)
            res = await worker.detect(bool_frame)

            assert res == []
            mock_model.predict.assert_not_called()
            worker.close()

    @pytest.mark.asyncio
    async def test_fallback_boxes_no_person_returns_empty_list(self) -> None:
        """Verify fallback box parsing returns [] when 0 in classes but no person detected."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            box_item = MagicMock()
            box_item.xyxy = [50.0, 60.0, 70.0, 80.0]
            box_item.conf = [0.85]
            box_item.cls = [2]

            mock_result = MagicMock()
            mock_result.boxes = [box_item]
            mock_result.names = {0: "person", 2: "car"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 2])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert detections == []
            worker.close()

    @pytest.mark.asyncio
    async def test_fallback_boxes_corrupt_box_skipped(self) -> None:
        """Verify corrupt fallback box is skipped with warning and valid box kept."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            box_corrupt = MagicMock()
            box_corrupt.xyxy = [float("nan"), 20.0, 30.0, 40.0]
            box_corrupt.conf = [0.90]
            box_corrupt.cls = [0]

            box_valid = MagicMock()
            box_valid.xyxy = [10.0, 20.0, 30.0, 40.0]
            box_valid.conf = [0.85]
            box_valid.cls = [0]

            mock_result = MagicMock()
            mock_result.boxes = [box_corrupt, box_valid]
            mock_result.names = {0: "person"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (10, 20, 30, 40)
            worker.close()

    @pytest.mark.asyncio
    async def test_concurrent_detect_calls_with_asyncio_gather(self) -> None:
        """Verify concurrent detect calls serialized properly without thread race conditions."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            call_count = 0

            def side_effect_predict(*args: Any, **kwargs: Any) -> list[Any]:
                nonlocal call_count
                call_count += 1
                mock_res = MagicMock()
                mock_boxes = MagicMock()
                mock_boxes.xyxy = [[call_count, 10, 50, 60]]
                mock_boxes.conf = [0.90]
                mock_boxes.cls = [0]
                mock_boxes.__len__ = MagicMock(return_value=1)
                mock_res.boxes = mock_boxes
                mock_res.names = {0: "person"}
                return [mock_res]

            mock_model.predict.side_effect = side_effect_predict
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((100, 100, 3), dtype=np.uint8)

            results = await asyncio.gather(*(worker.detect(frame) for _ in range(5)))

            assert len(results) == 5
            for r in results:
                assert len(r) == 1
                assert r[0].class_name == "person"
            worker.close()

    @pytest.mark.asyncio
    async def test_detections_below_confidence_threshold_filtered(self) -> None:
        """Verify that predictions below the configured confidence threshold are filtered out."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[
                    [10.0, 20.0, 100.0, 200.0],
                    [50.0, 60.0, 150.0, 250.0],
                ],
                conf=[0.55, 0.85],  # 0.55 is below confidence 0.70
                cls=[0, 0],
                names={0: "person"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(confidence=0.70)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (50, 60, 150, 250)
            assert detections[0].confidence == pytest.approx(0.85)
            worker.close()

    @pytest.mark.asyncio
    async def test_all_person_detections_below_confidence_returns_empty_list(self) -> None:
        """Verify that if all person detections are below confidence threshold, [] is returned."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            mock_result = self._create_mock_yolo_result(
                xyxy=[[10.0, 20.0, 100.0, 200.0]],
                conf=[0.40],
                cls=[0],
                names={0: "person"},
            )
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(confidence=0.60)
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert detections == []
            worker.close()

    @pytest.mark.asyncio
    async def test_fallback_boxes_below_confidence_filtered(self) -> None:
        """Verify fallback box parsing drops boxes below confidence threshold."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            box_low = MagicMock()
            box_low.xyxy = [10.0, 20.0, 30.0, 40.0]
            box_low.conf = [0.45]
            box_low.cls = [0]

            box_high = MagicMock()
            box_high.xyxy = [50.0, 60.0, 70.0, 80.0]
            box_high.conf = [0.85]
            box_high.cls = [0]

            mock_result = MagicMock()
            mock_result.boxes = [box_low, box_high]
            mock_result.names = {0: "person"}
            mock_model.predict.return_value = [mock_result]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(confidence=0.60)
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 1
            assert detections[0].box == (50, 60, 70, 80)
            worker.close()

    @pytest.mark.asyncio
    async def test_names_resolution_edge_cases(self) -> None:
        """Verify names dictionary with whitespace and list with out-of-bounds index."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            # Out of bounds class ID in names list
            mock_res_list = self._create_mock_yolo_result(
                xyxy=[[10.0, 20.0, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]],
                conf=[0.90, 0.85],
                cls=[0, 8],
                names=["person"],  # length 1, class 8 is out of bounds
            )
            mock_model.predict.return_value = [mock_res_list]
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker(classes=[0, 8])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            detections = await worker.detect(frame)

            assert len(detections) == 2
            assert detections[0].class_name == "person"
            assert detections[1].class_name == "class_8"
            worker.close()

        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()
            # Whitespace in names dict values
            mock_res_dict = self._create_mock_yolo_result(
                xyxy=[[10.0, 20.0, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]],
                conf=[0.90, 0.85],
                cls=[0, 2],
                names={0: "   ", 2: "  truck  "},
            )
            mock_model.predict.return_value = [mock_res_dict]
            mock_yolo_cls.return_value = mock_model

            worker2 = DetectorWorker(classes=[0, 2])
            detections2 = await worker2.detect(frame)

            assert len(detections2) == 2
            assert detections2[0].class_name == "person"  # fell back because "   " was blank
            assert detections2[1].class_name == "truck"  # stripped
            worker2.close()

    def test_raw_results_non_iterable_without_boxes(self) -> None:
        """Verify _parse_results gracefully handles raw results that are not iterable and have no boxes."""
        with patch("argus.core.detector.YOLO"):
            worker = DetectorWorker()
            assert worker._parse_results(12345) == []
            worker.close()


# ===========================================================================
# 5. Non-Blocking Event Loop Verification
# ===========================================================================


class TestDetectorAsyncNonBlocking:
    """
    Verify that inference runs in run_in_executor and does not block
    the main asyncio event loop.
    """

    @pytest.mark.asyncio
    async def test_async_executor_does_not_block_main_event_loop(self) -> None:
        """
        Assert that the async executor does not block the main event loop.

        We simulate a slow blocking prediction (100ms sleep in the thread).
        Concurrently, we run a lightweight asyncio task that ticks every 15ms.
        If the event loop were blocked by inference, the concurrent task would
        freeze and record 0 or 1 ticks. Since the executor offloads the work,
        the background task continues ticking smoothly (at least 4+ ticks).
        """
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_model = MagicMock()

            def slow_predict(*args: Any, **kwargs: Any) -> list[Any]:
                # Simulate CPU/GPU inference time in worker thread
                time.sleep(0.10)
                mock_res = MagicMock()
                mock_boxes = MagicMock()
                mock_boxes.xyxy = [[10.0, 20.0, 100.0, 200.0]]
                mock_boxes.conf = [0.90]
                mock_boxes.cls = [0]
                mock_boxes.__len__ = MagicMock(return_value=1)
                mock_res.boxes = mock_boxes
                mock_res.names = {0: "person"}
                return [mock_res]

            mock_model.predict.side_effect = slow_predict
            mock_yolo_cls.return_value = mock_model

            worker = DetectorWorker()
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

            event_loop_ticks = 0
            ticker_running = True

            async def ticker() -> None:
                nonlocal event_loop_ticks
                while ticker_running:
                    await asyncio.sleep(0.015)
                    event_loop_ticks += 1

            ticker_task = asyncio.create_task(ticker())

            try:
                detections = await worker.detect(frame)
            finally:
                ticker_running = False
                await ticker_task

            # Assert inference completed and parsed properly
            assert len(detections) == 1
            assert detections[0].box == (10, 20, 100, 200)

            # Assert event loop executed multiple times concurrently during inference
            # 100ms / 15ms ~= 6-7 ticks; at least 3 ticks proves non-blocking
            assert event_loop_ticks >= 3, (
                f"Event loop was blocked! Expected >=3 ticks during inference, got {event_loop_ticks}"
            )

            worker.close()


# ===========================================================================
# 6. Lifecycle & Teardown Tests
# ===========================================================================


class TestDetectorWorkerLifecycle:
    """Tests for resource cleanup and context management."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Verify DetectorWorker supports async with syntax."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            async with DetectorWorker() as worker:
                assert not worker._closed
            assert worker._closed

    def test_sync_context_manager(self) -> None:
        """Verify DetectorWorker supports synchronous with syntax."""
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            with DetectorWorker() as worker:
                assert not worker._closed
            assert worker._closed

    def test_custom_executor_not_closed(self) -> None:
        """Verify custom executor provided by caller is not shut down by close()."""
        custom_exec = ThreadPoolExecutor(max_workers=1)
        with patch("argus.core.detector.YOLO") as mock_yolo_cls:
            mock_yolo_cls.return_value = MagicMock()
            worker = DetectorWorker(executor=custom_exec)
            worker.close()

            # Custom executor should still be usable
            future = custom_exec.submit(lambda: 42)
            assert future.result() == 42

        custom_exec.shutdown(wait=False)
