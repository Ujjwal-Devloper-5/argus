"""
Unit tests for EventRecorder (argus/core/recorder.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from argus.core.recorder import (
    EventRecorder,
    build_ffmpeg_command,
    check_nvenc_support,
    is_nvenc_available,
    normalize_frame,
    reset_nvenc_cache,
)


class TestHardwareAccelerationDetection:
    def test_check_nvenc_support_probe(self) -> None:
        reset_nvenc_cache()
        result = check_nvenc_support(probe_timeout=2.0)
        assert isinstance(result, bool)

    def test_is_nvenc_available_resolution_constraints(self) -> None:
        reset_nvenc_cache()
        # Too small width or height
        assert is_nvenc_available(width=64, height=64) is False
        assert is_nvenc_available(width=144, height=144) is False
        assert is_nvenc_available(width=640, height=30) is False

        # Odd dimensions
        assert is_nvenc_available(width=255, height=256) is False
        assert is_nvenc_available(width=256, height=255) is False

    @patch("argus.core.recorder.check_nvenc_support", return_value=True)
    def test_is_nvenc_available_when_supported(self, mock_probe: MagicMock) -> None:
        assert is_nvenc_available(width=640, height=480) is True
        assert is_nvenc_available(width=1280, height=720) is True
        assert is_nvenc_available(width=1920, height=1080) is True

    @patch("argus.core.recorder.check_nvenc_support", return_value=False)
    def test_is_nvenc_available_when_unsupported(self, mock_probe: MagicMock) -> None:
        assert is_nvenc_available(width=640, height=480) is False

    def test_reset_nvenc_cache(self) -> None:
        with patch("argus.core.recorder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_nvenc_cache()
            res1 = check_nvenc_support()
            res2 = check_nvenc_support()
            assert res1 is True
            assert res2 is True
            assert mock_run.call_count == 1

            reset_nvenc_cache()
            _ = check_nvenc_support()
            assert mock_run.call_count == 2


class TestBuildFFmpegCommand:
    def test_build_ffmpeg_command_libx264(self) -> None:
        cmd = build_ffmpeg_command(
            output_path="/tmp/test.mp4",
            width=640,
            height=480,
            fps=15,
            codec="libx264",
        )
        assert isinstance(cmd, list)
        assert cmd[0] == "ffmpeg"
        assert "-s" in cmd
        assert "640x480" in cmd
        assert "libx264" in cmd
        assert "ultrafast" in cmd
        assert "yuv420p" in cmd
        assert "+faststart" in cmd

    def test_build_ffmpeg_command_h264_nvenc(self) -> None:
        cmd = build_ffmpeg_command(
            output_path="/tmp/test_nv.mp4",
            width=1280,
            height=720,
            fps=30,
            codec="h264_nvenc",
        )
        assert isinstance(cmd, list)
        assert cmd[0] == "ffmpeg"
        assert "1280x720" in cmd
        assert "h264_nvenc" in cmd


class TestEventRecorderInitAndProperties:
    def test_default_init(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        assert rec.output_dir == tmp_path
        assert rec.fps == 15
        assert rec.is_recording is False
        assert rec.frame_count == 0
        assert rec.current_output_path is None

    def test_custom_init(self, tmp_path: Path) -> None:
        rec = EventRecorder(
            output_dir=tmp_path / "custom",
            fps=25,
            codec="libx264",
            camera_name="Driveway_1",
            prefix="ALERT",
        )
        assert rec.output_dir == tmp_path / "custom"
        assert rec.fps == 25
        assert rec._requested_codec == "libx264"
        assert rec._camera_name == "driveway_1"
        assert rec._prefix == "ALERT"

    def test_invalid_fps_raises(self) -> None:
        with pytest.raises(ValueError, match="fps must be positive"):
            EventRecorder(fps=0)
        with pytest.raises(ValueError, match="fps must be positive"):
            EventRecorder(fps=-10)


class TestEventRecorderValidation:
    async def test_add_frame_when_not_recording_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(RuntimeError, match="no recording in progress"):
            await rec.add_frame(frame)

    async def test_stop_recording_when_not_recording_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        with pytest.raises(RuntimeError, match="no recording in progress"):
            await rec.stop_recording()

    async def test_start_recording_when_already_recording_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path, codec="libx264")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])
        assert rec.is_recording is True

        with pytest.raises(RuntimeError, match="already in progress"):
            await rec.start_recording([frame])

        # Clean up
        await rec.stop_recording()

    async def test_invalid_pre_event_frames_type_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        with pytest.raises(TypeError, match="not a numpy ndarray"):
            await rec.start_recording(["invalid"])  # type: ignore[list-item]

    async def test_invalid_add_frame_type_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path, codec="libx264")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])

        with pytest.raises(TypeError, match="Expected frame of type np.ndarray"):
            await rec.add_frame("not a numpy array")  # type: ignore[arg-type]

        await rec.stop_recording()

    async def test_stop_recording_with_zero_frames_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        await rec.start_recording([])
        with pytest.raises(ValueError, match="No frames were recorded"):
            await rec.stop_recording()
        assert rec.is_recording is False

    async def test_cancel_recording(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path, codec="libx264")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])
        assert rec.is_recording is True
        out_path = rec.current_output_path

        await rec.cancel_recording()
        assert rec.is_recording is False
        assert rec.frame_count == 0
        if out_path:
            assert not out_path.exists()

    async def test_cancel_recording_when_not_recording(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        await rec.cancel_recording()  # should not raise
        assert rec.is_recording is False


class TestEventRecorderIntegration:
    async def test_stitch_five_frames_end_to_end(self, tmp_path: Path) -> None:
        """
        Verify EventRecorder successfully stitches numpy arrays into a readable video file
        using a tiny 5-frame test (2 pre-event frames + 3 live frames).
        """
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")

        # 2 pre-event frames (256x256 BGR)
        pre_frames = [
            np.full((256, 256, 3), 40, dtype=np.uint8),
            np.full((256, 256, 3), 80, dtype=np.uint8),
        ]

        await rec.start_recording(pre_frames)
        assert rec.is_recording is True
        assert rec.frame_count == 2

        # 3 incoming live frames
        for val in [120, 160, 200]:
            live_frame = np.full((256, 256, 3), val, dtype=np.uint8)
            await rec.add_frame(live_frame)

        assert rec.frame_count == 5

        video_path = await rec.stop_recording()
        assert rec.is_recording is False
        assert Path(video_path).exists()
        assert Path(video_path).stat().st_size > 0
        assert "EVENT_" in Path(video_path).name
        assert Path(video_path).name.endswith(".mp4")

        # Verify readability with OpenCV VideoCapture
        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened(), f"Could not open stitched video {video_path}"
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        assert total_frames == 5
        assert w == 256
        assert h == 256

    async def test_recording_with_empty_pre_event_frames(self, tmp_path: Path) -> None:
        """Test recording starting with empty pre_event_frames and adding frames live."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        await rec.start_recording([])
        assert rec.is_recording is True

        for i in range(4):
            frame = np.full((160, 160, 3), i * 50, dtype=np.uint8)
            await rec.add_frame(frame)

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()
        assert Path(video_path).stat().st_size > 0

        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        assert count == 4

    async def test_frame_resizing_on_dimension_mismatch(self, tmp_path: Path) -> None:
        """Verify frames with different dimensions are resized without breaking FFmpeg stream."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        initial_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        await rec.start_recording([initial_frame])

        # Add frame with different dimension (100x100 instead of 200x200)
        mismatched_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        await rec.add_frame(mismatched_frame)

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()
        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        assert count == 2

    async def test_camera_name_in_filename(self, tmp_path: Path) -> None:
        rec = EventRecorder(
            output_dir=tmp_path,
            fps=10,
            camera_name="front_door",
            prefix="EVENT",
            codec="libx264",
        )
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])
        video_path = await rec.stop_recording()

        assert "EVENT_front_door_" in Path(video_path).name

    async def test_sequential_recordings_on_same_instance(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")

        # Recording 1
        await rec.start_recording([np.zeros((160, 160, 3), dtype=np.uint8)])
        await rec.add_frame(np.zeros((160, 160, 3), dtype=np.uint8))
        path1 = await rec.stop_recording()
        assert Path(path1).exists()

        # Recording 2
        await rec.start_recording([np.zeros((160, 160, 3), dtype=np.uint8)])
        await rec.add_frame(np.zeros((160, 160, 3), dtype=np.uint8))
        path2 = await rec.stop_recording()
        assert Path(path2).exists()
        assert path1 != path2 or "_1.mp4" in path2


class TestEventRecorderFailover:
    async def test_failover_from_nvenc_to_libx264(self, tmp_path: Path) -> None:
        """
        Simulate an NVENC failure during stop_recording to verify graceful failover to libx264.
        """
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="h264_nvenc")
        frames = [np.full((200, 200, 3), i * 30, dtype=np.uint8) for i in range(5)]

        await rec.start_recording(frames[:2])
        for f in frames[2:]:
            await rec.add_frame(f)

        # Mock the primary process to report failure
        assert rec._proc is not None
        assert rec._proc._transport is not None  # type: ignore[attr-defined]
        rec._proc._transport.get_returncode = MagicMock(return_value=234)  # type: ignore[attr-defined]
        rec._actual_codec = "h264_nvenc"

        with patch.object(
            rec, "_fallback_encode_libx264", wraps=rec._fallback_encode_libx264
        ) as mock_fallback:
            video_path = await rec.stop_recording()
            mock_fallback.assert_called_once()
            assert Path(video_path).exists()
            assert Path(video_path).stat().st_size > 0

    async def test_nvenc_requested_with_small_resolution_falls_back_to_libx264(
        self, tmp_path: Path
    ) -> None:
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="h264_nvenc")
        small_frame = np.zeros((64, 64, 3), dtype=np.uint8)

        await rec.start_recording([small_frame])
        assert rec._actual_codec == "libx264"
        video_path = await rec.stop_recording()
        assert Path(video_path).exists()

    async def test_unrecoverable_ffmpeg_error_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])

        assert rec._proc is not None
        assert rec._proc._transport is not None  # type: ignore[attr-defined]
        rec._proc._transport.get_returncode = MagicMock(return_value=1)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="FFmpeg encoding failed"):
            await rec.stop_recording()


class TestAsyncNonBlocking:
    async def test_add_frame_is_non_blocking(self, tmp_path: Path) -> None:
        """Verify that add_frame queues the frame without blocking event loop."""
        rec = EventRecorder(output_dir=tmp_path, fps=15, codec="libx264")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)
        await rec.start_recording([frame])

        loop = asyncio.get_running_loop()
        t0 = loop.time()
        for _ in range(10):
            await rec.add_frame(frame)
        duration = loop.time() - t0

        # Adding 10 frames into queue should take much less than 50ms
        assert duration < 0.1

        await rec.stop_recording()


class TestAdversarialEdgeCases:
    async def test_grayscale_and_bgra_and_float_frames_recording(self, tmp_path: Path) -> None:
        """Verify 2D grayscale, 4-channel BGRA, and float32 frames are properly normalized and recorded."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")

        f_pre = np.full((100, 100, 3), 50, dtype=np.uint8)
        f_gray = np.full((100, 100), 100, dtype=np.uint8)
        f_bgra = np.full((100, 100, 4), 150, dtype=np.uint8)
        f_float = np.full((100, 100, 3), 0.8, dtype=np.float32)

        await rec.start_recording([f_pre])
        await rec.add_frame(f_gray)
        await rec.add_frame(f_bgra)
        await rec.add_frame(f_float)

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()

        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        assert count == 4
        assert w == 100
        assert h == 100

    async def test_concurrent_add_frame_on_empty_pre_event(self, tmp_path: Path) -> None:
        """Verify concurrent add_frame calls when _proc is None do not cause race conditions or leaks."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        await rec.start_recording([])

        frame1 = np.full((120, 120, 3), 50, dtype=np.uint8)
        frame2 = np.full((120, 120, 3), 100, dtype=np.uint8)

        # Concurrently add both frames
        await asyncio.gather(rec.add_frame(frame1), rec.add_frame(frame2))

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()

        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        assert count == 2

    async def test_start_recording_invalid_frame_leaves_recorder_clean(
        self, tmp_path: Path
    ) -> None:
        """Verify that an exception in start_recording resets state and prevents permanent lockout."""
        rec = EventRecorder(output_dir=tmp_path)

        with pytest.raises(ValueError, match="must be a non-empty 2D or 3D array"):
            await rec.start_recording([np.array([])])

        assert rec.is_recording is False

        # Should be able to successfully start a new session immediately
        valid_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        await rec.start_recording([valid_frame])
        assert rec.is_recording is True
        await rec.cancel_recording()
        assert rec.is_recording is False

    async def test_rapid_cycling_under_simulated_nvenc_failure(self, tmp_path: Path) -> None:
        """Verify repeated start/stop cycles under simulated NVENC failure work without leakage."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="h264_nvenc")
        frame = np.zeros((160, 160, 3), dtype=np.uint8)

        for _ in range(3):
            await rec.start_recording([frame])
            await rec.add_frame(frame)

            assert rec._proc is not None
            assert rec._proc._transport is not None  # type: ignore[attr-defined]
            rec._proc._transport.get_returncode = MagicMock(return_value=234)  # type: ignore[attr-defined]
            rec._actual_codec = "h264_nvenc"

            video_path = await rec.stop_recording()
            assert Path(video_path).exists()
            assert Path(video_path).stat().st_size > 0
            assert rec.is_recording is False

    def test_normalize_frame_validation(self) -> None:
        """Verify normalize_frame unit behavior."""
        with pytest.raises(TypeError, match="Expected frame of type np.ndarray"):
            normalize_frame("not_an_array")  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="must be a non-empty 2D or 3D array"):
            normalize_frame(np.array([]))

        with pytest.raises(ValueError, match="must be a non-empty 2D or 3D array"):
            normalize_frame(np.zeros((10,)))

        with pytest.raises(ValueError, match="Unsupported number of channels: 5"):
            normalize_frame(np.zeros((10, 10, 5), dtype=np.uint8))

        # Float normalization
        f_flt = np.full((50, 50, 3), 0.5, dtype=np.float32)
        norm_flt = normalize_frame(f_flt)
        assert norm_flt.dtype == np.uint8
        assert norm_flt[0, 0, 0] == 127

        # Grayscale normalization
        f_gray = np.full((50, 50), 80, dtype=np.uint8)
        norm_gray = normalize_frame(f_gray)
        assert norm_gray.shape == (50, 50, 3)

        # BGRA normalization
        f_bgra = np.full((50, 50, 4), 90, dtype=np.uint8)
        norm_bgra = normalize_frame(f_bgra)
        assert norm_bgra.shape == (50, 50, 3)

    async def test_delayed_launch_failure_in_add_frame_leaves_recorder_clean(
        self, tmp_path: Path
    ) -> None:
        """Verify that a delayed process launch error in add_frame resets state and prevents permanent lockout."""
        rec = EventRecorder(output_dir=tmp_path)
        await rec.start_recording([])
        assert rec.is_recording is True

        valid_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with (
            patch.object(rec, "_launch_process", side_effect=RuntimeError("FFmpeg spawn error")),
            pytest.raises(RuntimeError, match="FFmpeg spawn error"),
        ):
            await rec.add_frame(valid_frame)

        assert rec.is_recording is False
        assert rec.current_output_path is None or not rec.current_output_path.exists()

        # Verify immediate clean re-use
        await rec.start_recording([valid_frame])
        assert rec.is_recording is True
        await rec.cancel_recording()
        assert rec.is_recording is False

    async def test_stop_recording_cancellation_cleans_up_process_and_files(
        self, tmp_path: Path
    ) -> None:
        """Verify that cancelling stop_recording terminates FFmpeg and cleans up partial files."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        frame = np.zeros((120, 120, 3), dtype=np.uint8)
        await rec.start_recording([frame])
        out_path = rec.current_output_path
        assert out_path is not None

        task = asyncio.create_task(rec.stop_recording())
        await asyncio.sleep(0.001)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert rec.is_recording is False
        assert not out_path.exists()

    async def test_stop_recording_failure_cleans_up_partial_file(self, tmp_path: Path) -> None:
        """Verify that an unrecoverable FFmpeg error during stop_recording deletes the corrupt output file."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        frame = np.zeros((120, 120, 3), dtype=np.uint8)
        await rec.start_recording([frame])
        out_path = rec.current_output_path
        assert out_path is not None

        assert rec._proc is not None
        assert rec._proc._transport is not None  # type: ignore[attr-defined]
        rec._proc._transport.get_returncode = MagicMock(return_value=1)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="FFmpeg encoding failed"):
            await rec.stop_recording()

        assert rec.is_recording is False
        assert not out_path.exists()

    def test_camera_name_and_prefix_path_traversal_sanitization(self, tmp_path: Path) -> None:
        """Verify that camera_name and prefix with traversal characters are sanitized to safe filenames."""
        rec = EventRecorder(
            output_dir=tmp_path,
            camera_name="../../etc/cron.d/hack",
            prefix="../BAD/ALERT",
        )
        assert rec._camera_name == "etc_cron_d_hack"
        assert rec._prefix == "BAD_ALERT"

        cand = rec._generate_output_path()
        assert cand.is_relative_to(tmp_path)
        assert ".." not in str(cand)

    async def test_ram_optimization_libx264_does_not_accumulate_frames(
        self, tmp_path: Path
    ) -> None:
        """Verify that CPU libx264 recordings stream directly without buffering every frame in RAM."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        frames = [np.full((100, 100, 3), i * 40, dtype=np.uint8) for i in range(5)]

        await rec.start_recording(frames[:2])
        for f in frames[2:]:
            await rec.add_frame(f)

        assert rec.frame_count == 5
        # Under libx264, _frames must not buffer in RAM
        assert len(rec._frames) == 0

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()
        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 5
        cap.release()

    def test_normalize_frame_advanced_dtypes_and_bounds(self) -> None:
        """Verify normalize_frame handles boolean, [-1.0, 1.0], NaNs, and bounds validation."""
        # Boolean mask
        b_frame = np.array([[True, False], [False, True]])
        norm_b = normalize_frame(b_frame)
        assert norm_b[0, 0, 0] == 255
        assert norm_b[0, 1, 0] == 0

        # Normalized float [-1.0, 1.0]
        f_norm = np.array([[-1.0, 0.0], [0.5, 1.0]], dtype=np.float32)
        norm_f = normalize_frame(f_norm)
        assert norm_f[0, 0, 0] == 0
        assert norm_f[0, 1, 0] == 127
        assert norm_f[1, 1, 0] == 255

        # Float with NaNs and Infs
        nan_frame = np.array([[np.nan, np.inf], [-np.inf, 0.5]], dtype=np.float32)
        norm_nan = normalize_frame(nan_frame)
        assert norm_nan.dtype == np.uint8
        assert norm_nan[0, 0, 0] == 0
        assert norm_nan[0, 1, 0] == 255
        assert norm_nan[1, 0, 0] == 0

        # Target dimensions validation
        f_test = np.zeros((20, 20, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="target_width must be a positive integer"):
            normalize_frame(f_test, target_width=-10, target_height=20)
        with pytest.raises(ValueError, match="target_height must be a positive integer"):
            normalize_frame(f_test, target_width=20, target_height=0)

    async def test_start_recording_none_raises(self, tmp_path: Path) -> None:
        rec = EventRecorder(output_dir=tmp_path)
        with pytest.raises(TypeError, match="pre_event_frames must be an iterable"):
            await rec.start_recording(None)  # type: ignore[arg-type]

    def test_normalize_frame_readonly_float_array(self) -> None:
        """Verify normalize_frame does not mutate or crash on read-only float arrays."""
        f_flt = np.full((30, 30, 3), 0.5, dtype=np.float32)
        f_flt.flags.writeable = False
        res = normalize_frame(f_flt)
        assert res.dtype == np.uint8
        assert res.shape == (30, 30, 3)
        assert res[0, 0, 0] == 127

    def test_normalize_frame_uint16_scaling(self) -> None:
        """Verify uint16 frames are scaled appropriately instead of saturated to white."""
        f_u16 = np.full((20, 20), 32768, dtype=np.uint16)
        res = normalize_frame(f_u16)
        assert res.dtype == np.uint8
        assert res.shape == (20, 20, 3)
        assert res[0, 0, 0] == 128

    async def test_sub_one_fps_recording(self, tmp_path: Path) -> None:
        """Verify fractional / sub-1.0 fps (e.g. 0.5 fps) is supported and does not truncate to 0."""
        rec = EventRecorder(output_dir=tmp_path, fps=0.5, codec="libx264")
        assert rec.fps == 0.5

        f1 = np.zeros((100, 100, 3), dtype=np.uint8)
        f2 = np.full((100, 100, 3), 200, dtype=np.uint8)
        await rec.start_recording([f1])
        await rec.add_frame(f2)

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()
        assert Path(video_path).stat().st_size > 0

        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        assert count == 2

    async def test_atomic_output_path_concurrency_no_collisions(self, tmp_path: Path) -> None:
        """Verify concurrent output path generation does not collide."""
        rec1 = EventRecorder(output_dir=tmp_path, camera_name="cam_a")
        rec2 = EventRecorder(output_dir=tmp_path, camera_name="cam_a")

        p1, p2 = rec1._generate_output_path(), rec2._generate_output_path()
        assert p1 != p2
        assert p1.name != p2.name
        assert p1.exists()
        assert p2.exists()

        p1.unlink()
        p2.unlink()

    async def test_current_output_path_cleared_on_cancel_and_zero_frames(
        self, tmp_path: Path
    ) -> None:
        """Verify current_output_path resets to None after cancellation or 0-frame failure."""
        rec = EventRecorder(output_dir=tmp_path, codec="libx264")
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        await rec.start_recording([f])
        assert rec.current_output_path is not None
        await rec.cancel_recording()
        assert rec.current_output_path is None

        # Test zero-frame failure
        await rec.start_recording([])
        assert rec.current_output_path is not None
        with pytest.raises(ValueError, match="No frames were recorded"):
            await rec.stop_recording()
        assert rec.current_output_path is None

    async def test_nvenc_fallback_buffer_bounded_and_keeps_recent_frames(
        self, tmp_path: Path
    ) -> None:
        """Verify _frames is bounded and keeps the most recent frames under h264_nvenc."""
        with patch.object(EventRecorder, "MAX_FALLBACK_FRAMES", 5):
            rec = EventRecorder(output_dir=tmp_path, codec="h264_nvenc")
            frames = [np.full((100, 100, 3), i * 10, dtype=np.uint8) for i in range(10)]

            # Mock launch process so we don't need real NVENC
            with patch.object(rec, "_launch_process") as mock_launch:
                mock_launch.return_value = None
                rec._actual_codec = "h264_nvenc"
                rec._output_path = rec._generate_output_path()
                rec._is_recording = True

                for f in frames:
                    await rec.add_frame(f)

                assert rec.frame_count == 10
                assert len(rec._frames) == 5
                # Verify it kept the MOST RECENT frames (5, 6, 7, 8, 9)
                stored_values = [int(f[0, 0, 0]) for f in rec._frames]
                assert stored_values == [50, 60, 70, 80, 90]

            await rec.cancel_recording()

    async def test_start_recording_accepts_videobuffer(self, tmp_path: Path) -> None:
        """Verify VideoBuffer instance can be passed directly into start_recording."""
        from argus.core.buffer import VideoBuffer

        buf = VideoBuffer(fps=10, seconds=1)
        for i in range(3):
            buf.append(np.full((120, 120, 3), i * 50, dtype=np.uint8))

        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        await rec.start_recording(buf)  # type: ignore[arg-type]
        assert rec.frame_count == 3
        await rec.add_frame(np.full((120, 120, 3), 200, dtype=np.uint8))
        assert rec.frame_count == 4

        video_path = await rec.stop_recording()
        assert Path(video_path).exists()
        cap = cv2.VideoCapture(video_path)
        assert cap.isOpened()
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 4
        cap.release()

    async def test_stop_recording_writer_task_timeout_cancels_worker(self, tmp_path: Path) -> None:
        """Verify writer task timeout during stop_recording cancels worker and recovers."""
        rec = EventRecorder(output_dir=tmp_path, fps=10, codec="libx264")
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        await rec.start_recording([f])

        # Replace writer_task with a hanging task to simulate pipe deadlock
        async def hang_forever() -> None:
            await asyncio.sleep(100)

        assert rec._writer_task is not None
        rec._writer_task.cancel()
        rec._writer_task = asyncio.create_task(hang_forever())

        target_task = rec._writer_task
        assert target_task is not None

        orig_wait_for = asyncio.wait_for

        async def fast_wait_for(fut: Any, timeout: float | None = None) -> Any:
            if fut is target_task:
                return await orig_wait_for(target_task, timeout=0.05)
            return await orig_wait_for(fut, timeout=timeout)

        with patch("asyncio.wait_for", side_effect=fast_wait_for):
            video_path = await rec.stop_recording()
            assert Path(video_path).exists()
            assert rec.is_recording is False
