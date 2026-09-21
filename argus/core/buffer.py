"""
Circular Memory Buffer for Argus video frames.

Maintains a rolling buffer of pre-event video frames in RAM using collections.deque,
guaranteeing zero disk I/O until an event is triggered.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Iterator
from typing import overload

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class VideoBuffer:
    """
    Circular memory buffer holding the most recent N seconds of video frames.

    Frames are stored as raw numpy arrays in a collections.deque with maxlen = fps * seconds.
    When capacity is reached, old frames are automatically ejected to keep the buffer
    strictly in RAM with no disk I/O.
    """

    def __init__(
        self,
        fps: int | float = 15,
        seconds: int | float = 10,
        maxlen: int | None = None,
    ) -> None:
        if isinstance(fps, bool) or not isinstance(fps, (int, float)):
            raise TypeError(f"fps must be an integer or float, got {type(fps).__name__}")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise TypeError(f"seconds must be an integer or float, got {type(seconds).__name__}")
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError(f"seconds must be positive, got {seconds}")

        self._fps = (
            int(fps)
            if isinstance(fps, int) or (isinstance(fps, float) and fps.is_integer())
            else float(fps)
        )
        self._seconds = (
            int(seconds)
            if isinstance(seconds, int) or (isinstance(seconds, float) and seconds.is_integer())
            else float(seconds)
        )
        if maxlen is not None:
            if isinstance(maxlen, bool) or not isinstance(maxlen, int) or maxlen <= 0:
                raise ValueError(f"maxlen must be positive, got {maxlen}")
            self._maxlen = int(maxlen)
        else:
            self._maxlen = max(1, int(round(float(self._fps) * float(self._seconds))))

        self._buffer: deque[np.ndarray] = deque(maxlen=self._maxlen)
        self._lock = threading.Lock()

    @property
    def fps(self) -> int | float:
        """Frame rate of the video buffer."""
        return self._fps

    @property
    def seconds(self) -> int | float:
        """Target buffer duration in seconds."""
        return self._seconds

    @property
    def maxlen(self) -> int:
        """Maximum number of frames that can be held."""
        return self._maxlen

    @property
    def capacity(self) -> int:
        """Maximum number of frames that can be held (alias for maxlen)."""
        return self._maxlen

    @property
    def is_full(self) -> bool:
        """Whether the buffer has reached maximum capacity."""
        with self._lock:
            return len(self._buffer) == self._maxlen

    @property
    def empty(self) -> bool:
        """Whether the buffer contains no frames."""
        with self._lock:
            return len(self._buffer) == 0

    @property
    def duration(self) -> float:
        """Current duration of buffered frames in seconds."""
        with self._lock:
            return len(self._buffer) / self._fps if self._fps > 0 else 0.0

    def append(self, frame: np.ndarray) -> None:
        """
        Append a frame to the circular buffer.

        If the buffer is full, the oldest frame is automatically dropped.
        """
        if not isinstance(frame, np.ndarray):
            raise TypeError(f"Expected frame of type np.ndarray, got {type(frame).__name__}")
        if frame.size == 0 or frame.ndim not in (2, 3):
            raise ValueError(
                f"Invalid frame shape {getattr(frame, 'shape', None)}; must be a non-empty 2D or 3D array"
            )
        if frame.ndim == 3 and frame.shape[2] not in (1, 3, 4):
            raise ValueError(
                f"Unsupported number of channels: {frame.shape[2]}; must be 1, 3, or 4"
            )
        with self._lock:
            self._buffer.append(frame)

    def get_buffer(self) -> list[np.ndarray]:
        """
        Return a snapshot list of all currently stored frames in chronological order.
        """
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        """Clear all frames from the buffer."""
        with self._lock:
            self._buffer.clear()

    def __iter__(self) -> Iterator[np.ndarray]:
        """Iterate over a thread-safe snapshot of currently stored frames."""
        with self._lock:
            return iter(list(self._buffer))

    @overload
    def __getitem__(self, index: int) -> np.ndarray: ...

    @overload
    def __getitem__(self, index: slice) -> list[np.ndarray]: ...

    def __getitem__(self, index: int | slice) -> np.ndarray | list[np.ndarray]:
        """Get frame(s) by index or slice in chronological order."""
        with self._lock:
            if isinstance(index, slice):
                return list(self._buffer)[index]
            return self._buffer[index]

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def __bool__(self) -> bool:
        with self._lock:
            return len(self._buffer) > 0

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"<VideoBuffer frames={len(self._buffer)}/{self._maxlen} "
                f"fps={self._fps} seconds={self._seconds}>"
            )
