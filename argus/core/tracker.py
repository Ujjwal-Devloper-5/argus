"""
SORT (Simple Online and Realtime Tracking) object tracker for Argus.

Assigns persistent tracking IDs to detected bounding boxes across video frames
using a Kalman filter motion model and Hungarian algorithm (linear sum assignment)
IoU matching.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence

import numpy as np
import structlog
from scipy.optimize import linear_sum_assignment

from argus.core.detector import Detection

logger = structlog.get_logger(__name__)


def compute_iou(
    bb_test: Sequence[float] | np.ndarray,
    bb_gt: Sequence[float] | np.ndarray,
) -> float:
    """
    Compute Intersection-over-Union (IoU) between two bounding boxes.

    Args:
        bb_test: Coordinates [x1, y1, x2, y2].
        bb_gt: Coordinates [x1, y1, x2, y2].

    Returns:
        IoU score in range [0.0, 1.0].
    """
    if len(bb_test) < 4 or len(bb_gt) < 4:
        return 0.0

    t0, t1, t2, t3 = float(bb_test[0]), float(bb_test[1]), float(bb_test[2]), float(bb_test[3])
    g0, g1, g2, g3 = float(bb_gt[0]), float(bb_gt[1]), float(bb_gt[2]), float(bb_gt[3])

    if not (
        math.isfinite(t0)
        and math.isfinite(t1)
        and math.isfinite(t2)
        and math.isfinite(t3)
        and math.isfinite(g0)
        and math.isfinite(g1)
        and math.isfinite(g2)
        and math.isfinite(g3)
    ):
        return 0.0

    xx1 = max(t0, g0)
    yy1 = max(t1, g1)
    xx2 = min(t2, g2)
    yy2 = min(t3, g3)

    w = max(0.0, xx2 - xx1)
    h = max(0.0, yy2 - yy1)
    wh = w * h

    area_test = max(0.0, t2 - t0) * max(0.0, t3 - t1)
    area_gt = max(0.0, g2 - g0) * max(0.0, g3 - g1)

    union = area_test + area_gt - wh
    if union <= 0.0:
        return 0.0
    return float(wh / union)


def _convert_bbox_to_z(bbox: Sequence[float] | np.ndarray) -> np.ndarray:
    """
    Convert bounding box [x1, y1, x2, y2] to observation vector [u, v, s, r].

    u: center x, v: center y, s: area (scale), r: aspect ratio (w / h).
    """
    if len(bbox) < 4:
        return np.array([np.nan, np.nan, np.nan, np.nan], dtype=np.float64)

    b0, b1, b2, b3 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    if not (math.isfinite(b0) and math.isfinite(b1) and math.isfinite(b2) and math.isfinite(b3)):
        return np.array([np.nan, np.nan, np.nan, np.nan], dtype=np.float64)

    w = max(1.0, b2 - b0)
    h = max(1.0, b3 - b1)
    u = b0 + w / 2.0
    v = b1 + h / 2.0
    s = w * h
    r = w / h
    return np.array([u, v, s, r], dtype=np.float64)


def _convert_x_to_bbox(x: np.ndarray) -> np.ndarray:
    """
    Convert state vector [u, v, s, r, ...] to bounding box [x1, y1, x2, y2].
    """
    if not np.all(np.isfinite(x[:4])):
        return np.array([np.nan, np.nan, np.nan, np.nan], dtype=np.float64)

    u = float(x[0])
    v = float(x[1])
    s = max(1.0, float(x[2]))
    r = max(1e-4, min(1e4, float(x[3])))

    w = math.sqrt(s * r)
    h = s / max(1e-4, w)

    return np.array(
        [u - w / 2.0, v - h / 2.0, u + w / 2.0, v + h / 2.0],
        dtype=np.float64,
    )


class KalmanBoxTracker:
    """
    Tracks an individual bounding box using a 7-state Kalman filter:
    State: [u, v, s, r, u_dot, v_dot, s_dot]^T
    Observation: [u, v, s, r]^T
    """

    def __init__(
        self,
        bbox: Sequence[float] | np.ndarray,
        track_id: int,
        class_name: str = "person",
    ) -> None:
        """
        Initialize tracker with initial bounding box and unique track_id.
        """
        self.id = track_id
        self.class_name = class_name

        # State transition matrix F (constant velocity model)
        self.F = np.eye(7, dtype=np.float64)
        for i in range(3):
            self.F[i, i + 4] = 1.0

        # Measurement matrix H
        self.H = np.zeros((4, 7), dtype=np.float64)
        for i in range(4):
            self.H[i, i] = 1.0

        # Measurement noise covariance R
        self.R = np.eye(4, dtype=np.float64)
        self.R[2:, 2:] *= 10.0

        # State covariance matrix P
        self.P = np.eye(7, dtype=np.float64) * 10.0
        self.P[4:, 4:] *= 1000.0  # High initial velocity uncertainty

        # Process noise covariance Q
        self.Q = np.eye(7, dtype=np.float64)
        self.Q[4:, 4:] *= 0.01

        # Initial state
        z = _convert_bbox_to_z(bbox)
        self.x = np.zeros(7, dtype=np.float64)
        self.x[:4] = z

        self.time_since_update = 0
        self.hits = 1
        self.age = 0

    def is_valid(self) -> bool:
        """Check if tracker state and covariance are finite and non-degenerate."""
        return bool(
            np.all(np.isfinite(self.x))
            and np.all(np.isfinite(self.P))
            and self.x[2] > 0
            and self.x[3] > 0
        )

    def update(self, bbox: Sequence[float] | np.ndarray) -> None:
        """
        Update the state estimate with a new observed bounding box.
        """
        self.time_since_update = 0
        self.hits += 1

        z = _convert_bbox_to_z(bbox)
        y = z - self.H @ self.x
        s_cov = self.H @ self.P @ self.H.T + self.R
        try:
            k_gain = self.P @ self.H.T @ np.linalg.inv(s_cov)
        except np.linalg.LinAlgError:
            k_gain = self.P @ self.H.T @ np.linalg.pinv(s_cov)

        self.x = self.x + k_gain @ y
        eye_7 = np.eye(7, dtype=np.float64)
        self.P = (eye_7 - k_gain @ self.H) @ self.P
        self.P = (self.P + self.P.T) / 2.0

    def predict(self) -> np.ndarray:
        """
        Advance the state vector and return the predicted bounding box.
        """
        # Ensure area and scale remain positive
        if self.x[6] + self.x[2] <= 0:
            self.x[6] = 0.0

        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        self.P = (self.P + self.P.T) / 2.0
        self.age += 1
        self.time_since_update += 1

        return self.get_state()

    def get_state(self) -> np.ndarray:
        """
        Return the current bounding box estimate [x1, y1, x2, y2].
        """
        return _convert_x_to_bbox(self.x)


class SortTracker:
    """
    SORT (Simple Online and Realtime Tracking) implementation.

    Maintains active tracks, performs Hungarian matching on IoU distances,
    and returns detections with populated `track_id` fields.
    """

    def __init__(
        self,
        max_age: int = 30,
        iou_threshold: float = 0.3,
        initial_id: int = 1,
    ) -> None:
        """
        Initialize the SortTracker.

        Args:
            max_age: Maximum consecutive frames to keep a lost track alive.
            iou_threshold: Minimum IoU overlap to associate a detection with an existing track.
            initial_id: Starting tracking ID (default 1).
        """
        if max_age < 1:
            raise ValueError(f"max_age must be >= 1, got {max_age}")
        if not (0.0 <= iou_threshold <= 1.0):
            raise ValueError(f"iou_threshold must be between 0.0 and 1.0, got {iou_threshold}")
        if initial_id < 1:
            raise ValueError(f"initial_id must be >= 1, got {initial_id}")

        self.max_age = max_age
        self.iou_threshold = iou_threshold
        self._next_id = initial_id
        self.trackers: list[KalmanBoxTracker] = []
        self._lock = threading.RLock()

    def update(self, detections: list[Detection]) -> list[Detection]:
        """
        Update tracker with new YOLO detections and return them with populated `track_id`.

        Args:
            detections: List of Detection objects from the object detector.

        Returns:
            List of Detection objects with populated `track_id` fields.
        """
        with self._lock:
            if not detections:
                # Predict existing tracks to advance time
                for trk in self.trackers:
                    trk.predict()
                self.trackers = [
                    t for t in self.trackers if t.is_valid() and t.time_since_update <= self.max_age
                ]
                return []

            # 1. Predict next state for all active trackers
            predicted_boxes: list[np.ndarray] = []
            valid_trackers: list[KalmanBoxTracker] = []
            for trk in self.trackers:
                pos = trk.predict()
                if trk.is_valid() and not np.any(np.isnan(pos)) and not np.any(np.isinf(pos)):
                    predicted_boxes.append(pos)
                    valid_trackers.append(trk)
            self.trackers = valid_trackers

            # 2. Extract bounding boxes from incoming detections
            detection_boxes = [det.box for det in detections]
            assigned_ids: list[int | None] = [None] * len(detections)

            # 3. Associate detections with tracks via IoU and Hungarian algorithm
            if len(self.trackers) > 0 and len(detection_boxes) > 0:
                iou_matrix = np.zeros(
                    (len(self.trackers), len(detection_boxes)),
                    dtype=np.float64,
                )
                for t_idx, trk_box in enumerate(predicted_boxes):
                    for d_idx, det in enumerate(detections):
                        # Only match if classes are compatible
                        if self.trackers[t_idx].class_name == det.class_name:
                            iou_matrix[t_idx, d_idx] = compute_iou(trk_box, det.box)

                # Maximize IoU by minimizing negative IoU
                row_ind, col_ind = linear_sum_assignment(-iou_matrix)

                matched_trackers: set[int] = set()
                matched_detections: set[int] = set()

                for r, c in zip(row_ind, col_ind, strict=False):
                    if (
                        iou_matrix[r, c] > 0.0
                        and iou_matrix[r, c] >= self.iou_threshold
                        and self.trackers[r].class_name == detections[c].class_name
                    ):
                        matched_trackers.add(r)
                        matched_detections.add(c)
                        self.trackers[r].update(detection_boxes[c])
                        assigned_ids[c] = self.trackers[r].id

                # Create new trackers for unmatched detections
                for d_idx in range(len(detections)):
                    if d_idx not in matched_detections:
                        new_id = self._next_id
                        self._next_id += 1
                        new_trk = KalmanBoxTracker(
                            bbox=detection_boxes[d_idx],
                            track_id=new_id,
                            class_name=detections[d_idx].class_name,
                        )
                        self.trackers.append(new_trk)
                        assigned_ids[d_idx] = new_id
            else:
                # No existing trackers: create a new tracker for each detection
                for d_idx, det in enumerate(detections):
                    new_id = self._next_id
                    self._next_id += 1
                    new_trk = KalmanBoxTracker(
                        bbox=det.box,
                        track_id=new_id,
                        class_name=det.class_name,
                    )
                    self.trackers.append(new_trk)
                    assigned_ids[d_idx] = new_id

            # 4. Remove dead trackers that haven't been updated for max_age frames or became invalid
            self.trackers = [
                t for t in self.trackers if t.is_valid() and t.time_since_update <= self.max_age
            ]

            # 5. Return updated detections with track_id populated
            updated_detections: list[Detection] = []
            for det, track_id in zip(detections, assigned_ids, strict=True):
                updated_detections.append(det.model_copy(update={"track_id": track_id}))

            logger.debug(
                "Updated SORT tracker",
                input_detections=len(detections),
                active_trackers=len(self.trackers),
                assigned_ids=assigned_ids,
            )

            return updated_detections

    def reset(self) -> None:
        """Reset all active tracks and the track ID sequence."""
        with self._lock:
            self.trackers.clear()
            self._next_id = 1
            logger.info("Reset SortTracker")

    @property
    def active_tracks_count(self) -> int:
        """Return the number of currently active tracks."""
        with self._lock:
            return len(self.trackers)
