"""
Motion Pre-filter for Argus.

Uses OpenCV's MOG2 background subtractor to quickly identify frames with
meaningful motion before passing downstream to heavier detection / recognition models.
"""

from __future__ import annotations

import asyncio
import math
import threading
from typing import Any

import cv2
import numpy as np

from argus.config.settings import CameraConfig


class MotionFilter:
    """
    Motion pre-filter using OpenCV's MOG2 background subtractor.

    Filters out static frames before passing downstream to computationally expensive
    models (YOLO detection, InsightFace face recognition, etc.).
    """

    def __init__(
        self,
        threshold: float = 0.005,
        history: int = 500,
        var_threshold: float = 16.0,
        detect_shadows: bool = False,
    ) -> None:
        """
        Initialize the motion filter.

        Args:
            threshold: Fraction of foreground pixels required to trigger motion (0.005 = 0.5%).
            history: Number of frames used to build the background model.
            var_threshold: Threshold on the squared Mahalanobis distance to decide whether
                it is well described by the background model.
            detect_shadows: If True, shadows are marked (pixel value 127) and excluded
                from motion count.
        """
        if isinstance(threshold, bool) or not (
            isinstance(threshold, (int, float))
            and math.isfinite(threshold)
            and 0.0 <= threshold <= 1.0
        ):
            raise ValueError(f"Motion threshold must be between 0.0 and 1.0, got {threshold}")
        if isinstance(history, bool) or not isinstance(history, int) or history <= 0:
            raise ValueError(f"History must be positive, got {history}")
        if isinstance(var_threshold, bool) or not (
            isinstance(var_threshold, (int, float))
            and math.isfinite(var_threshold)
            and var_threshold > 0
        ):
            raise ValueError(f"var_threshold must be positive, got {var_threshold}")
        if not isinstance(detect_shadows, bool):
            raise TypeError(
                f"detect_shadows must be a boolean, got {type(detect_shadows).__name__}"
            )

        self.threshold = float(threshold)
        self.history = history
        self.var_threshold = float(var_threshold)
        self.detect_shadows = detect_shadows
        self._lock = threading.Lock()

        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=self.history,
            varThreshold=self.var_threshold,
            detectShadows=self.detect_shadows,
        )

    @classmethod
    def from_camera(cls, camera: CameraConfig, **kwargs: Any) -> MotionFilter:
        """Create a MotionFilter configured from a CameraConfig."""
        if not isinstance(camera, CameraConfig):
            raise TypeError(f"camera must be a CameraConfig, got {type(camera).__name__}")
        kwargs.setdefault("threshold", camera.motion_threshold)
        return cls(**kwargs)

    def reset(self) -> None:
        """Reset the background subtractor model."""
        with self._lock:
            self._subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.var_threshold,
                detectShadows=self.detect_shadows,
            )

    def calculate_motion_ratio(self, frame: np.ndarray | None, update_model: bool = True) -> float:
        """
        Calculate the fraction of pixels classified as foreground motion.

        Args:
            frame: BGR or grayscale image frame as a numpy array.
            update_model: If True, adapts the background model with this frame.
                If False, evaluates motion without modifying the background model.

        Returns:
            Fraction of foreground pixels in range [0.0, 1.0].
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return 0.0

        # Handle batch dimension if present (e.g. 1 x H x W x C)
        if frame.ndim == 4 and frame.shape[0] == 1:
            frame = frame.squeeze(0)

        # Reject invalid dimensions (must be 2D grayscale or 3D multi-channel)
        if frame.ndim not in (2, 3):
            return 0.0

        # Reject invalid channels: OpenCV MOG2 matrices support 1 to 512 channels
        if frame.ndim == 3 and (frame.shape[2] == 0 or frame.shape[2] > 512):
            return 0.0

        # Validate dtype: convert numeric arrays to uint8 or reject object/non-numeric arrays
        if frame.dtype != np.uint8:
            if np.issubdtype(frame.dtype, np.number):
                if np.issubdtype(frame.dtype, np.floating):
                    if not np.all(np.isfinite(frame)):
                        return 0.0
                    max_val = float(frame.max())
                    min_val = float(frame.min())
                    if min_val >= 0.0 and max_val <= 1.0 and max_val > 0.0:
                        frame = (frame * 255.0).astype(np.uint8)
                    else:
                        frame = np.clip(frame, 0, 255).astype(np.uint8)
                else:
                    frame = np.clip(frame, 0, 255).astype(np.uint8)
            elif np.issubdtype(frame.dtype, np.bool_):
                frame = (frame.astype(np.uint8)) * 255
            else:
                return 0.0

        frame = np.ascontiguousarray(frame)

        learning_rate = -1 if update_model else 0
        with self._lock:
            fg_mask = self._subtractor.apply(frame, learningRate=learning_rate)

        if self.detect_shadows:
            # OpenCV sets shadows to 127; true foreground motion is 255
            fg_pixels = int(np.count_nonzero(fg_mask == 255))
        else:
            # Standard MOG2 without shadows marks foreground as 255
            fg_pixels = int(np.count_nonzero(fg_mask > 0))

        total_pixels = frame.shape[0] * frame.shape[1]
        return fg_pixels / total_pixels

    def has_motion(self, frame: np.ndarray | None) -> bool:
        """
        Check if the frame contains motion exceeding the configured threshold.

        Args:
            frame: BGR or grayscale image frame as a numpy array.

        Returns:
            True if foreground pixel ratio exceeds self.threshold, False otherwise.
        """
        ratio = self.calculate_motion_ratio(frame, update_model=True)
        return ratio > self.threshold

    async def has_motion_async(self, frame: np.ndarray | None) -> bool:
        """
        Asynchronously check if frame contains motion using a thread pool executor.

        Avoids blocking the asyncio event loop with OpenCV CPU operations.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.has_motion, frame)
