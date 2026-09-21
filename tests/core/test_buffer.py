"""
Unit tests for VideoBuffer (argus/core/buffer.py).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np
import pytest

from argus.core.buffer import VideoBuffer


class TestVideoBufferInit:
    def test_default_initialization(self) -> None:
        buf = VideoBuffer()
        assert buf.fps == 15
        assert buf.seconds == 10
        assert buf.maxlen == 150
        assert buf.capacity == 150
        assert len(buf) == 0
        assert buf.empty is True
        assert buf.is_full is False
        assert buf.duration == 0.0

    def test_custom_fps_and_seconds(self) -> None:
        buf = VideoBuffer(fps=30, seconds=5)
        assert buf.fps == 30
        assert buf.seconds == 5
        assert buf.maxlen == 150
        assert len(buf) == 0

    def test_explicit_maxlen_override(self) -> None:
        buf = VideoBuffer(fps=15, seconds=10, maxlen=25)
        assert buf.maxlen == 25
        assert buf.capacity == 25

    def test_invalid_fps_raises(self) -> None:
        with pytest.raises(ValueError, match="fps must be positive"):
            VideoBuffer(fps=0)
        with pytest.raises(ValueError, match="fps must be positive"):
            VideoBuffer(fps=-5)

    def test_invalid_seconds_raises(self) -> None:
        with pytest.raises(ValueError, match="seconds must be positive"):
            VideoBuffer(seconds=0)
        with pytest.raises(ValueError, match="seconds must be positive"):
            VideoBuffer(seconds=-2)

    def test_invalid_maxlen_raises(self) -> None:
        with pytest.raises(ValueError, match="maxlen must be positive"):
            VideoBuffer(maxlen=0)
        with pytest.raises(ValueError, match="maxlen must be positive"):
            VideoBuffer(maxlen=-10)

    def test_repr(self) -> None:
        buf = VideoBuffer(fps=10, seconds=2)
        r = repr(buf)
        assert "VideoBuffer" in r
        assert "0/20" in r


class TestVideoBufferOperations:
    def test_append_single_frame(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        buf.append(frame)

        assert len(buf) == 1
        assert buf.empty is False
        assert buf.is_full is False
        assert buf.duration == pytest.approx(0.1)

        stored = buf.get_buffer()
        assert len(stored) == 1
        np.testing.assert_array_equal(stored[0], frame)

    def test_append_invalid_type_raises(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        with pytest.raises(TypeError, match="Expected frame of type np.ndarray"):
            buf.append([1, 2, 3])  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="Expected frame of type np.ndarray"):
            buf.append(None)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="Expected frame of type np.ndarray"):
            buf.append("not a frame")  # type: ignore[arg-type]

    def test_clear(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        for i in range(5):
            buf.append(np.full((10, 10, 3), i, dtype=np.uint8))
        assert len(buf) == 5

        buf.clear()
        assert len(buf) == 0
        assert buf.empty is True
        assert buf.get_buffer() == []
        assert buf.duration == 0.0

    def test_get_buffer_returns_new_list_copy(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        frame = np.ones((10, 10, 3), dtype=np.uint8)
        buf.append(frame)

        res1 = buf.get_buffer()
        res2 = buf.get_buffer()
        assert res1 is not res2
        assert len(res1) == 1
        assert len(res2) == 1


class TestVideoBufferEjection:
    def test_old_frames_ejected_when_capacity_reached(self) -> None:
        """Verify rolling buffer strictly holds maxlen frames, dropping the oldest."""
        capacity = 5
        buf = VideoBuffer(maxlen=capacity)

        frames = [np.full((10, 10, 3), i, dtype=np.uint8) for i in range(10)]

        # Append initial capacity frames (0, 1, 2, 3, 4)
        for i in range(capacity):
            buf.append(frames[i])
            assert len(buf) == i + 1

        assert buf.is_full is True
        stored = buf.get_buffer()
        assert [int(f[0, 0, 0]) for f in stored] == [0, 1, 2, 3, 4]

        # Append frame 5 -> frame 0 should be ejected
        buf.append(frames[5])
        assert len(buf) == capacity
        assert buf.is_full is True
        stored = buf.get_buffer()
        assert [int(f[0, 0, 0]) for f in stored] == [1, 2, 3, 4, 5]

        # Append frame 6, 7, 8, 9
        for i in range(6, 10):
            buf.append(frames[i])
            assert len(buf) == capacity

        stored = buf.get_buffer()
        assert [int(f[0, 0, 0]) for f in stored] == [5, 6, 7, 8, 9]

    def test_concurrency_thread_safety(self) -> None:
        """Verify thread-safe concurrent appends do not corrupt internal deque."""
        buf = VideoBuffer(maxlen=50)

        def worker(thread_id: int) -> None:
            for i in range(30):
                f = np.full((10, 10, 3), (thread_id * 50 + i) % 250, dtype=np.uint8)
                buf.append(f)
                _ = buf.get_buffer()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, tid) for tid in range(4)]
            for f in futures:
                f.result()

        assert len(buf) == 50
        assert buf.is_full is True

    def test_no_disk_io_during_buffering(self) -> None:
        """Verify that appending and accessing the buffer never performs file open/write."""
        buf = VideoBuffer(fps=15, seconds=10)
        with patch("builtins.open") as mock_open:
            for i in range(20):
                buf.append(np.full((32, 32, 3), i, dtype=np.uint8))
            _ = buf.get_buffer()
            mock_open.assert_not_called()

    def test_empty_frame_raises_value_error(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        with pytest.raises(ValueError, match="Invalid frame shape"):
            buf.append(np.array([]))

        with pytest.raises(ValueError, match="Invalid frame shape"):
            buf.append(np.zeros((0, 0, 3), dtype=np.uint8))

    def test_invalid_dimensions_raise_value_error(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        with pytest.raises(ValueError, match="must be a non-empty 2D or 3D array"):
            buf.append(np.zeros((10,), dtype=np.uint8))

        with pytest.raises(ValueError, match="must be a non-empty 2D or 3D array"):
            buf.append(np.zeros((10, 10, 3, 2), dtype=np.uint8))

    def test_float_seconds_and_fps(self) -> None:
        buf = VideoBuffer(fps=15, seconds=0.5)
        assert buf.seconds == 0.5
        assert buf.maxlen == 8
        assert buf.capacity == 8

        buf2 = VideoBuffer(fps=29.97, seconds=2.0)
        assert buf2.fps == 29.97
        assert buf2.maxlen == 60

    def test_append_grayscale_and_color_frames(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        buf.append(np.zeros((100, 100), dtype=np.uint8))
        buf.append(np.zeros((100, 100, 3), dtype=np.uint8))
        assert len(buf) == 2

    def test_type_and_finite_validation_in_init(self) -> None:
        with pytest.raises(TypeError, match="fps must be an integer or float"):
            VideoBuffer(fps=True)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="seconds must be an integer or float"):
            VideoBuffer(seconds=False)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="fps must be positive"):
            VideoBuffer(fps=float("nan"))
        with pytest.raises(ValueError, match="seconds must be positive"):
            VideoBuffer(seconds=float("inf"))
        with pytest.raises(ValueError, match="maxlen must be positive"):
            VideoBuffer(maxlen=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="maxlen must be positive"):
            VideoBuffer(maxlen="10")  # type: ignore[arg-type]

    def test_unsupported_3d_channel_count_raises(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        with pytest.raises(ValueError, match="Unsupported number of channels: 5"):
            buf.append(np.zeros((10, 10, 5), dtype=np.uint8))
        with pytest.raises(ValueError, match="Unsupported number of channels: 2"):
            buf.append(np.zeros((10, 10, 2), dtype=np.uint8))

    def test_buffer_bool_evaluation(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        assert bool(buf) is False
        buf.append(np.zeros((10, 10, 3), dtype=np.uint8))
        assert bool(buf) is True
        buf.clear()
        assert bool(buf) is False

    def test_buffer_iteration_protocol(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        frames = [np.full((10, 10, 3), i, dtype=np.uint8) for i in range(5)]
        for f in frames:
            buf.append(f)

        iter_frames = list(buf)
        assert len(iter_frames) == 5
        for i, f in enumerate(iter_frames):
            assert int(f[0, 0, 0]) == i

    def test_buffer_indexing_and_slicing(self) -> None:
        buf = VideoBuffer(fps=10, seconds=1)
        for i in range(5):
            buf.append(np.full((10, 10, 3), i * 10, dtype=np.uint8))

        # Indexing
        assert int(buf[0][0, 0, 0]) == 0
        assert int(buf[-1][0, 0, 0]) == 40
        assert int(buf[2][0, 0, 0]) == 20

        with pytest.raises(IndexError):
            _ = buf[10]

        # Slicing
        slice1 = buf[:2]
        assert isinstance(slice1, list)
        assert len(slice1) == 2
        assert int(slice1[0][0, 0, 0]) == 0
        assert int(slice1[1][0, 0, 0]) == 10

        slice2 = buf[-2:]
        assert len(slice2) == 2
        assert int(slice2[0][0, 0, 0]) == 30
        assert int(slice2[1][0, 0, 0]) == 40

    def test_buffer_thread_safe_iteration(self) -> None:
        buf = VideoBuffer(maxlen=50)

        def reader() -> None:
            for _ in range(50):
                # Iteration takes snapshot without deque mutation error
                _ = list(buf)

        def writer() -> None:
            for i in range(100):
                buf.append(np.full((10, 10, 3), i % 255, dtype=np.uint8))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(writer),
                executor.submit(reader),
                executor.submit(writer),
                executor.submit(reader),
            ]
            for f in futures:
                f.result()
