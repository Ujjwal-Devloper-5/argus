"""
Unit tests for FaceRecognizer, FaceMatch, and InsightFace integration in argus.core.recognizer.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from pydantic import ValidationError

from argus.config.settings import RecognitionConfig, Settings
from argus.core.detector import Detection
from argus.core.recognizer import FaceMatch, FaceRecognizer, resolve_providers
from argus.intelligence.embeddings import EmbeddingDB


class MockInsightFaceFace:
    """Mock InsightFace detected face object."""

    def __init__(
        self,
        embedding: np.ndarray | None = None,
        bbox: tuple[float, float, float, float] = (10.0, 10.0, 60.0, 80.0),
    ) -> None:
        self.embedding = (
            embedding if embedding is not None else np.random.randn(512).astype(np.float32)
        )
        self.bbox = bbox


class MockInsightFaceApp:
    """Mock insightface.app.FaceAnalysis."""

    def __init__(self, default_faces: list[Any] | None = None) -> None:
        self.default_faces = default_faces
        self.prepare_called = False

    def prepare(self, ctx_id: int = 0, det_thresh: float = 0.5, det_size: Any = None) -> None:
        self.prepare_called = True

    def get(self, crop: np.ndarray) -> Any:
        if self.default_faces is not None:
            return self.default_faces
        # By default return one dummy face
        dummy_emb = np.ones(512, dtype=np.float32)
        dummy_emb /= np.linalg.norm(dummy_emb)
        return [MockInsightFaceFace(embedding=dummy_emb)]


class TestFaceMatchModel:
    """Test suite for strictly-typed FaceMatch Pydantic model."""

    def test_valid_creation(self) -> None:
        """Verify model creation with valid fields."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        emb = np.ones(512, dtype=np.float32)
        match = FaceMatch(
            detection=det,
            embedding=emb,
            similarity=0.85,
            is_known=True,
            profile_id=1,
        )
        assert match.detection == det
        assert isinstance(match.embedding, np.ndarray)
        assert len(match.embedding) == 512
        assert match.similarity == 0.85
        assert match.is_known is True
        assert match.profile_id == 1

    def test_no_face_detected_defaults(self) -> None:
        """Verify model representation when no face was detected."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        match = FaceMatch(
            detection=det,
            embedding=None,
            similarity=0.0,
            is_known=False,
            profile_id=None,
        )
        assert match.embedding is None
        assert match.similarity == 0.0
        assert match.is_known is False
        assert match.profile_id is None

    def test_embedding_from_sequence(self) -> None:
        """Verify validator converts list of floats into float32 numpy array."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        floats = [0.1] * 512
        match = FaceMatch(detection=det, embedding=floats)
        assert isinstance(match.embedding, np.ndarray)
        assert match.embedding.dtype == np.float32
        assert len(match.embedding) == 512

    def test_invalid_embedding_type_raises(self) -> None:
        """Verify passing non-numeric/non-sequence embedding raises ValidationError."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        with pytest.raises(ValidationError):
            FaceMatch(detection=det, embedding="invalid_string")  # type: ignore[arg-type]

    def test_model_immutability(self) -> None:
        """Verify FaceMatch is frozen and cannot be mutated."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        match = FaceMatch(detection=det, similarity=0.5)
        with pytest.raises(ValidationError):
            match.similarity = 0.9  # type: ignore[misc]

    def test_equality_with_numpy_arrays(self) -> None:
        """Verify custom __eq__ correctly compares numpy array embeddings without ambiguity errors."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        emb1 = np.ones(512, dtype=np.float32)
        emb2 = np.ones(512, dtype=np.float32)
        emb3 = np.zeros(512, dtype=np.float32)

        match1 = FaceMatch(
            detection=det, embedding=emb1, similarity=0.8, is_known=True, profile_id=1
        )
        match2 = FaceMatch(
            detection=det, embedding=emb2, similarity=0.8, is_known=True, profile_id=1
        )
        match3 = FaceMatch(
            detection=det, embedding=emb3, similarity=0.8, is_known=True, profile_id=1
        )
        match_none = FaceMatch(detection=det, embedding=None, similarity=0.0)

        assert match1 == match2
        assert match1 != match3
        assert match1 != match_none
        assert match1 != "not_a_facematch"

    def test_hashable_and_usable_in_sets(self) -> None:
        """Verify FaceMatch can be hashed and added to python sets."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        emb1 = np.ones(512, dtype=np.float32)
        emb2 = np.ones(512, dtype=np.float32)

        match1 = FaceMatch(detection=det, embedding=emb1, similarity=0.8, profile_id=1)
        match2 = FaceMatch(detection=det, embedding=emb2, similarity=0.8, profile_id=1)
        match3 = FaceMatch(detection=det, embedding=None, similarity=0.0)

        s = {match1, match2, match3}
        assert len(s) == 2
        assert match1 in s
        assert match3 in s


class TestProviderResolution:
    """Test safe ONNX/PyTorch provider auto-detection and CPU failover."""

    def test_cpu_failover_when_cuda_missing(self) -> None:
        """Verify failing over to CPUExecutionProvider when CUDA is not in available providers."""
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            resolved = resolve_providers(["CUDAExecutionProvider", "CPUExecutionProvider"])
            assert resolved == ["CPUExecutionProvider"]

    def test_cuda_retained_when_available(self) -> None:
        """Verify CUDAExecutionProvider is retained when present in available providers."""
        with patch(
            "onnxruntime.get_available_providers",
            return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
        ):
            resolved = resolve_providers(["CUDAExecutionProvider", "CPUExecutionProvider"])
            assert resolved == ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def test_default_providers_handling(self) -> None:
        """Verify default provider list when none specified."""
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            resolved = resolve_providers(None)
            assert resolved == ["CPUExecutionProvider"]

    def test_ort_query_exception_handled(self) -> None:
        """Verify exception during provider query safely defaults to CPU."""
        with patch("onnxruntime.get_available_providers", side_effect=RuntimeError("driver error")):
            resolved = resolve_providers()
            assert resolved == ["CPUExecutionProvider"]


class TestFaceRecognizer:
    """Test suite for FaceRecognizer inference and matching logic."""

    @pytest.fixture
    def test_frame(self) -> np.ndarray:
        """Create a dummy BGR video frame (height=480, width=640, channels=3)."""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    @pytest.fixture
    def enrolled_db(self) -> tuple[EmbeddingDB, np.ndarray]:
        """Create an EmbeddingDB with one enrolled profile."""
        db = EmbeddingDB()
        rng = np.random.default_rng(42)
        vec = rng.standard_normal(512).astype(np.float32)
        vec /= np.linalg.norm(vec)
        db.add(profile_id=10, embedding=vec)
        return db, vec

    def test_initialization_invalid_threshold(self) -> None:
        """Verify invalid similarity threshold raises ValueError."""
        with pytest.raises(ValueError, match="similarity_threshold"):
            FaceRecognizer(similarity_threshold=-0.1, app=MockInsightFaceApp())
        with pytest.raises(ValueError, match="similarity_threshold"):
            FaceRecognizer(similarity_threshold=1.5, app=MockInsightFaceApp())

    def test_from_config(self) -> None:
        """Verify from_config correctly extracts settings."""
        cfg = RecognitionConfig(similarity_threshold=0.75)
        rec = FaceRecognizer.from_config(cfg, app=MockInsightFaceApp())
        assert rec.similarity_threshold == 0.75
        rec.close()

    def test_from_config_invalid_type_raises(self) -> None:
        """Verify invalid config type raises TypeError."""
        with pytest.raises(TypeError, match="RecognitionConfig"):
            FaceRecognizer.from_config("not_a_config", app=MockInsightFaceApp())  # type: ignore[arg-type]

    async def test_empty_frame_returns_empty_list(self) -> None:
        """Verify passing an empty frame returns []."""
        rec = FaceRecognizer(app=MockInsightFaceApp())
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)

        res_none = await rec.recognize(None, [det])  # type: ignore[arg-type]
        assert res_none == []

        res_empty = await rec.recognize(np.zeros((0, 0, 3), dtype=np.uint8), [det])
        assert res_empty == []
        rec.close()

    async def test_empty_detections_returns_empty_list(self, test_frame: np.ndarray) -> None:
        """Verify passing empty detections returns []."""
        rec = FaceRecognizer(app=MockInsightFaceApp())
        res = await rec.recognize(test_frame, [])
        assert res == []
        rec.close()

    async def test_known_face_matched_successfully(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify enrolled face is recognized with high similarity and is_known=True."""
        db, known_vec = enrolled_db
        mock_app = MockInsightFaceApp(default_faces=[MockInsightFaceFace(embedding=known_vec)])
        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(50, 50, 150, 150), confidence=0.92)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        match = matches[0]
        assert match.detection == det
        assert match.is_known is True
        assert match.profile_id == 10
        assert pytest.approx(match.similarity, rel=1e-4) == 1.0
        assert match.embedding is not None
        rec.close()

    async def test_unknown_face_below_threshold(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify face with low similarity is flagged as is_known=False."""
        db, _ = enrolled_db

        # Orthogonal embedding
        ortho_vec = np.zeros(512, dtype=np.float32)
        ortho_vec[0] = 1.0

        mock_app = MockInsightFaceApp(default_faces=[MockInsightFaceFace(embedding=ortho_vec)])
        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(50, 50, 150, 150), confidence=0.88)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        match = matches[0]
        assert match.is_known is False
        assert match.similarity < 0.60
        rec.close()

    async def test_empty_database_handling(self, test_frame: np.ndarray) -> None:
        """Verify query against an empty database returns is_known=False and profile_id=None."""
        empty_db = EmbeddingDB()
        mock_app = MockInsightFaceApp()
        rec = FaceRecognizer(db=empty_db, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(20, 20, 80, 80), confidence=0.85)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        match = matches[0]
        assert match.is_known is False
        assert match.profile_id is None
        assert match.similarity == 0.0
        assert match.embedding is not None
        rec.close()

    async def test_none_database_handling(self, test_frame: np.ndarray) -> None:
        """Verify recognizer works when db=None (extracts embedding without DB lookup)."""
        mock_app = MockInsightFaceApp()
        rec = FaceRecognizer(db=None, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(20, 20, 80, 80), confidence=0.85)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        match = matches[0]
        assert match.is_known is False
        assert match.profile_id is None
        assert match.similarity == 0.0
        assert match.embedding is not None
        rec.close()

    async def test_no_face_found_in_crop(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify when InsightFace detects 0 faces in the crop, FaceMatch handles it gracefully."""
        db, _ = enrolled_db
        mock_app = MockInsightFaceApp(default_faces=[])  # Empty list of faces
        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(30, 30, 90, 90), confidence=0.80)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        match = matches[0]
        assert match.detection == det
        assert match.embedding is None
        assert match.similarity == 0.0
        assert match.is_known is False
        assert match.profile_id is None
        rec.close()

    async def test_direct_numpy_array_from_mock_app(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify handling mock app that returns a 512-dim numpy array directly."""
        db, known_vec = enrolled_db

        class DirectArrayMock:
            def get(self, crop: np.ndarray) -> np.ndarray:
                return known_vec

        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=DirectArrayMock())
        det = Detection(box=(10, 10, 60, 60), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].is_known is True
        assert matches[0].profile_id == 10
        rec.close()

    async def test_out_of_bounds_bounding_box(self, test_frame: np.ndarray) -> None:
        """Verify coordinates outside frame boundary are safely clipped or handled."""
        mock_app = MockInsightFaceApp()
        rec = FaceRecognizer(app=mock_app)

        # Partially out of bounds: frame is 480x640
        det_partial = Detection(box=(600, 450, 700, 550), confidence=0.9)
        # Completely out of bounds / degenerate
        det_degenerate = Detection(box=(700, 700, 700, 700), confidence=0.9)

        matches = await rec.recognize(test_frame, [det_partial, det_degenerate])
        assert len(matches) == 2
        # Degenerate crop produces empty match without error
        assert matches[1].embedding is None
        assert matches[1].similarity == 0.0
        rec.close()

    async def test_multiple_faces_selects_largest(self, test_frame: np.ndarray) -> None:
        """Verify when multiple faces are detected in a single crop, the largest is selected."""
        small_emb = np.zeros(512, dtype=np.float32)
        small_emb[0] = 1.0
        large_emb = np.zeros(512, dtype=np.float32)
        large_emb[1] = 1.0

        face_small = MockInsightFaceFace(
            embedding=small_emb, bbox=(10.0, 10.0, 20.0, 20.0)
        )  # area 100
        face_large = MockInsightFaceFace(
            embedding=large_emb, bbox=(10.0, 10.0, 60.0, 60.0)
        )  # area 2500

        mock_app = MockInsightFaceApp(default_faces=[face_small, face_large])
        rec = FaceRecognizer(app=mock_app)

        det = Detection(box=(0, 0, 100, 100), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, large_emb)
        rec.close()

    async def test_non_blocking_event_loop(self, test_frame: np.ndarray) -> None:
        """Verify slow InsightFace inference does not block the asyncio event loop."""

        class SlowMockApp:
            def get(self, crop: np.ndarray) -> list[Any]:
                time.sleep(0.12)  # Blocking sleep simulating heavy neural net inference
                return [MockInsightFaceFace()]

        rec = FaceRecognizer(app=SlowMockApp())
        det = Detection(box=(50, 50, 150, 150), confidence=0.9)

        ticker_ticks = 0

        async def concurrent_ticker() -> None:
            nonlocal ticker_ticks
            for _ in range(8):
                await asyncio.sleep(0.015)
                ticker_ticks += 1

        # Run inference and ticker concurrently
        results, _ = await asyncio.gather(
            rec.recognize(test_frame, [det]),
            concurrent_ticker(),
        )

        assert len(results) == 1
        # The ticker MUST have made progress while the blocking inference executed in thread pool
        assert ticker_ticks >= 3, f"Event loop was blocked: only {ticker_ticks} ticks executed"
        rec.close()

    async def test_context_manager_and_closed_error(self, test_frame: np.ndarray) -> None:
        """Verify async context manager closes executor and post-close calls raise RuntimeError."""
        mock_app = MockInsightFaceApp()
        async with FaceRecognizer(app=mock_app) as rec:
            det = Detection(box=(10, 10, 50, 50), confidence=0.9)
            res = await rec.recognize(test_frame, [det])
            assert len(res) == 1

        # After exiting context manager, recognizer is closed
        with pytest.raises(RuntimeError, match="closed"):
            await rec.recognize(test_frame, [det])

    def test_equality_different_detections(self) -> None:
        """Verify equality returns False when detections differ."""
        det1 = Detection(box=(10, 20, 30, 40), confidence=0.9)
        det2 = Detection(box=(50, 60, 70, 80), confidence=0.9)
        match1 = FaceMatch(detection=det1, similarity=0.8)
        match2 = FaceMatch(detection=det2, similarity=0.8)
        assert match1 != match2

    def test_equality_one_embedding_none(self) -> None:
        """Verify equality returns False when one embedding is None."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.9)
        match1 = FaceMatch(detection=det, embedding=np.ones(512, dtype=np.float32))
        match2 = FaceMatch(detection=det, embedding=None)
        assert match1 != match2

    def test_initialization_with_faceanalysis_mock(self) -> None:
        """Verify FaceRecognizer initializes FaceAnalysis when app is None."""
        mock_fa_instance = MockInsightFaceApp()
        with patch("argus.core.recognizer.FaceAnalysis", return_value=mock_fa_instance):
            rec = FaceRecognizer(app=None, model_name="buffalo_l")
            assert rec.app == mock_fa_instance
            assert mock_fa_instance.prepare_called is True
            rec.close()

    def test_missing_insightface_raises_importerror(self) -> None:
        """Verify initializing without app raises ImportError if insightface is missing."""
        with (
            patch("argus.core.recognizer.FaceAnalysis", None),
            pytest.raises(ImportError, match="insightface is required"),
        ):
            FaceRecognizer(app=None)

    async def test_app_exception_during_inference(self, test_frame: np.ndarray) -> None:
        """Verify exceptions during app.get() are logged and return FaceMatch with None embedding."""

        class FailingApp:
            def get(self, crop: np.ndarray) -> Any:
                raise RuntimeError("inference engine crash")

        rec = FaceRecognizer(app=FailingApp())
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])
        assert len(matches) == 1
        assert matches[0].embedding is None
        rec.close()

    async def test_app_returns_none(self, test_frame: np.ndarray) -> None:
        """Verify app returning None produces match with embedding=None."""

        class NoneApp:
            def get(self, crop: np.ndarray) -> Any:
                return None

        rec = FaceRecognizer(app=NoneApp())
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])
        assert len(matches) == 1
        assert matches[0].embedding is None
        rec.close()

    async def test_app_returns_list_of_arrays(self, test_frame: np.ndarray) -> None:
        """Verify app returning a list of numpy arrays is handled properly."""
        emb = np.ones(512, dtype=np.float32)
        mock_app = MockInsightFaceApp(default_faces=[emb])
        rec = FaceRecognizer(app=mock_app)
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])
        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, emb)
        rec.close()

    async def test_app_returns_list_of_dicts(self, test_frame: np.ndarray) -> None:
        """Verify app returning dicts with 'embedding' key is handled properly."""
        emb = np.ones(512, dtype=np.float32)
        mock_app = MockInsightFaceApp(default_faces=[{"embedding": emb}])
        rec = FaceRecognizer(app=mock_app)
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])
        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, emb)
        rec.close()

    def test_facematch_nan_inf_embedding_rejected(self) -> None:
        """Verify FaceMatch rejects embeddings containing NaN or Inf."""
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        nan_emb = np.ones(512, dtype=np.float32)
        nan_emb[0] = float("nan")
        with pytest.raises(ValueError, match="NaN or Inf"):
            FaceMatch(detection=det, embedding=nan_emb)

        inf_emb = np.ones(512, dtype=np.float32)
        inf_emb[0] = float("inf")
        with pytest.raises(ValueError, match="NaN or Inf"):
            FaceMatch(detection=det, embedding=inf_emb)

    def test_facematch_negative_zero_hash_consistency(self) -> None:
        """Verify -0.0 and 0.0 in embeddings satisfy hash and equality invariants."""
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        emb_zero = np.zeros(512, dtype=np.float32)
        emb_neg_zero = np.zeros(512, dtype=np.float32)
        emb_neg_zero[0] = -0.0

        match1 = FaceMatch(
            detection=det, embedding=emb_zero, similarity=0.8, is_known=True, profile_id=1
        )
        match2 = FaceMatch(
            detection=det, embedding=emb_neg_zero, similarity=0.8, is_known=True, profile_id=1
        )

        assert match1 == match2
        assert hash(match1) == hash(match2)
        assert len({match1, match2}) == 1

    async def test_unknown_face_sets_profile_id_none(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify that when a face is below similarity threshold, profile_id is None."""
        db, _ = enrolled_db
        ortho_vec = np.zeros(512, dtype=np.float32)
        ortho_vec[0] = 1.0

        mock_app = MockInsightFaceApp(default_faces=[MockInsightFaceFace(embedding=ortho_vec)])
        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=mock_app)

        det = Detection(box=(50, 50, 150, 150), confidence=0.88)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].is_known is False
        assert matches[0].profile_id is None
        assert matches[0].similarity < 0.60
        rec.close()

    async def test_multiple_faces_first_face_none_embedding(self, test_frame: np.ndarray) -> None:
        """Verify recognizer extracts embedding from face 1 when face 0 has None embedding."""
        from types import SimpleNamespace

        valid_emb = np.ones(512, dtype=np.float32)
        mock_faces = [
            SimpleNamespace(bbox=[0, 0, 20, 20], embedding=None),
            SimpleNamespace(bbox=[0, 0, 100, 100], embedding=valid_emb),
        ]
        mock_app = MockInsightFaceApp(default_faces=mock_faces)
        rec = FaceRecognizer(app=mock_app)

        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, valid_emb)
        rec.close()

    async def test_multiple_faces_prefers_largest_valid_face(self, test_frame: np.ndarray) -> None:
        """Verify recognizer chooses largest face among those with valid embeddings."""
        from types import SimpleNamespace

        emb_small = np.full(512, 1.0, dtype=np.float32)
        emb_large = np.full(512, 2.0, dtype=np.float32)

        mock_faces = [
            SimpleNamespace(bbox=[0, 0, 500, 500], embedding=None),  # Largest, but invalid
            SimpleNamespace(bbox=[0, 0, 200, 200], embedding=emb_large),  # Valid large
            SimpleNamespace(bbox=[0, 0, 50, 50], embedding=emb_small),  # Valid small
        ]
        mock_app = MockInsightFaceApp(default_faces=mock_faces)
        rec = FaceRecognizer(app=mock_app)

        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, emb_large)
        rec.close()

    async def test_normed_embedding_fallback(self, test_frame: np.ndarray) -> None:
        """Verify recognizer falls back to normed_embedding if embedding is None."""
        from types import SimpleNamespace

        emb_normed = np.ones(512, dtype=np.float32)
        mock_faces = [
            SimpleNamespace(bbox=[0, 0, 50, 50], embedding=None, normed_embedding=emb_normed)
        ]
        mock_app = MockInsightFaceApp(default_faces=mock_faces)
        rec = FaceRecognizer(app=mock_app)

        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert np.array_equal(matches[0].embedding, emb_normed)
        rec.close()

    async def test_grayscale_and_rgba_frames_handled(self) -> None:
        """Verify recognizer handles 2D grayscale and 4-channel RGBA frames."""
        valid_emb = np.ones(512, dtype=np.float32)
        mock_app = MockInsightFaceApp(default_faces=[valid_emb])
        rec = FaceRecognizer(app=mock_app)

        # Grayscale 2D frame
        gray_frame = np.full((200, 200), 128, dtype=np.uint8)
        det = Detection(box=(10, 10, 80, 80), confidence=0.9)
        matches_gray = await rec.recognize(gray_frame, [det])
        assert len(matches_gray) == 1
        assert matches_gray[0].embedding is not None

        # 4-channel RGBA frame
        rgba_frame = np.full((200, 200, 4), 200, dtype=np.uint8)
        matches_rgba = await rec.recognize(rgba_frame, [det])
        assert len(matches_rgba) == 1
        assert matches_rgba[0].embedding is not None
        rec.close()

    def test_facematch_pydantic_serialization_roundtrip(self) -> None:
        """Verify FaceMatch correctly serializes to JSON and roundtrips without errors."""
        det = Detection(box=(10, 20, 50, 60), confidence=0.92, class_name="person")
        emb = np.ones(512, dtype=np.float32) * 0.5
        match = FaceMatch(
            detection=det,
            embedding=emb,
            similarity=0.88,
            is_known=True,
            profile_id=42,
        )

        # 1. model_dump python mode returns np.ndarray
        dump_py = match.model_dump()
        assert isinstance(dump_py["embedding"], np.ndarray)
        assert np.array_equal(dump_py["embedding"], emb)

        # 2. model_dump json mode returns list[float]
        dump_json = match.model_dump(mode="json")
        assert isinstance(dump_json["embedding"], list)
        assert len(dump_json["embedding"]) == 512

        # 3. model_dump_json returns valid JSON string
        json_str = match.model_dump_json()
        assert isinstance(json_str, str)
        assert '"is_known":true' in json_str
        assert '"profile_id":42' in json_str

        # 4. Deserialization round-trip recreates identical FaceMatch with matching hash
        restored = FaceMatch.model_validate_json(json_str)
        assert restored == match
        assert hash(restored) == hash(match)
        assert isinstance(restored.embedding, np.ndarray)
        assert restored.embedding.dtype == np.float32

    def test_facematch_none_embedding_serialization_roundtrip(self) -> None:
        """Verify undetected face (embedding=None) serializes and deserializes properly."""
        det = Detection(box=(10, 20, 50, 60), confidence=0.75, class_name="person")
        match = FaceMatch(
            detection=det,
            embedding=None,
            similarity=0.0,
            is_known=False,
            profile_id=None,
        )

        json_str = match.model_dump_json()
        restored = FaceMatch.model_validate_json(json_str)
        assert restored == match
        assert hash(restored) == hash(match)
        assert restored.embedding is None

    def test_facematch_rejects_wrong_dimension_embedding(self) -> None:
        """Verify FaceMatch rejects embeddings that are not 512-dimensional."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        with pytest.raises(ValidationError, match="dimension 512"):
            FaceMatch(detection=det, embedding=np.ones(128, dtype=np.float32))

        with pytest.raises(ValidationError, match="dimension 512"):
            FaceMatch(detection=det, embedding=[0.1] * 256)

    def test_facematch_consistency_validation(self) -> None:
        """Verify logical consistency checks on is_known, profile_id, and embedding."""
        det = Detection(box=(10, 20, 30, 40), confidence=0.90)
        emb = np.ones(512, dtype=np.float32)

        # is_known cannot be True without profile_id
        with pytest.raises(ValidationError, match="profile_id is None"):
            FaceMatch(detection=det, embedding=emb, is_known=True, profile_id=None)

        # is_known cannot be True without embedding
        with pytest.raises(ValidationError, match="embedding is None"):
            FaceMatch(detection=det, embedding=None, is_known=True, profile_id=1)

    def test_from_config_with_settings_and_dict(self) -> None:
        """Verify FaceRecognizer.from_config supports Settings, dicts, and RecognitionConfig."""
        mock_app = MockInsightFaceApp()
        settings = Settings()

        # From Settings instance
        rec1 = FaceRecognizer.from_config(settings, app=mock_app)
        assert rec1.similarity_threshold == settings.recognition.similarity_threshold
        rec1.close()

        # From dict
        rec2 = FaceRecognizer.from_config({"similarity_threshold": 0.85}, app=mock_app)
        assert rec2.similarity_threshold == 0.85
        rec2.close()

        # Invalid type raises TypeError
        with pytest.raises(TypeError, match="RecognitionConfig"):
            FaceRecognizer.from_config(12345, app=mock_app)  # type: ignore[arg-type]

    def test_recognizer_rejects_boolean_similarity_threshold(self) -> None:
        """Verify boolean similarity_threshold is rejected."""
        mock_app = MockInsightFaceApp()
        with pytest.raises(ValueError, match="similarity_threshold"):
            FaceRecognizer(similarity_threshold=True, app=mock_app)  # type: ignore[arg-type]

    def test_recognizer_sync_and_async_context_manager(self) -> None:
        """Verify FaceRecognizer works with both sync and async context managers and stop()."""
        mock_app = MockInsightFaceApp()

        with FaceRecognizer(app=mock_app) as rec_sync:
            assert not rec_sync._closed
        assert rec_sync._closed

    async def test_recognizer_async_lifecycle(self) -> None:
        """Verify FaceRecognizer async context manager and stop() method."""
        mock_app = MockInsightFaceApp()

        async with FaceRecognizer(app=mock_app) as rec_async:
            assert not rec_async._closed
        assert rec_async._closed

        # Explicit stop
        rec3 = FaceRecognizer(app=mock_app)
        assert not rec3._closed
        await rec3.stop()
        assert rec3._closed

    async def test_recognizer_handles_invalid_dim_frames(self) -> None:
        """Verify recognizer gracefully handles 1D and >3D frames by returning empty list."""
        mock_app = MockInsightFaceApp()
        rec = FaceRecognizer(app=mock_app)
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)

        # 1D array
        res_1d = await rec.recognize(np.array([1, 2, 3], dtype=np.uint8), [det])
        assert res_1d == []

        # 4D array
        res_4d = await rec.recognize(np.zeros((1, 100, 100, 3), dtype=np.uint8), [det])
        assert res_4d == []
        rec.close()

    async def test_recognizer_handles_2d_embedding_in_face_object(
        self, test_frame: np.ndarray
    ) -> None:
        """Verify recognizer handles face objects where embedding has shape (1, 512)."""
        from types import SimpleNamespace

        emb_2d = np.ones((1, 512), dtype=np.float32)
        mock_faces = [SimpleNamespace(bbox=[0, 0, 50, 50], embedding=emb_2d)]
        mock_app = MockInsightFaceApp(default_faces=mock_faces)
        rec = FaceRecognizer(app=mock_app)

        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is not None
        assert matches[0].embedding.shape == (512,)
        rec.close()

    async def test_nan_embedding_from_insightface_does_not_crash(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """Verify InsightFace returning NaN/Inf embeddings does not crash the recognizer."""
        db, _ = enrolled_db

        class NanMockApp:
            def prepare(self, **kwargs: Any) -> None:
                pass

            def get(self, crop: np.ndarray) -> Any:
                from types import SimpleNamespace

                nan_emb = np.full(512, np.nan, dtype=np.float32)
                return [SimpleNamespace(bbox=[0, 0, 50, 50], embedding=nan_emb)]

        rec = FaceRecognizer(db=db, app=NanMockApp())
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        matches = await rec.recognize(test_frame, [det])

        assert len(matches) == 1
        assert matches[0].embedding is None
        assert matches[0].is_known is False
        assert matches[0].profile_id is None
        rec.close()

    async def test_rgba_crop_contiguity_and_extraction(self) -> None:
        """Verify 4-channel RGBA frame yields C-contiguous 3-channel crop for InsightFace."""
        captured_crops: list[np.ndarray] = []

        class ContiguityCaptureApp:
            def prepare(self, **kwargs: Any) -> None:
                pass

            def get(self, crop: np.ndarray) -> Any:
                captured_crops.append(crop)
                return np.ones(512, dtype=np.float32)

        rec = FaceRecognizer(app=ContiguityCaptureApp())
        rgba_frame = np.zeros((100, 100, 4), dtype=np.uint8)
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)

        matches = await rec.recognize(rgba_frame, [det])
        assert len(matches) == 1
        assert len(captured_crops) == 1
        crop = captured_crops[0]
        assert crop.ndim == 3
        assert crop.shape[2] == 3
        assert crop.flags.c_contiguous is True
        rec.close()

    async def test_float_frame_normalization_to_uint8(self) -> None:
        """Verify float32 frames are safely scaled to uint8 before model execution."""
        captured_crops: list[np.ndarray] = []

        class DtypeCaptureApp:
            def prepare(self, **kwargs: Any) -> None:
                pass

            def get(self, crop: np.ndarray) -> Any:
                captured_crops.append(crop)
                return np.ones(512, dtype=np.float32)

        rec = FaceRecognizer(app=DtypeCaptureApp())
        float_frame = np.ones((100, 100, 3), dtype=np.float32) * 0.5
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)

        matches = await rec.recognize(float_frame, [det])
        assert len(matches) == 1
        assert len(captured_crops) == 1
        crop = captured_crops[0]
        assert crop.dtype == np.uint8
        assert crop.flags.c_contiguous is True
        rec.close()

    async def test_non_numeric_frame_rejected(self) -> None:
        """Verify non-numeric frame dtypes are safely rejected without raising."""
        rec = FaceRecognizer(app=MockInsightFaceApp())
        obj_frame = np.array([["bad", "data"], ["more", "bad"]], dtype=object)
        det = Detection(box=(0, 0, 1, 1), confidence=0.9)

        matches = await rec.recognize(obj_frame, [det])
        assert matches == []
        rec.close()

    async def test_motion_blur_and_mixed_multi_detection_frame(
        self, test_frame: np.ndarray, enrolled_db: tuple[EmbeddingDB, np.ndarray]
    ) -> None:
        """
        Verify handling of 5 mixed detections in a single frame:
        1. Motion blurred face (0 faces detected in crop)
        2. Known enrolled face (similarity > threshold)
        3. Unknown face (similarity < threshold)
        4. Degenerate zero-area bounding box
        5. Out-of-bounds bounding box
        """
        db, enrolled_vec = enrolled_db
        ortho_vec = np.zeros(512, dtype=np.float32)
        ortho_vec[0] = 1.0

        call_count = 0

        class MixedMockApp:
            def prepare(self, **kwargs: Any) -> None:
                pass

            def get(self, crop: np.ndarray) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Crop 1: motion blurred (0 faces detected)
                    return []
                elif call_count == 2:
                    # Crop 2: known face
                    return [MockInsightFaceFace(embedding=enrolled_vec)]
                else:
                    # Crop 3: unknown face (orthogonal)
                    return [MockInsightFaceFace(embedding=ortho_vec)]

        rec = FaceRecognizer(db=db, similarity_threshold=0.60, app=MixedMockApp())

        dets = [
            Detection(box=(10, 10, 50, 50), confidence=0.9, track_id=1),  # Blur
            Detection(box=(60, 10, 100, 50), confidence=0.95, track_id=2),  # Known
            Detection(box=(110, 10, 150, 50), confidence=0.85, track_id=3),  # Unknown
            Detection(box=(200, 200, 200, 200), confidence=0.5, track_id=4),  # Zero area
            Detection(box=(9000, 9000, 9500, 9500), confidence=0.5, track_id=5),  # Out of frame
        ]

        matches = await rec.recognize(test_frame, dets)
        assert len(matches) == 5

        # 1. Motion blur
        assert matches[0].detection == dets[0]
        assert matches[0].embedding is None
        assert matches[0].is_known is False
        assert matches[0].profile_id is None

        # 2. Known
        assert matches[1].detection == dets[1]
        assert matches[1].embedding is not None
        assert matches[1].is_known is True
        assert matches[1].profile_id == 10
        assert matches[1].similarity > 0.60

        # 3. Unknown
        assert matches[2].detection == dets[2]
        assert matches[2].embedding is not None
        assert matches[2].is_known is False
        assert matches[2].profile_id is None
        assert matches[2].similarity < 0.60

        # 4. Zero area
        assert matches[3].detection == dets[3]
        assert matches[3].embedding is None
        assert matches[3].is_known is False

        # 5. Out of frame
        assert matches[4].detection == dets[4]
        assert matches[4].embedding is None
        assert matches[4].is_known is False

        # Verify JSON roundtrip preserves all 5 matches including track_ids
        for m in matches:
            json_data = m.model_dump_json()
            restored = FaceMatch.model_validate_json(json_data)
            assert restored == m
            assert restored.detection.track_id == m.detection.track_id

        rec.close()

    def test_facematch_detection_track_id_preserved_in_json(self) -> None:
        """Verify Detection track_id is preserved when serializing FaceMatch to JSON."""
        det = Detection(
            box=(10, 20, 30, 40),
            confidence=0.9,
            class_name="person",
            track_id=77,
        )
        match = FaceMatch(
            detection=det,
            embedding=None,
            similarity=0.0,
            is_known=False,
            profile_id=None,
        )

        # Python dump
        py_dump = match.model_dump()
        assert py_dump["detection"]["track_id"] == 77

        # JSON string dump
        json_str = match.model_dump_json()
        assert '"track_id":77' in json_str

        # Roundtrip validation
        restored = FaceMatch.model_validate_json(json_str)
        assert restored.detection.track_id == 77
        assert restored == match

    async def test_concurrent_recognize_calls(self, test_frame: np.ndarray) -> None:
        """Verify concurrent recognize calls are safely handled without race conditions."""
        rec = FaceRecognizer(app=MockInsightFaceApp())
        dets = [Detection(box=(10, 10, 50, 50), confidence=0.9)]

        tasks = [rec.recognize(test_frame, dets) for _ in range(15)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 15
        for res in results:
            assert len(res) == 1
            assert res[0].embedding is not None

        rec.close()
