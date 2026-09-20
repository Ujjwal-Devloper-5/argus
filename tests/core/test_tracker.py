"""
Unit tests for SortTracker and KalmanBoxTracker in argus.core.tracker.
"""

from __future__ import annotations

import numpy as np
import pytest

from argus.core.detector import Detection
from argus.core.tracker import KalmanBoxTracker, SortTracker, compute_iou


class TestIoUComputation:
    """Test bounding box IoU calculation."""

    def test_identical_boxes(self) -> None:
        """Verify identical boxes yield IoU of 1.0."""
        box = [10, 10, 50, 50]
        assert compute_iou(box, box) == 1.0

    def test_completely_disjoint_boxes(self) -> None:
        """Verify non-overlapping boxes yield IoU of 0.0."""
        box1 = [0, 0, 10, 10]
        box2 = [20, 20, 30, 30]
        assert compute_iou(box1, box2) == 0.0

    def test_partial_overlap(self) -> None:
        """Verify partially overlapping boxes calculate exact IoU."""
        box1 = [0, 0, 20, 20]  # area = 400
        box2 = [10, 0, 30, 20]  # area = 400, intersection = 10 * 20 = 200
        # union = 400 + 400 - 200 = 600, IoU = 200 / 600 = 1/3
        assert pytest.approx(compute_iou(box1, box2), rel=1e-4) == 1.0 / 3.0

    def test_zero_area_boxes(self) -> None:
        """Verify degenerate zero-area boxes yield IoU of 0.0."""
        box1 = [10, 10, 10, 10]
        box2 = [10, 10, 20, 20]
        assert compute_iou(box1, box2) == 0.0

    def test_inverted_coordinates(self) -> None:
        """Verify inverted coordinates yield IoU of 0.0."""
        box1 = [50, 50, 10, 10]
        box2 = [10, 10, 50, 50]
        assert compute_iou(box1, box2) == 0.0


class TestKalmanBoxTracker:
    """Test KalmanBoxTracker state estimation and prediction."""

    def test_initialization(self) -> None:
        """Verify tracker starts with correct id, hits, and valid state."""
        trk = KalmanBoxTracker(bbox=[10, 20, 50, 80], track_id=42, class_name="person")
        assert trk.id == 42
        assert trk.class_name == "person"
        assert trk.hits == 1
        assert trk.time_since_update == 0
        state = trk.get_state()
        assert len(state) == 4
        assert pytest.approx(state[0], abs=1.0) == 10.0
        assert pytest.approx(state[1], abs=1.0) == 20.0
        assert pytest.approx(state[2], abs=1.0) == 50.0
        assert pytest.approx(state[3], abs=1.0) == 80.0

    def test_predict_and_update(self) -> None:
        """Verify predict advances time and update incorporates new observation."""
        trk = KalmanBoxTracker(bbox=[10, 10, 50, 50], track_id=1)
        pred = trk.predict()
        assert trk.time_since_update == 1
        assert trk.age == 1
        assert len(pred) == 4

        trk.update([12, 11, 52, 51])
        assert trk.time_since_update == 0
        assert trk.hits == 2


class TestSortTracker:
    """Test SORT tracking lifecycle and multi-object association."""

    def test_initialization_defaults(self) -> None:
        """Verify default parameters."""
        tracker = SortTracker()
        assert tracker.max_age == 30
        assert tracker.iou_threshold == 0.3
        assert tracker.active_tracks_count == 0

    def test_initialization_invalid_params(self) -> None:
        """Verify parameter bounds checking."""
        with pytest.raises(ValueError, match="max_age"):
            SortTracker(max_age=0)
        with pytest.raises(ValueError, match="iou_threshold"):
            SortTracker(iou_threshold=-0.1)
        with pytest.raises(ValueError, match="iou_threshold"):
            SortTracker(iou_threshold=1.5)

    def test_empty_detections(self) -> None:
        """Verify empty detections list returns empty list."""
        tracker = SortTracker()
        assert tracker.update([]) == []

    def test_single_object_tracking_continuity(self) -> None:
        """Verify a moving object maintains the same track_id across frames."""
        tracker = SortTracker()

        det_frame1 = Detection(box=(100, 100, 200, 250), confidence=0.90)
        results1 = tracker.update([det_frame1])
        assert len(results1) == 1
        track_id1 = results1[0].track_id
        assert track_id1 is not None

        # Slightly shifted position in next frame (high IoU)
        det_frame2 = Detection(box=(104, 102, 204, 252), confidence=0.88)
        results2 = tracker.update([det_frame2])
        assert len(results2) == 1
        assert results2[0].track_id == track_id1
        assert results2[0].box == (104, 102, 204, 252)
        assert results2[0].confidence == 0.88

        # Third frame
        det_frame3 = Detection(box=(108, 105, 208, 255), confidence=0.92)
        results3 = tracker.update([det_frame3])
        assert len(results3) == 1
        assert results3[0].track_id == track_id1

    def test_multiple_objects_distinct_track_ids(self) -> None:
        """Verify multiple separate objects receive distinct track IDs."""
        tracker = SortTracker()

        det_a = Detection(box=(10, 10, 50, 50), confidence=0.9)
        det_b = Detection(box=(300, 300, 400, 400), confidence=0.9)

        results1 = tracker.update([det_a, det_b])
        assert len(results1) == 2
        id_a = results1[0].track_id
        id_b = results1[1].track_id
        assert id_a is not None and id_b is not None
        assert id_a != id_b

        # Next frame
        det_a2 = Detection(box=(12, 11, 52, 51), confidence=0.91)
        det_b2 = Detection(box=(302, 301, 402, 401), confidence=0.89)

        results2 = tracker.update([det_a2, det_b2])
        assert len(results2) == 2
        assert results2[0].track_id == id_a
        assert results2[1].track_id == id_b

    def test_track_persistence_across_missed_frame(self) -> None:
        """Verify track survives a temporary occlusion (empty detection frame)."""
        tracker = SortTracker(max_age=5)

        det1 = Detection(box=(50, 50, 100, 100), confidence=0.9)
        res1 = tracker.update([det1])
        initial_id = res1[0].track_id

        # Person is occluded / detector missed person for 2 frames
        res_empty1 = tracker.update([])
        assert res_empty1 == []
        res_empty2 = tracker.update([])
        assert res_empty2 == []

        # Person reappears close to predicted position
        det_reappear = Detection(box=(54, 52, 104, 102), confidence=0.85)
        res_reappear = tracker.update([det_reappear])
        assert len(res_reappear) == 1
        assert res_reappear[0].track_id == initial_id

    def test_track_expiration_after_max_age(self) -> None:
        """Verify track is removed when unobserved for more than max_age frames."""
        tracker = SortTracker(max_age=2)

        det1 = Detection(box=(50, 50, 100, 100), confidence=0.9)
        res1 = tracker.update([det1])
        initial_id = res1[0].track_id

        # 3 empty frames (> max_age=2)
        tracker.update([])
        tracker.update([])
        tracker.update([])
        assert tracker.active_tracks_count == 0

        # Detection appears again — should be assigned a new track ID
        det2 = Detection(box=(50, 50, 100, 100), confidence=0.9)
        res2 = tracker.update([det2])
        assert len(res2) == 1
        assert res2[0].track_id != initial_id

    def test_class_isolation_prevents_id_stealing(self) -> None:
        """Verify tracks with different class names do not match even if boxes overlap."""
        tracker = SortTracker()

        det_person = Detection(box=(100, 100, 200, 200), class_name="person", confidence=0.9)
        res1 = tracker.update([det_person])
        person_id = res1[0].track_id

        # Overlapping box but class is car
        det_car = Detection(box=(100, 100, 200, 200), class_name="car", confidence=0.9)
        res2 = tracker.update([det_car])
        assert len(res2) == 1
        assert res2[0].track_id != person_id

    def test_reset(self) -> None:
        """Verify reset clears all trackers and resets ID counter."""
        tracker = SortTracker()
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        tracker.update([det])
        assert tracker.active_tracks_count == 1

        tracker.reset()
        assert tracker.active_tracks_count == 0

        # Next detection gets track ID 1
        res = tracker.update([det])
        assert res[0].track_id == 1

    def test_class_isolation_with_zero_iou_threshold(self) -> None:
        """Verify class mismatch never allows track ID stealing even when iou_threshold is 0.0."""
        tracker = SortTracker(iou_threshold=0.0)
        det_person = Detection(box=(100, 100, 200, 200), class_name="person", confidence=0.9)
        res1 = tracker.update([det_person])
        person_id = res1[0].track_id

        det_car = Detection(box=(100, 100, 200, 200), class_name="car", confidence=0.9)
        res2 = tracker.update([det_car])
        assert len(res2) == 1
        assert res2[0].track_id != person_id

    def test_disjoint_objects_not_matched_with_zero_iou_threshold(self) -> None:
        """Verify completely disjoint boxes never match even when iou_threshold is 0.0."""
        tracker = SortTracker(iou_threshold=0.0)
        det1 = Detection(box=(0, 0, 10, 10), confidence=0.9)
        res1 = tracker.update([det1])
        id1 = res1[0].track_id

        # Far away detection with 0 IoU
        det2 = Detection(box=(500, 500, 600, 600), confidence=0.9)
        res2 = tracker.update([det2])
        assert len(res2) == 1
        assert res2[0].track_id != id1

    def test_tracker_nan_state_purged(self) -> None:
        """Verify tracker whose state becomes NaN is purged and does not corrupt tracking."""
        tracker = SortTracker()
        det = Detection(box=(100, 100, 200, 200), confidence=0.9)
        res = tracker.update([det])
        assert len(res) == 1

        # Corrupt the active tracker's state with NaNs
        tracker.trackers[0].x[2] = float("nan")
        assert not tracker.trackers[0].is_valid()

        # On next update, corrupted tracker should be dropped and new detection gets new ID
        res2 = tracker.update([det])
        assert len(res2) == 1
        assert res2[0].track_id != res[0].track_id

    def test_empty_frame_purges_corrupted_tracker(self) -> None:
        """Verify empty detections frame purges corrupted NaN tracker."""
        tracker = SortTracker()
        det = Detection(box=(100, 100, 200, 200), confidence=0.9)
        tracker.update([det])
        assert tracker.active_tracks_count == 1

        tracker.trackers[0].x[0] = float("nan")
        tracker.update([])
        assert tracker.active_tracks_count == 0

    def test_kalman_filter_extreme_aspect_ratio_and_jitter(self) -> None:
        """Verify alternating extreme aspect ratio jitter does not diverge or produce NaNs."""
        trk = KalmanBoxTracker(bbox=[10, 10, 12, 1000], track_id=1)
        for i in range(20):
            box = [10, 10, 1000, 12] if i % 2 == 0 else [10, 10, 12, 1000]
            trk.predict()
            trk.update(box)
            state = trk.get_state()
            assert not np.any(np.isnan(state))
            assert not np.any(np.isinf(state))
            assert trk.is_valid()

    def test_covariance_symmetry_maintained(self) -> None:
        """Verify covariance matrix P remains strictly symmetric after repeated updates."""
        trk = KalmanBoxTracker(bbox=[50, 50, 150, 150], track_id=1)
        for _ in range(50):
            trk.predict()
            trk.update([51, 52, 151, 152])
        assert np.allclose(trk.P, trk.P.T, atol=1e-10)

    def test_identical_overlapping_detections_maintain_distinct_tracks(self) -> None:
        """Verify dozens of identical overlapping detections receive distinct IDs and preserve them."""
        tracker = SortTracker()
        dets = [Detection(box=(100, 100, 200, 200), confidence=0.9) for _ in range(20)]
        res1 = tracker.update(dets)
        ids1 = [d.track_id for d in res1]
        assert len(set(ids1)) == 20

        # Next frame
        res2 = tracker.update(dets)
        ids2 = [d.track_id for d in res2]
        assert len(set(ids2)) == 20
        assert set(ids1) == set(ids2)

    def test_sort_tracker_initial_id_validation(self) -> None:
        """Verify initial_id validation in SortTracker."""
        with pytest.raises(ValueError, match="initial_id must be >= 1"):
            SortTracker(initial_id=0)

        with pytest.raises(ValueError, match="initial_id must be >= 1"):
            SortTracker(initial_id=-1)

        tracker = SortTracker(initial_id=100)
        det = Detection(box=(10, 10, 50, 50), confidence=0.9)
        res = tracker.update([det])
        assert res[0].track_id == 100

    def test_compute_iou_with_non_finite_inputs(self) -> None:
        """Verify compute_iou safely returns 0.0 on NaN, Inf, or truncated inputs."""
        from argus.core.tracker import compute_iou

        assert compute_iou([float("nan"), 0, 10, 10], [0, 0, 10, 10]) == 0.0
        assert compute_iou([0, 0, 10, 10], [float("nan"), 0, 10, 10]) == 0.0
        assert compute_iou([float("inf"), 0, 10, 10], [0, 0, 10, 10]) == 0.0
        assert compute_iou([0, 0, 10, 10], [0, 0, float("inf"), 10]) == 0.0
        assert compute_iou([0, 0], [0, 0, 10, 10]) == 0.0
        assert compute_iou([0, 0, 10, 10], [0, 0]) == 0.0

    def test_convert_bbox_to_z_with_non_finite_inputs(self) -> None:
        """Verify _convert_bbox_to_z safely returns NaNs on non-finite or short inputs."""
        from argus.core.tracker import _convert_bbox_to_z

        z_nan = _convert_bbox_to_z([float("nan"), 0, 10, 10])
        assert np.any(np.isnan(z_nan))

        z_short = _convert_bbox_to_z([0, 0])
        assert np.any(np.isnan(z_short))

    def test_tracker_post_update_invalid_eviction(self) -> None:
        """Verify a tracker that becomes invalid is evicted at end of update."""
        tracker = SortTracker()
        det = Detection(box=(100, 100, 200, 200), confidence=0.9)
        tracker.update([det])
        assert tracker.active_tracks_count == 1

        # Force tracker to become invalid during subsequent update
        tracker.trackers[0].x[2] = -100.0  # Invalid area/scale
        assert not tracker.trackers[0].is_valid()

        # Update with new non-overlapping detection
        det2 = Detection(box=(10, 10, 30, 30), confidence=0.9)
        tracker.update([det2])
        # The invalid tracker must have been evicted, only the new tracker survives
        assert tracker.active_tracks_count == 1
        assert tracker.trackers[0].id != 1

    def test_detection_track_id_serialization(self) -> None:
        """Verify Detection with track_id properly serializes and deserializes."""
        tracker = SortTracker()
        det = Detection(box=(20, 20, 80, 80), confidence=0.92)
        tracked = tracker.update([det])
        assert len(tracked) == 1
        assert tracked[0].track_id == 1

        # Test model_dump includes track_id
        dumped = tracked[0].model_dump()
        assert dumped["track_id"] == 1

        # Test JSON serialization includes track_id
        json_str = tracked[0].model_dump_json()
        assert '"track_id":1' in json_str

        # Test deserialization restores track_id
        restored = Detection.model_validate_json(json_str)
        assert restored.track_id == 1
        assert restored == tracked[0]

    def test_concurrent_tracker_updates(self) -> None:
        """Verify thread-safe concurrent updates on a shared SortTracker instance."""
        import concurrent.futures

        tracker = SortTracker()

        def worker(worker_id: int) -> None:
            # Each worker sends a sequence of detections in distinct regions
            base_x = worker_id * 50
            for frame_idx in range(5):
                det = Detection(
                    box=(base_x + frame_idx, 50, base_x + frame_idx + 30, 80),
                    confidence=0.85,
                )
                res = tracker.update([det])
                assert len(res) == 1
                assert res[0].track_id is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert tracker.active_tracks_count >= 1
