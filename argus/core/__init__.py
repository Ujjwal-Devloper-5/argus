"""Core video processing components for Argus."""

from argus.core.buffer import VideoBuffer
from argus.core.detector import Detection, DetectorWorker
from argus.core.motion import MotionFilter
from argus.core.recognizer import FaceMatch, FaceRecognizer
from argus.core.recorder import (
    EventRecorder,
    build_ffmpeg_command,
    check_nvenc_support,
    is_nvenc_available,
    normalize_frame,
    reset_nvenc_cache,
)
from argus.core.stream import StreamWorker
from argus.core.tracker import SortTracker

__all__ = [
    "Detection",
    "DetectorWorker",
    "EventRecorder",
    "FaceMatch",
    "FaceRecognizer",
    "MotionFilter",
    "SortTracker",
    "StreamWorker",
    "VideoBuffer",
    "build_ffmpeg_command",
    "check_nvenc_support",
    "is_nvenc_available",
    "normalize_frame",
    "reset_nvenc_cache",
]
