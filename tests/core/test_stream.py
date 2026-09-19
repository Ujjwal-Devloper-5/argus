"""
Unit tests for StreamWorker (PyAV RTSP ingestor) and MotionFilter (OpenCV MOG2).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import av
import numpy as np
import pytest

from argus.config.settings import CameraConfig
from argus.core.motion import MotionFilter
from argus.core.stream import StreamWorker

# ===========================================================================
# Fixtures & Helpers
# ===========================================================================


@pytest.fixture
def sample_camera() -> CameraConfig:
    """Fixture for standard CameraConfig."""
    return CameraConfig(
        name="front_door",
        rtsp_url="rtsp://192.168.1.100:554/live",
        fps=15,
        motion_threshold=0.005,
    )


@pytest.fixture
def disabled_camera() -> CameraConfig:
    """Fixture for disabled CameraConfig."""
    return CameraConfig(
        name="disabled_cam",
        rtsp_url="rtsp://192.168.1.101:554/live",
        disabled=True,
    )


def create_mock_video_frame(width: int = 64, height: int = 64, color: int = 120) -> MagicMock:
    """Create a mock PyAV VideoFrame with to_ndarray method."""
    mock_frame = MagicMock()
    arr = np.full((height, width, 3), fill_value=color, dtype=np.uint8)
    mock_frame.to_ndarray.return_value = arr
    return mock_frame


def create_temp_video_file(
    path: Path, num_frames: int = 5, width: int = 64, height: int = 64
) -> Path:
    """Create a real minimal MP4 video file using PyAV for testing."""
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"

    for i in range(num_frames):
        img = np.full((height, width, 3), fill_value=i * 20, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


# ===========================================================================
# StreamWorker Unit Tests
# ===========================================================================


class TestStreamWorker:
    """Test suite for StreamWorker."""

    def test_worker_initialization(self, sample_camera: CameraConfig) -> None:
        """Test default and custom initialization attributes."""
        worker = StreamWorker(sample_camera)
        assert worker.camera == sample_camera
        assert worker.queue.maxsize == 5
        assert worker.initial_backoff == 5.0
        assert worker.max_backoff == 60.0
        assert worker.backoff_factor == 2.0
        assert worker.stimeout_us == 5_000_000
        assert worker.current_backoff == 5.0
        assert not worker.is_running

        # Custom initialization
        custom_q: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=10)
        custom_worker = StreamWorker(
            sample_camera,
            queue=custom_q,
            initial_backoff=2.0,
            max_backoff=30.0,
            backoff_factor=1.5,
            stimeout_us=2_000_000,
        )
        assert custom_worker.queue is custom_q
        assert custom_worker.queue.maxsize == 10
        assert custom_worker.initial_backoff == 2.0
        assert custom_worker.max_backoff == 30.0
        assert custom_worker.backoff_factor == 1.5
        assert custom_worker.stimeout_us == 2_000_000

    def test_queue_backpressure_drops_oldest(self, sample_camera: CameraConfig) -> None:
        """Assert that queue backpressure correctly drops the oldest frame."""
        queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=3)
        worker = StreamWorker(sample_camera, queue=queue)

        frames = [np.full((10, 10, 3), fill_value=i, dtype=np.uint8) for i in range(5)]

        # Push frame 0, 1, 2 -> Queue becomes full [0, 1, 2]
        worker.push_frame(frames[0])
        worker.push_frame(frames[1])
        worker.push_frame(frames[2])
        assert queue.qsize() == 3

        # Push frame 3 -> Frame 0 dropped, queue contains [1, 2, 3]
        worker.push_frame(frames[3])
        assert queue.qsize() == 3

        # Push frame 4 -> Frame 1 dropped, queue contains [2, 3, 4]
        worker.push_frame(frames[4])
        assert queue.qsize() == 3

        # Verify remaining frames in queue are [2, 3, 4]
        f2 = queue.get_nowait()
        f3 = queue.get_nowait()
        f4 = queue.get_nowait()
        assert np.array_equal(f2, frames[2])
        assert np.array_equal(f3, frames[3])
        assert np.array_equal(f4, frames[4])
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_disabled_camera_does_not_start(self, disabled_camera: CameraConfig) -> None:
        """Assert that disabled camera worker returns immediately without streaming."""
        worker = StreamWorker(disabled_camera)
        with patch("av.open") as mock_open:
            await worker.start()
            mock_open.assert_not_called()
        assert not worker.is_running

    @pytest.mark.asyncio
    async def test_streaming_frames_arrive_in_queue_with_mock(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert that PyAV is called with tcp/stimeout and frames arrive in the queue."""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_container.streams.video = [mock_stream]

        frame1 = create_mock_video_frame(color=10)
        frame2 = create_mock_video_frame(color=20)
        frame3 = create_mock_video_frame(color=30)
        mock_container.decode.return_value = iter([frame1, frame2, frame3])

        worker = StreamWorker(sample_camera, initial_backoff=0.01, max_backoff=0.05)

        with patch("av.open", return_value=mock_container) as mock_open:
            task = asyncio.create_task(worker.start())

            received_frames = []
            for _ in range(3):
                frame = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
                received_frames.append(frame)

            await worker.stop()
            await task

            mock_open.assert_called()
            called_options = mock_open.call_args[1].get("options")
            assert called_options is not None
            assert called_options["rtsp_transport"] == "tcp"
            assert called_options["stimeout"] == "5000000"

            assert len(received_frames) == 3
            assert received_frames[0].shape == (64, 64, 3)
            assert received_frames[0][0, 0, 0] == 10
            assert received_frames[1][0, 0, 0] == 20
            assert received_frames[2][0, 0, 0] == 30

    @pytest.mark.asyncio
    async def test_streaming_with_simulated_numpy_arrays(self, sample_camera: CameraConfig) -> None:
        """Assert that generator yielding raw numpy arrays is supported directly."""
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_container.streams.video = [mock_stream]

        raw_frame = np.ones((32, 32, 3), dtype=np.uint8) * 255
        mock_container.decode.return_value = iter([raw_frame])

        worker = StreamWorker(sample_camera, initial_backoff=0.01, max_backoff=0.05)
        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            frame = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
            await worker.stop()
            await task

            assert np.array_equal(frame, raw_frame)

    @pytest.mark.asyncio
    async def test_streaming_with_local_video_file(
        self, tmp_path: Path, sample_camera: CameraConfig
    ) -> None:
        """Assert stream ingestor functions end-to-end with real local video."""
        video_path = tmp_path / "test_feed.mp4"
        create_temp_video_file(video_path, num_frames=4, width=48, height=48)

        local_camera = CameraConfig(
            name="local_cam",
            rtsp_url=str(video_path),
            fps=10,
        )
        worker = StreamWorker(local_camera, initial_backoff=0.01, max_backoff=0.05)

        task = asyncio.create_task(worker.start())
        f1 = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
        assert isinstance(f1, np.ndarray)
        assert f1.shape == (48, 48, 3)

        await worker.stop()
        await task

    @pytest.mark.asyncio
    async def test_reconnection_logic_on_open_error(self, sample_camera: CameraConfig) -> None:
        """Assert that reconnection logic triggers on mock AVError and backs off."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=0.01,
            max_backoff=0.04,
            backoff_factor=2.0,
        )

        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_frame = create_mock_video_frame(color=77)
        mock_container.decode.return_value = iter([mock_frame])

        av_error = getattr(av, "AVError", av.FFmpegError)(1, "Simulated RTSP connection failure")

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First two attempts fail with AVError
                raise av_error
            # Third attempt succeeds
            return mock_container

        with patch("av.open", side_effect=side_effect):
            task = asyncio.create_task(worker.start())
            frame = await asyncio.wait_for(worker.queue.get(), timeout=3.0)
            assert frame[0, 0, 0] == 77
            assert call_count >= 3

            # Reconnection logic resets backoff after successful frame reception
            assert worker.current_backoff == worker.initial_backoff

            await worker.stop()
            await task

    @pytest.mark.asyncio
    async def test_exponential_backoff_and_capping(self, sample_camera: CameraConfig) -> None:
        """Assert that exponential backoff doubles and is capped at max_backoff."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=0.01,
            max_backoff=0.035,
            backoff_factor=2.0,
        )

        av_error = getattr(av, "AVError", av.FFmpegError)(1, "Persistent failure")
        attempts = 0

        def side_effect(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise av_error

        with patch("av.open", side_effect=side_effect):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.15)
            await worker.stop()
            await task

            assert attempts >= 3
            # Should be capped at max_backoff
            assert worker.current_backoff == 0.035

    @pytest.mark.asyncio
    async def test_reconnection_on_read_failure(self, sample_camera: CameraConfig) -> None:
        """Assert that read failure during frame decoding triggers reconnection."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=0.01,
            max_backoff=0.04,
            backoff_factor=2.0,
        )

        # Container 1: yields 1 frame, then raises error
        container1 = MagicMock()
        container1.streams.video = [MagicMock()]
        frame1 = create_mock_video_frame(color=11)

        def failing_gen():
            yield frame1
            raise av.FFmpegError(1, "Corrupted packet or network disconnect")

        container1.decode.return_value = failing_gen()

        # Container 2: yields 1 frame
        container2 = MagicMock()
        container2.streams.video = [MagicMock()]
        frame2 = create_mock_video_frame(color=22)
        container2.decode.return_value = iter([frame2])

        containers = [container1, container2]

        with patch(
            "av.open", side_effect=lambda *a, **k: containers.pop(0) if containers else MagicMock()
        ):
            task = asyncio.create_task(worker.start())

            f1 = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
            assert f1[0, 0, 0] == 11

            f2 = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
            assert f2[0, 0, 0] == 22

            await worker.stop()
            await task

    @pytest.mark.asyncio
    async def test_no_video_stream_triggers_reconnect(self, sample_camera: CameraConfig) -> None:
        """Assert container with no video streams triggers reconnect error handling."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=0.01,
            max_backoff=0.04,
        )

        container_no_video = MagicMock()
        container_no_video.streams.video = []

        container_with_video = MagicMock()
        container_with_video.streams.video = [MagicMock()]
        frame = create_mock_video_frame(color=99)
        container_with_video.decode.return_value = iter([frame])

        containers = [container_no_video, container_with_video]

        with patch(
            "av.open", side_effect=lambda *a, **k: containers.pop(0) if containers else MagicMock()
        ):
            task = asyncio.create_task(worker.start())
            f = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
            assert f[0, 0, 0] == 99
            await worker.stop()
            await task

    @pytest.mark.asyncio
    async def test_clean_teardown_during_long_backoff(self, sample_camera: CameraConfig) -> None:
        """Assert worker teardown completes promptly without waiting for long backoff sleep."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=60.0,
            max_backoff=60.0,
        )

        with patch("av.open", side_effect=av.FFmpegError(1, "Connection refused")):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.05)

            start_time = asyncio.get_running_loop().time()
            await worker.stop()
            await task
            elapsed = asyncio.get_running_loop().time() - start_time

            assert elapsed < 1.0
            assert not worker.is_running

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, sample_camera: CameraConfig) -> None:
        """Assert calling start when worker is already running is a safe no-op."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_container.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            assert worker.is_running

            await worker.start()

            await worker.stop()
            await task

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self, sample_camera: CameraConfig) -> None:
        """Assert calling stop on an unstarted worker is safe."""
        worker = StreamWorker(sample_camera)
        await worker.stop()
        assert not worker.is_running


# ===========================================================================
# MotionFilter Unit Tests
# ===========================================================================


class TestMotionFilter:
    """Test suite for MotionFilter."""

    def test_motion_filter_initialization(self, sample_camera: CameraConfig) -> None:
        """Test default and custom configuration."""
        mf_default = MotionFilter()
        assert mf_default.threshold == 0.005
        assert mf_default.history == 500
        assert mf_default.var_threshold == 16.0
        assert not mf_default.detect_shadows

        mf_camera = MotionFilter.from_camera(sample_camera)
        assert mf_camera.threshold == 0.005

        mf_custom = MotionFilter(
            threshold=0.02,
            history=300,
            var_threshold=25.0,
            detect_shadows=True,
        )
        assert mf_custom.threshold == 0.02
        assert mf_custom.history == 300
        assert mf_custom.var_threshold == 25.0
        assert mf_custom.detect_shadows

    def test_empty_and_none_frames(self) -> None:
        """Assert None and empty frames return False and 0.0 ratio."""
        mf = MotionFilter()
        assert not mf.has_motion(None)
        assert mf.calculate_motion_ratio(None) == 0.0

        empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
        assert not mf.has_motion(empty_frame)
        assert mf.calculate_motion_ratio(empty_frame) == 0.0

    def test_motion_detection_logic(self) -> None:
        """
        Assert motion is detected only when foreground fraction exceeds threshold.

        Default threshold: 0.005 (0.5% of pixels).
        """
        mf = MotionFilter(threshold=0.005)
        h, w = 100, 100

        base_frame = np.full((h, w, 3), fill_value=50, dtype=np.uint8)

        # Feed static frames to build the background model
        for _ in range(5):
            mf.has_motion(base_frame)

        # 1. Identical frame -> No motion
        static_frame = base_frame.copy()
        assert not mf.has_motion(static_frame)
        assert mf.calculate_motion_ratio(static_frame, update_model=False) == 0.0

        # 2. Large motion: 20x20 white patch = 400 pixels = 4.0% > 0.5%
        motion_frame = base_frame.copy()
        motion_frame[40:60, 40:60] = 255
        ratio = mf.calculate_motion_ratio(motion_frame, update_model=False)
        assert ratio > 0.005
        assert mf.has_motion(motion_frame)

        # 3. Reset background model
        mf.reset()
        for _ in range(5):
            mf.has_motion(base_frame)

        # 4. Tiny change: 4x4 patch = 16 pixels = 0.16% < 0.5%
        tiny_motion_frame = base_frame.copy()
        tiny_motion_frame[40:44, 40:44] = 255
        tiny_ratio = mf.calculate_motion_ratio(tiny_motion_frame, update_model=False)
        assert tiny_ratio < 0.005
        assert not mf.has_motion(tiny_motion_frame)

    def test_configurable_threshold(self) -> None:
        """Assert motion filter respects custom thresholds."""
        h, w = 100, 100
        base_frame = np.full((h, w, 3), fill_value=30, dtype=np.uint8)

        test_frame = base_frame.copy()
        test_frame[45:55, 45:55] = 255  # 100 pixels = 1%

        # Strict filter: 2% threshold -> 1% motion should return False
        strict_mf = MotionFilter(threshold=0.02)
        for _ in range(5):
            strict_mf.has_motion(base_frame)
        assert not strict_mf.has_motion(test_frame)

        # Sensitive filter: 0.2% threshold -> 1% motion should return True
        sensitive_mf = MotionFilter(threshold=0.002)
        for _ in range(5):
            sensitive_mf.has_motion(base_frame)
        assert sensitive_mf.has_motion(test_frame)

    @pytest.mark.asyncio
    async def test_motion_filter_async(self) -> None:
        """Assert async motion check executes in executor without blocking."""
        mf = MotionFilter(threshold=0.005)
        h, w = 100, 100
        base_frame = np.full((h, w, 3), fill_value=40, dtype=np.uint8)

        for _ in range(5):
            await mf.has_motion_async(base_frame)

        motion_frame = base_frame.copy()
        motion_frame[30:70, 30:70] = 255
        has_motion = await mf.has_motion_async(motion_frame)
        assert has_motion is True

    def test_motion_filter_shadow_detection(self) -> None:
        """Assert motion filter works with detect_shadows=True."""
        mf = MotionFilter(threshold=0.005, detect_shadows=True)
        base = np.zeros((100, 100, 3), dtype=np.uint8)
        for _ in range(5):
            mf.has_motion(base)

        motion_frame = base.copy()
        motion_frame[30:70, 30:70] = 255
        assert mf.has_motion(motion_frame)

    def test_motion_filter_zero_dimension(self) -> None:
        """Assert zero-dimension frames return 0.0 ratio."""
        mf = MotionFilter()
        zero_w = np.zeros((10, 0, 3), dtype=np.uint8)
        assert not mf.has_motion(zero_w)
        assert mf.calculate_motion_ratio(zero_w) == 0.0


# ===========================================================================
# StreamWorker Edge Case Tests
# ===========================================================================


class TestStreamWorkerEdgeCases:
    """Edge cases and failure paths for StreamWorker."""

    def test_push_frame_concurrent_queue_full(self, sample_camera: CameraConfig) -> None:
        """Assert push_frame recovers when put_nowait raises QueueFull."""
        worker = StreamWorker(sample_camera, queue=asyncio.Queue(maxsize=1))
        f1 = np.ones((5, 5, 3), dtype=np.uint8)
        f2 = np.ones((5, 5, 3), dtype=np.uint8) * 2

        worker.push_frame(f1)
        # Force a QueueFull scenario on put_nowait
        orig_put = worker.queue.put_nowait
        call_count = 0

        def flaky_put(item):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.QueueFull
            return orig_put(item)

        with patch.object(worker.queue, "put_nowait", side_effect=flaky_put):
            worker.push_frame(f2)

        res = worker.queue.get_nowait()
        assert np.array_equal(res, f2)

    @pytest.mark.asyncio
    async def test_worker_task_cancellation(self, sample_camera: CameraConfig) -> None:
        """Assert worker handles task cancellation cleanly."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_container.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not worker.is_running

    @pytest.mark.asyncio
    async def test_decode_next_fallback_to_asarray(self, sample_camera: CameraConfig) -> None:
        """Assert _decode_next converts non-ndarray objects without to_ndarray."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]

        # Object that has no to_ndarray but is convertible with np.asarray (e.g. list of lists)
        custom_frame = [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]]
        mock_container.decode.return_value = iter([custom_frame])

        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            frame = await asyncio.wait_for(worker.queue.get(), timeout=2.0)
            await worker.stop()
            await task

            assert isinstance(frame, np.ndarray)
            assert frame.shape == (2, 2, 3)

    @pytest.mark.asyncio
    async def test_stop_timeout_cancels_task(self, sample_camera: CameraConfig) -> None:
        """Assert stop() cancels a stubborn task if it exceeds timeout."""
        worker = StreamWorker(sample_camera)
        worker._running = True
        mock_container = MagicMock()
        worker._container = mock_container

        async def stubborn_loop():
            try:
                while True:
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass
            finally:
                worker._running = False

        task = asyncio.create_task(stubborn_loop())
        worker._task = task

        # Call stop with short timeout to trigger TimeoutError and task cancellation
        await worker.stop(timeout=0.01)

        assert not worker.is_running
        assert worker._container is None
        mock_container.close.assert_called_once()

    def test_close_container_safely_handles_exceptions(self) -> None:
        """Assert _close_container catches any exception during close."""
        bad_container = MagicMock()
        bad_container.close.side_effect = RuntimeError("Broken container")
        # Should not raise
        StreamWorker._close_container(bad_container)
        StreamWorker._close_container(None)


# ===========================================================================
# StreamWorker Robustness & Adversarial Tests
# ===========================================================================


class TestStreamWorkerRobustness:
    """Stress tests, validation, and leak prevention for StreamWorker."""

    def test_worker_init_validation(self, sample_camera: CameraConfig) -> None:
        """Assert StreamWorker validates constructor arguments defensively."""
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            StreamWorker(sample_camera, initial_backoff=0.0)
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            StreamWorker(sample_camera, initial_backoff=-1.0)
        with pytest.raises(ValueError, match="max_backoff .* cannot be less than initial_backoff"):
            StreamWorker(sample_camera, initial_backoff=10.0, max_backoff=5.0)
        with pytest.raises(ValueError, match="backoff_factor must be >= 1.0"):
            StreamWorker(sample_camera, backoff_factor=0.5)
        with pytest.raises(ValueError, match="stimeout_us must be positive"):
            StreamWorker(sample_camera, stimeout_us=0)

    def test_push_frame_invalid_frames_ignored(self, sample_camera: CameraConfig) -> None:
        """Assert push_frame rejects None, non-ndarray, and empty arrays."""
        worker = StreamWorker(sample_camera)
        worker.push_frame(None)  # type: ignore
        worker.push_frame("not a numpy array")  # type: ignore
        worker.push_frame(np.zeros((0, 0, 3)))
        assert worker.queue.empty()

    @pytest.mark.asyncio
    async def test_push_frame_task_done_decremented_on_drop(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert dropped frames call task_done so queue.join() does not hang."""
        queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=2)
        worker = StreamWorker(sample_camera, queue=queue)

        # Push 4 frames: 2 will be dropped, 2 will remain
        for i in range(4):
            worker.push_frame(np.full((5, 5, 3), i, dtype=np.uint8))

        assert queue.qsize() == 2

        # Consume the 2 remaining frames and call task_done
        for _ in range(2):
            queue.get_nowait()
            queue.task_done()

        # queue.join() should return immediately without deadlock
        await asyncio.wait_for(queue.join(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_direct_task_cancellation_cleans_up_executor(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert cancelling worker task directly shuts down and cleans executor."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_container.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            assert worker.is_running
            assert worker._executor is not None

            # Cancel task directly from outside without calling worker.stop()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            assert not worker.is_running
            # Executor should be cleaned up, not leaked
            assert worker._executor is None

    @pytest.mark.asyncio
    async def test_network_flapping_stress(self, sample_camera: CameraConfig) -> None:
        """Stress test: rapid network flapping (drops every few ms) handled cleanly."""
        worker = StreamWorker(
            sample_camera,
            initial_backoff=0.001,
            max_backoff=0.005,
            backoff_factor=1.5,
        )

        flap_count = 0
        av_err = getattr(av, "AVError", av.FFmpegError)(1, "Flapping network error")

        def flappy_open(*args, **kwargs):
            nonlocal flap_count
            flap_count += 1
            if flap_count % 2 == 0:
                raise av_err
            mc = MagicMock()
            mc.streams.video = [MagicMock()]
            mc.decode.side_effect = av_err
            return mc

        with patch("av.open", side_effect=flappy_open):
            task = asyncio.create_task(worker.start())
            await asyncio.sleep(0.1)
            await worker.stop()
            await task

        assert flap_count >= 5
        assert not worker.is_running
        assert worker._executor is None

    @pytest.mark.asyncio
    async def test_worker_restart_lifecycle(self, sample_camera: CameraConfig) -> None:
        """Assert worker can be cleanly stopped and restarted repeatedly."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_c = MagicMock()
        mock_c.streams.video = [MagicMock()]
        mock_c.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_c):
            # Run 1
            t1 = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            await worker.stop()
            await t1
            assert not worker.is_running
            assert worker._executor is None

            # Run 2
            t2 = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            await worker.stop()
            await t2
            assert not worker.is_running
            assert worker._executor is None

    @pytest.mark.asyncio
    async def test_concurrent_stops(self, sample_camera: CameraConfig) -> None:
        """Assert multiple concurrent calls to stop() are safe and idempotent."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_c = MagicMock()
        mock_c.streams.video = [MagicMock()]
        mock_c.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_c):
            t = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            # Call stop concurrently 3 times
            await asyncio.gather(worker.stop(), worker.stop(), worker.stop())
            await t
            assert not worker.is_running
            assert worker._executor is None

    @pytest.mark.asyncio
    async def test_decode_next_handles_none_from_generator(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert _decode_next gracefully handles generator returning None."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_c = MagicMock()
        mock_c.streams.video = [MagicMock()]
        # Yield None, which signals EOF
        mock_c.decode.return_value = iter([None])

        with patch("av.open", return_value=mock_c):
            t = asyncio.create_task(worker.start())
            await asyncio.sleep(0.03)
            await worker.stop()
            await t
            assert not worker.is_running


# ===========================================================================
# MotionFilter Edge Case & Type Tests
# ===========================================================================


class TestMotionFilterEdgeCasesAndTypes:
    """Validation, diverse dtypes, dimensions, and concurrency for MotionFilter."""

    def test_motion_filter_init_validation(self) -> None:
        """Assert MotionFilter validates parameters defensively."""
        with pytest.raises(ValueError, match="Motion threshold must be between 0.0 and 1.0"):
            MotionFilter(threshold=-0.01)
        with pytest.raises(ValueError, match="Motion threshold must be between 0.0 and 1.0"):
            MotionFilter(threshold=1.05)
        with pytest.raises(ValueError, match="History must be positive"):
            MotionFilter(history=0)
        with pytest.raises(ValueError, match="History must be positive"):
            MotionFilter(history=-10)
        with pytest.raises(ValueError, match="var_threshold must be positive"):
            MotionFilter(var_threshold=0.0)

    def test_motion_filter_1d_array_gracefully_rejected(self) -> None:
        """Assert 1D arrays are safely rejected with 0.0 without IndexError."""
        mf = MotionFilter()
        arr_1d = np.array([1, 2, 3, 4, 5])
        assert mf.calculate_motion_ratio(arr_1d) == 0.0
        assert not mf.has_motion(arr_1d)

    def test_motion_filter_4d_batch_array_supported(self) -> None:
        """Assert 4D batch array (1, H, W, C) is supported via squeezing."""
        mf = MotionFilter(threshold=0.005)
        base = np.full((1, 80, 80, 3), 40, dtype=np.uint8)
        for _ in range(5):
            mf.has_motion(base)

        motion_batch = base.copy()
        motion_batch[0, 20:60, 20:60] = 255
        assert mf.has_motion(motion_batch)

    def test_motion_filter_higher_dimensional_array_rejected(self) -> None:
        """Assert arrays with ndim > 4 or batch size > 1 are safely rejected."""
        mf = MotionFilter()
        arr_multi_batch = np.zeros((2, 50, 50, 3), dtype=np.uint8)
        assert mf.calculate_motion_ratio(arr_multi_batch) == 0.0

        arr_5d = np.zeros((1, 1, 50, 50, 3), dtype=np.uint8)
        assert mf.calculate_motion_ratio(arr_5d) == 0.0

    def test_motion_filter_object_and_non_numeric_array_rejected(self) -> None:
        """Assert object arrays (e.g. np.array(None)) are safely rejected."""
        mf = MotionFilter()
        assert mf.calculate_motion_ratio(np.array(None)) == 0.0
        assert mf.calculate_motion_ratio(np.array(["a", "b", "c"])) == 0.0
        # 2D non-numeric array
        assert mf.calculate_motion_ratio(np.array([["a", "b"], ["c", "d"]])) == 0.0

    def test_motion_filter_float_arrays_supported(self) -> None:
        """Assert float arrays (normalized 0.0-1.0 and 0.0-255.0) are supported."""
        mf = MotionFilter(threshold=0.005)
        base_norm = np.full((60, 60, 3), 0.2, dtype=np.float32)
        for _ in range(5):
            mf.has_motion(base_norm)

        motion_norm = base_norm.copy()
        motion_norm[15:45, 15:45] = 1.0
        assert mf.has_motion(motion_norm)

        # Float in 0-255 range
        base_255 = np.full((60, 60, 3), 50.0, dtype=np.float32)
        for _ in range(5):
            mf.has_motion(base_255)
        motion_255 = base_255.copy()
        motion_255[15:45, 15:45] = 250.0
        assert mf.has_motion(motion_255)

    def test_motion_filter_integer_arrays_supported(self) -> None:
        """Assert int32 and int16 arrays are clipped to uint8 and supported."""
        mf = MotionFilter(threshold=0.005)
        base_int = np.full((60, 60, 3), 30, dtype=np.int32)
        for _ in range(5):
            mf.has_motion(base_int)

        motion_int = base_int.copy()
        motion_int[15:45, 15:45] = 255
        assert mf.has_motion(motion_int)

    @pytest.mark.asyncio
    async def test_motion_filter_concurrent_thread_safety(self) -> None:
        """Assert concurrent async motion checks are thread-safe without corrupting state."""
        mf = MotionFilter(threshold=0.005)
        frame = np.full((60, 60, 3), 50, dtype=np.uint8)

        async def worker_task():
            for _ in range(20):
                await mf.has_motion_async(frame)

        # 5 tasks running concurrently
        await asyncio.gather(*[worker_task() for _ in range(5)])

    def test_motion_filter_nan_inf_validation(self) -> None:
        """Assert MotionFilter rejects NaN and Inf parameters defensively."""
        with pytest.raises(ValueError):
            MotionFilter(threshold=float("nan"))
        with pytest.raises(ValueError):
            MotionFilter(threshold=float("inf"))
        with pytest.raises(ValueError):
            MotionFilter(var_threshold=float("nan"))
        with pytest.raises(ValueError):
            MotionFilter(var_threshold=float("inf"))

    def test_motion_filter_from_camera_kwargs_override(self, sample_camera: CameraConfig) -> None:
        """Assert MotionFilter.from_camera allows overriding threshold via kwargs."""
        mf = MotionFilter.from_camera(sample_camera, threshold=0.02)
        assert mf.threshold == 0.02

    def test_motion_filter_513_channels_gracefully_rejected(self) -> None:
        """Assert 3D array exceeding OpenCV's 512 channel limit is rejected without crash."""
        mf = MotionFilter()
        arr_513 = np.zeros((10, 10, 513), dtype=np.uint8)
        assert mf.calculate_motion_ratio(arr_513) == 0.0
        assert not mf.has_motion(arr_513)

    def test_motion_filter_float_array_with_nan_inf_rejected(self) -> None:
        """Assert float array with NaN or Inf returns 0.0 without RuntimeWarning."""
        mf = MotionFilter()
        nan_frame = np.full((20, 20, 3), np.nan, dtype=np.float32)
        assert mf.calculate_motion_ratio(nan_frame) == 0.0
        assert not mf.has_motion(nan_frame)

        inf_frame = np.full((20, 20, 3), np.inf, dtype=np.float32)
        assert mf.calculate_motion_ratio(inf_frame) == 0.0
        assert not mf.has_motion(inf_frame)

    def test_motion_filter_boolean_array_supported(self) -> None:
        """Assert boolean arrays are converted and supported."""
        mf = MotionFilter(threshold=0.005)
        base_bool = np.zeros((50, 50), dtype=bool)
        for _ in range(5):
            mf.has_motion(base_bool)

        motion_bool = base_bool.copy()
        motion_bool[10:30, 10:30] = True
        assert mf.has_motion(motion_bool)

    def test_motion_filter_detect_shadows_type_validation(self) -> None:
        """Assert detect_shadows must be a boolean."""
        with pytest.raises(TypeError, match="detect_shadows must be a boolean"):
            MotionFilter(detect_shadows="true")  # type: ignore[arg-type]

    def test_motion_filter_from_camera_type_validation(self) -> None:
        """Assert from_camera requires a CameraConfig instance."""
        with pytest.raises(TypeError, match="camera must be a CameraConfig"):
            MotionFilter.from_camera("not_a_camera")  # type: ignore[arg-type]

    def test_motion_filter_boolean_args_rejected(self) -> None:
        """Assert booleans are rejected for threshold, history, and var_threshold."""
        with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
            MotionFilter(threshold=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="History must be positive"):
            MotionFilter(history=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="var_threshold must be positive"):
            MotionFilter(var_threshold=True)  # type: ignore[arg-type]


# ===========================================================================
# StreamWorker Adversarial & Concurrency Tests
# ===========================================================================


class TestStreamWorkerAdversarial:
    """Additional adversarial and boundary tests for StreamWorker."""

    def test_stream_worker_invalid_camera_type(self) -> None:
        """Assert StreamWorker rejects invalid camera types."""
        with pytest.raises(TypeError, match="camera must be a CameraConfig"):
            StreamWorker(None)  # type: ignore
        with pytest.raises(TypeError, match="camera must be a CameraConfig"):
            StreamWorker("rtsp://localhost/live")  # type: ignore

    def test_stream_worker_nan_inf_backoff_validation(self, sample_camera: CameraConfig) -> None:
        """Assert StreamWorker rejects NaN and Inf backoff parameters."""
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            StreamWorker(sample_camera, initial_backoff=float("nan"))
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            StreamWorker(sample_camera, initial_backoff=float("inf"))
        with pytest.raises(ValueError, match="max_backoff .* cannot be less than initial_backoff"):
            StreamWorker(sample_camera, initial_backoff=5.0, max_backoff=float("nan"))
        with pytest.raises(ValueError, match="backoff_factor must be >= 1.0"):
            StreamWorker(sample_camera, backoff_factor=float("nan"))
        with pytest.raises(ValueError, match="backoff_factor must be >= 1.0"):
            StreamWorker(sample_camera, backoff_factor=float("inf"))

    def test_stream_worker_push_frame_dimension_validation(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert push_frame rejects invalid dimension arrays."""
        worker = StreamWorker(sample_camera)
        # 1D array
        worker.push_frame(np.array([1, 2, 3]))
        assert worker.queue.empty()
        # 0D array
        worker.push_frame(np.array(42))
        assert worker.queue.empty()
        # 4D array
        worker.push_frame(np.zeros((1, 10, 10, 3)))
        assert worker.queue.empty()
        # 3D with 0 channels or >512 channels
        worker.push_frame(np.zeros((10, 10, 0)))
        assert worker.queue.empty()
        worker.push_frame(np.zeros((10, 10, 513)))
        assert worker.queue.empty()

    def test_stream_worker_substream_selection(self) -> None:
        """Assert use_substream selects rtsp_sub_url when available."""
        cam_with_sub = CameraConfig(
            name="cam_sub",
            rtsp_url="rtsp://main/stream",
            rtsp_sub_url="rtsp://sub/stream",
        )
        worker_main = StreamWorker(cam_with_sub, use_substream=False)
        assert worker_main.stream_url == "rtsp://main/stream"

        worker_sub = StreamWorker(cam_with_sub, use_substream=True)
        assert worker_sub.stream_url == "rtsp://sub/stream"

        # Fallback to main URL when rtsp_sub_url is None
        cam_no_sub = CameraConfig(
            name="cam_no_sub",
            rtsp_url="rtsp://main/stream",
            rtsp_sub_url=None,
        )
        worker_fallback = StreamWorker(cam_no_sub, use_substream=True)
        assert worker_fallback.stream_url == "rtsp://main/stream"

    @pytest.mark.asyncio
    async def test_stream_worker_concurrent_starts(self, sample_camera: CameraConfig) -> None:
        """Assert concurrent calls to start() are guarded and do not create duplicate executors."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_container.decode.return_value = iter([create_mock_video_frame()])

        with patch("av.open", return_value=mock_container):
            t1 = asyncio.create_task(worker.start())
            t2 = asyncio.create_task(worker.start())
            await asyncio.sleep(0.02)
            assert worker.is_running
            await worker.stop()
            await t1
            await t2
            assert not worker.is_running

    def test_stream_worker_boolean_args_rejected(self, sample_camera: CameraConfig) -> None:
        """Assert boolean values are rejected for numeric parameters."""
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            StreamWorker(sample_camera, initial_backoff=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="max_backoff .* cannot be less than initial_backoff"):
            StreamWorker(sample_camera, max_backoff=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="backoff_factor must be >= 1.0"):
            StreamWorker(sample_camera, backoff_factor=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="stimeout_us must be positive"):
            StreamWorker(sample_camera, stimeout_us=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_stream_worker_stop_timeout_validation(self, sample_camera: CameraConfig) -> None:
        """Assert invalid timeout values in stop() raise ValueError."""
        worker = StreamWorker(sample_camera)
        with pytest.raises(ValueError, match="timeout must be a non-negative finite number"):
            await worker.stop(timeout=-1.0)
        with pytest.raises(ValueError, match="timeout must be a non-negative finite number"):
            await worker.stop(timeout=float("nan"))
        with pytest.raises(ValueError, match="timeout must be a non-negative finite number"):
            await worker.stop(timeout=float("inf"))
        with pytest.raises(ValueError, match="timeout must be a non-negative finite number"):
            await worker.stop(timeout=True)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_stream_worker_stop_during_open(self, sample_camera: CameraConfig) -> None:
        """Assert stopping while av.open is executing closes the opened container cleanly."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]
        mock_container.decode.return_value = iter([create_mock_video_frame()])

        open_started = asyncio.Event()

        def slow_open(*args: Any, **kwargs: Any) -> Any:
            open_started.set()
            # Simulate worker._running set to False before open completes
            worker._running = False
            return mock_container

        with patch("av.open", side_effect=slow_open):
            task = asyncio.create_task(worker.start())
            await open_started.wait()
            await task
            assert not worker.is_running
            # Allow thread executor to complete scheduled close
            await asyncio.sleep(0.05)
            mock_container.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_worker_stop_stubborn_task_with_active_executor(
        self, sample_camera: CameraConfig
    ) -> None:
        """Assert stop() with stubborn task and active executor submits close to executor."""
        worker = StreamWorker(sample_camera, initial_backoff=0.01)
        mock_container = MagicMock()
        mock_container.streams.video = [MagicMock()]

        def hanging_gen():
            yield create_mock_video_frame()
            import time

            time.sleep(0.2)
            yield create_mock_video_frame()

        mock_container.decode.return_value = hanging_gen()

        with patch("av.open", return_value=mock_container):
            task = asyncio.create_task(worker.start())
            # Wait until worker is running and processing
            await asyncio.sleep(0.05)
            assert worker.is_running
            assert worker._executor is not None

            # Stop with small timeout so worker task cancellation triggers while thread is sleeping
            await worker.stop(timeout=0.02)
            assert not worker.is_running
            with pytest.raises(asyncio.CancelledError):
                await task
