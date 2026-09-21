"""
Recording Engine for Argus AI Security System.

Provides EventRecorder to stitch pre-event buffered frames and incoming live frames
into a single MP4 video file using asynchronous FFmpeg subprocesses, with automatic
Nvidia NVENC (RTX 3050) hardware acceleration and graceful fallback to libx264.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import re
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import ffmpeg
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Global cache for NVENC hardware detection
_NVENC_AVAILABLE: bool | None = None


def normalize_frame(
    frame: np.ndarray,
    target_width: int | None = None,
    target_height: int | None = None,
) -> np.ndarray:
    """
    Validate and normalize a frame into a C-contiguous uint8 BGR image.

    - Rejects non-ndarrays, empty arrays, and invalid dimensions (<2D or >3D).
    - Converts floating-point frames to uint8 [0, 255] (handling [-1.0, 1.0], [0.0, 1.0], NaNs, and Infs).
    - Converts boolean masks to uint8 [0, 255].
    - Converts grayscale (2D or HxWx1) to 3-channel BGR.
    - Converts BGRA (HxWx4) to 3-channel BGR.
    - Resizes to (target_width, target_height) if specified.
    - Ensures C-contiguous uint8 layout.
    """
    if not isinstance(frame, np.ndarray):
        raise TypeError(f"Expected frame of type np.ndarray, got {type(frame).__name__}")
    if frame.size == 0 or frame.ndim not in (2, 3):
        raise ValueError(
            f"Invalid frame shape {getattr(frame, 'shape', None)}; must be a non-empty 2D or 3D array"
        )

    if target_width is not None and (
        isinstance(target_width, bool) or not isinstance(target_width, int) or target_width <= 0
    ):
        raise ValueError(f"target_width must be a positive integer, got {target_width}")
    if target_height is not None and (
        isinstance(target_height, bool) or not isinstance(target_height, int) or target_height <= 0
    ):
        raise ValueError(f"target_height must be a positive integer, got {target_height}")

    # Dtype normalization
    if frame.dtype == np.bool_:
        frame = frame.astype(np.uint8) * 255
    elif np.issubdtype(frame.dtype, np.floating):
        frame = np.nan_to_num(frame, copy=True, nan=0.0, posinf=255.0, neginf=0.0)
        min_val = float(frame.min()) if frame.size > 0 else 0.0
        max_val = float(frame.max()) if frame.size > 0 else 0.0
        if min_val >= -1.0 and max_val <= 1.0 and min_val < 0.0:
            frame = ((frame + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
        elif min_val >= 0.0 and max_val <= 1.0 and max_val > 0.0:
            frame = (frame * 255.0).clip(0, 255).astype(np.uint8)
        else:
            frame = frame.clip(0, 255).astype(np.uint8)
    elif frame.dtype == np.uint16:
        max_val = float(frame.max()) if frame.size > 0 else 0.0
        if max_val > 255.0:
            frame = (frame / 256.0).clip(0, 255).astype(np.uint8)
        else:
            frame = frame.astype(np.uint8)
    elif frame.dtype != np.uint8:
        frame = frame.clip(0, 255).astype(np.uint8)

    # Channel normalization
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim == 3:
        channels = frame.shape[2]
        if channels == 1:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif channels == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif channels == 3:
            pass
        else:
            raise ValueError(f"Unsupported number of channels: {channels}; must be 1, 3, or 4")

    # Resize if requested and needed
    if (
        target_width is not None
        and target_height is not None
        and (frame.shape[1], frame.shape[0]) != (target_width, target_height)
    ):
        frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

    return np.ascontiguousarray(frame, dtype=np.uint8)


def check_nvenc_support(probe_timeout: float = 2.0) -> bool:
    """
    Check if FFmpeg supports h264_nvenc encoding on the system.

    Probes FFmpeg with a synthetic test frame using h264_nvenc.
    Results are cached globally for efficiency.
    """
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is not None:
        return _NVENC_AVAILABLE

    try:
        res = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=0.04:size=256x256:rate=25",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=probe_timeout,
            check=False,
        )
        _NVENC_AVAILABLE = res.returncode == 0
    except Exception:
        _NVENC_AVAILABLE = False

    return _NVENC_AVAILABLE


def is_nvenc_available(width: int = 640, height: int = 480) -> bool:
    """
    Determine if h264_nvenc is supported for the given video resolution.

    NVENC requires a minimum resolution (~145x49) and even pixel dimensions.
    If dimensions are too small or hardware encoding is not supported, returns False.
    """
    if width < 145 or height < 49:
        return False
    if width % 2 != 0 or height % 2 != 0:
        return False
    return check_nvenc_support()


def reset_nvenc_cache() -> None:
    """Reset cached NVENC detection result (used for testing)."""
    global _NVENC_AVAILABLE
    _NVENC_AVAILABLE = None


def build_ffmpeg_command(
    output_path: str,
    width: int,
    height: int,
    fps: int | float,
    codec: str,
) -> list[str]:
    """
    Use ffmpeg-python to construct the FFmpeg command line arguments.

    Encodes rawvideo BGR24 input stream to MP4 with yuv420p pixel format
    and faststart movflags for web and dashboard compatibility.
    """
    stream = ffmpeg.input(
        "pipe:",
        format="rawvideo",
        pix_fmt="bgr24",
        s=f"{width}x{height}",
        framerate=fps,
    )
    output_kwargs: dict[str, Any] = {
        "vcodec": codec,
        "pix_fmt": "yuv420p",
        "movflags": "+faststart",
    }
    if codec == "libx264":
        output_kwargs["preset"] = "ultrafast"

    stream = ffmpeg.output(stream, output_path, **output_kwargs)
    stream = ffmpeg.overwrite_output(stream)
    return ffmpeg.compile(stream)


class EventRecorder:
    """
    Asynchronous event recorder for incident video clips.

    Stitches pre-event frames from VideoBuffer and incoming live frames into a single MP4 video.
    Uses asynchronous FFmpeg subprocesses to prevent blocking the YOLOv8 AI pipeline.
    """

    MAX_FALLBACK_FRAMES: int = 3600  # Cap fallback buffer in RAM (4 mins at 15fps)

    def __init__(
        self,
        output_dir: str | Path | None = None,
        fps: int | float = 15,
        codec: str | None = None,
        camera_name: str | None = None,
        prefix: str = "EVENT",
    ) -> None:
        if isinstance(fps, bool) or not isinstance(fps, (int, float)):
            raise TypeError(f"fps must be an integer or float, got {type(fps).__name__}")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        if output_dir is not None:
            self._output_dir = Path(output_dir)
        else:
            try:
                from argus.config.settings import get_settings

                self._output_dir = Path(get_settings().recordings_path)
            except Exception:
                self._output_dir = Path("argus/data/recordings")

        self._fps: int | float = (
            int(fps)
            if isinstance(fps, int) or (isinstance(fps, float) and fps.is_integer())
            else float(fps)
        )
        self._requested_codec = codec

        # Sanitize camera_name and prefix to avoid path traversal / invalid filenames
        if camera_name and camera_name.strip():
            clean_cam = re.sub(r"[^a-zA-Z0-9_-]", "_", camera_name.strip()).strip("_").lower()
            self._camera_name: str | None = clean_cam if clean_cam else None
        else:
            self._camera_name = None

        if prefix and prefix.strip():
            clean_pre = re.sub(r"[^a-zA-Z0-9_-]", "_", prefix.strip()).strip("_")
            self._prefix: str = clean_pre if clean_pre else "EVENT"
        else:
            self._prefix = "EVENT"

        # Concurrency synchronization lock
        self._lock = asyncio.Lock()

        # State tracking
        self._is_recording: bool = False
        self._frames: deque[np.ndarray] = deque(maxlen=self.MAX_FALLBACK_FRAMES)
        self._frame_count: int = 0
        self._width: int = 0
        self._height: int = 0
        self._actual_codec: str = "libx264"
        self._output_path: Path | None = None

        # Async subprocess components
        self._proc: asyncio.subprocess.Process | None = None
        self._frame_queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_lines: deque[str] = deque(maxlen=100)

    @property
    def is_recording(self) -> bool:
        """Whether a recording session is currently active."""
        return self._is_recording

    @property
    def output_dir(self) -> Path:
        """Directory where recordings are saved."""
        return self._output_dir

    @property
    def fps(self) -> int | float:
        """Frame rate for recordings."""
        return self._fps

    @property
    def current_output_path(self) -> Path | None:
        """Output file path of the currently active or most recent recording."""
        return self._output_path

    @property
    def frame_count(self) -> int:
        """Number of frames accumulated in the current recording."""
        return self._frame_count

    def _select_codec(self, width: int, height: int) -> str:
        """Select encoding codec based on request, resolution, and hardware availability."""
        if self._requested_codec is not None:
            if self._requested_codec == "h264_nvenc" and not is_nvenc_available(width, height):
                logger.warning(
                    "Requested h264_nvenc but not supported for resolution, falling back to libx264",
                    width=width,
                    height=height,
                )
                return "libx264"
            return self._requested_codec

        if is_nvenc_available(width, height):
            return "h264_nvenc"
        return "libx264"

    def _generate_output_path(self) -> Path:
        """Generate a unique timestamped output filename atomically."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = (
            f"{self._prefix}_{self._camera_name}_{timestamp}"
            if self._camera_name
            else f"{self._prefix}_{timestamp}"
        )

        candidate = self._output_dir / f"{stem}.mp4"
        counter = 1
        while True:
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return candidate
            except FileExistsError:
                candidate = self._output_dir / f"{stem}_{counter}.mp4"
                counter += 1

        return candidate

    async def _launch_process(self, width: int, height: int) -> None:
        """Launch the asynchronous FFmpeg subprocess and background writer/reader tasks."""
        self._actual_codec = self._select_codec(width, height)
        cmd = build_ffmpeg_command(
            str(self._output_path),
            width=width,
            height=height,
            fps=self._fps,
            codec=self._actual_codec,
        )

        logger.info(
            "Launching FFmpeg subprocess for event recording",
            output_path=str(self._output_path),
            width=width,
            height=height,
            fps=self._fps,
            codec=self._actual_codec,
        )

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        self._frame_queue = asyncio.Queue()
        self._stderr_lines.clear()
        self._writer_task = asyncio.create_task(self._feed_worker())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _feed_worker(self) -> None:
        """Background worker task reading frames from queue and writing to FFmpeg stdin."""
        if not self._proc or not self._proc.stdin:
            return

        try:
            while True:
                frame = await self._frame_queue.get()
                if frame is None:
                    # Sentinel received: stop feeding
                    break

                if (frame.shape[1], frame.shape[0]) != (
                    self._width,
                    self._height,
                ) or frame.dtype != np.uint8:
                    frame = normalize_frame(
                        frame, target_width=self._width, target_height=self._height
                    )

                self._proc.stdin.write(frame.tobytes())
                await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning("FFmpeg stdin pipe disconnected", error=str(e))
        except Exception as e:
            logger.error("Error writing frame to FFmpeg stdin", error=str(e))
        finally:
            if self._proc and self._proc.stdin and not self._proc.stdin.is_closing():
                with contextlib.suppress(Exception):
                    self._proc.stdin.close()

    async def _read_stderr(self) -> None:
        """Background reader continuously draining FFmpeg stderr to prevent pipe buffer deadlock."""
        if not self._proc or not self._proc.stderr:
            return
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                self._stderr_lines.append(line.decode(errors="replace"))
        except (asyncio.CancelledError, Exception):
            pass

    async def start_recording(self, pre_event_frames: list[np.ndarray]) -> None:
        """
        Start recording an event.

        Initializes recording state, queues pre-event buffered frames, and starts
        the non-blocking FFmpeg subprocess.
        """
        async with self._lock:
            if self._is_recording:
                raise RuntimeError("Recording session is already in progress")

            if pre_event_frames is None:
                raise TypeError("pre_event_frames must be an iterable of numpy ndarrays, got None")

            # Validate all frames BEFORE changing recording state
            normalized_pre: list[np.ndarray] = []
            for idx, f in enumerate(pre_event_frames):
                if not isinstance(f, np.ndarray):
                    raise TypeError(
                        f"pre_event_frames[{idx}] is not a numpy ndarray, got {type(f).__name__}"
                    )
                normalized_pre.append(normalize_frame(f))

            self._output_path = self._generate_output_path()

            try:
                if normalized_pre:
                    h, w = normalized_pre[0].shape[:2]
                    # Ensure dimensions are even numbers for H.264 / yuv420p
                    self._width = max(2, w - (w % 2))
                    self._height = max(2, h - (h % 2))

                    await self._launch_process(self._width, self._height)
                    for f in normalized_pre:
                        if (f.shape[1], f.shape[0]) != (self._width, self._height):
                            f = cv2.resize(
                                f, (self._width, self._height), interpolation=cv2.INTER_LINEAR
                            )
                        if self._actual_codec == "h264_nvenc":
                            self._frames.append(f)
                        self._frame_count += 1
                        await self._frame_queue.put(f)

                self._is_recording = True
            except Exception:
                if self._output_path and self._output_path.exists():
                    with contextlib.suppress(Exception):
                        self._output_path.unlink()
                self._cleanup_session()
                self._is_recording = False
                raise

    async def add_frame(self, frame: np.ndarray) -> None:
        """
        Add a live video frame to the ongoing recording session.

        Runs asynchronously and queues the frame for background pipe ingestion,
        preventing any stall on the AI detection thread.
        """
        async with self._lock:
            if not self._is_recording:
                raise RuntimeError("Cannot add frame: no recording in progress")

            # Validate and normalize incoming frame
            norm_frame = normalize_frame(frame)

            if self._proc is None:
                # First frame received after empty pre_event_frames
                h, w = norm_frame.shape[:2]
                self._width = max(2, w - (w % 2))
                self._height = max(2, h - (h % 2))
                try:
                    await self._launch_process(self._width, self._height)
                except Exception:
                    self._is_recording = False
                    if self._output_path and self._output_path.exists():
                        with contextlib.suppress(Exception):
                            self._output_path.unlink()
                    self._output_path = None
                    self._cleanup_session()
                    raise

            if (norm_frame.shape[1], norm_frame.shape[0]) != (self._width, self._height):
                norm_frame = cv2.resize(
                    norm_frame, (self._width, self._height), interpolation=cv2.INTER_LINEAR
                )

            self._frame_count += 1
            if self._actual_codec == "h264_nvenc":
                self._frames.append(norm_frame)
            await self._frame_queue.put(norm_frame)

    async def _fallback_encode_libx264(self) -> str:
        """Fallback encoding: re-encode accumulated frames using CPU libx264."""
        assert self._output_path is not None
        cmd = build_ffmpeg_command(
            str(self._output_path),
            width=self._width,
            height=self._height,
            fps=self._fps,
            codec="libx264",
        )

        logger.info(
            "Executing fallback libx264 encoding",
            output_path=str(self._output_path),
            frame_count=len(self._frames),
        )

        fb_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        fb_stderr_lines: deque[str] = deque(maxlen=50)

        async def _read_fb_err() -> None:
            if not fb_proc.stderr:
                return
            try:
                while True:
                    line = await fb_proc.stderr.readline()
                    if not line:
                        break
                    fb_stderr_lines.append(line.decode(errors="replace"))
            except Exception:
                pass

        fb_err_task = asyncio.create_task(_read_fb_err())

        try:
            # Stream frames directly with timeout guard
            async def _feed_fallback() -> None:
                if not fb_proc.stdin:
                    return
                for f in self._frames:
                    if (f.shape[1], f.shape[0]) != (
                        self._width,
                        self._height,
                    ) or f.dtype != np.uint8:
                        f = normalize_frame(f, target_width=self._width, target_height=self._height)
                    fb_proc.stdin.write(f.tobytes())
                    await fb_proc.stdin.drain()
                fb_proc.stdin.close()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(fb_proc.stdin.wait_closed(), timeout=2.0)

            try:
                await asyncio.wait_for(_feed_fallback(), timeout=30.0)
            except Exception as e:
                logger.warning("Error feeding fallback FFmpeg stdin", error=str(e))
                if fb_proc.stdin and not fb_proc.stdin.is_closing():
                    with contextlib.suppress(Exception):
                        fb_proc.stdin.close()

            # Wait for fallback process with timeout guard
            try:
                await asyncio.wait_for(fb_proc.wait(), timeout=30.0)
            except TimeoutError:
                logger.error("FFmpeg fallback process timed out, terminating")
                with contextlib.suppress(Exception):
                    fb_proc.kill()
                await fb_proc.wait()

            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(fb_err_task, timeout=2.0)

            if fb_proc.returncode != 0:
                err_msg = "".join(fb_stderr_lines) or "unknown error"
                raise RuntimeError(
                    f"FFmpeg fallback libx264 encoding failed (exit code {fb_proc.returncode}): {err_msg}"
                )

            return str(self._output_path)
        except BaseException:
            fb_err_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await fb_err_task
            if fb_proc.returncode is None:
                with contextlib.suppress(Exception):
                    fb_proc.kill()
                with contextlib.suppress(Exception):
                    await fb_proc.wait()
            raise

    async def stop_recording(self) -> str:
        """
        Stop recording, finalize MP4 video encoding, and return saved video path.

        Gracefully flushes the background writer, closes FFmpeg stdin, and awaits
        process completion. If NVENC encoding fails, automatically falls back to libx264.
        """
        async with self._lock:
            if not self._is_recording:
                raise RuntimeError("Cannot stop recording: no recording in progress")

            if self._frame_count == 0:
                self._is_recording = False
                if self._output_path and self._output_path.exists():
                    with contextlib.suppress(Exception):
                        self._output_path.unlink()
                self._cleanup_session()
                self._output_path = None
                raise ValueError("No frames were recorded; cannot save video")

            assert self._output_path is not None

            try:
                # Signal writer task to stop and wait for it with timeout guard
                if self._writer_task is not None:
                    await self._frame_queue.put(None)
                    try:
                        await asyncio.wait_for(self._writer_task, timeout=15.0)
                    except TimeoutError:
                        logger.error(
                            "Writer task timed out feeding FFmpeg stdin, cancelling writer task"
                        )
                        self._writer_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await self._writer_task

                # Close process stdin and wait for FFmpeg to finish
                if self._proc is not None:
                    if self._proc.stdin and not self._proc.stdin.is_closing():
                        try:
                            self._proc.stdin.close()
                            await asyncio.wait_for(self._proc.stdin.wait_closed(), timeout=2.0)
                        except Exception:
                            pass

                    # Await FFmpeg process termination with timeout guard
                    try:
                        await asyncio.wait_for(self._proc.wait(), timeout=30.0)
                    except TimeoutError:
                        logger.error("FFmpeg process timed out during stop_recording, terminating")
                        self._proc.kill()
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(self._proc.wait(), timeout=5.0)

                if self._stderr_task is not None:
                    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                        await asyncio.wait_for(self._stderr_task, timeout=2.0)

                final_path: str
                if self._proc is not None and self._proc.returncode != 0:
                    stderr_output = "".join(self._stderr_lines)
                    if self._actual_codec == "h264_nvenc":
                        logger.warning(
                            "h264_nvenc encoding failed, falling back to libx264",
                            exit_code=self._proc.returncode,
                            stderr=stderr_output[-400:],
                        )
                        final_path = await self._fallback_encode_libx264()
                    else:
                        retcode = self._proc.returncode
                        raise RuntimeError(
                            f"FFmpeg encoding failed (exit code {retcode}): {stderr_output}"
                        )
                else:
                    final_path = str(self._output_path)

                # Verify output video exists and is non-empty
                if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
                    raise RuntimeError(f"Recorded file {final_path} does not exist or is empty")

                logger.info(
                    "Event recording completed successfully",
                    output_path=final_path,
                    size_bytes=os.path.getsize(final_path),
                    frame_count=self._frame_count,
                )
                return final_path
            except BaseException:
                # On cancellation or failure, clean up child process, tasks, and partial file
                if self._writer_task is not None and not self._writer_task.done():
                    self._writer_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._writer_task
                if self._stderr_task is not None and not self._stderr_task.done():
                    self._stderr_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._stderr_task
                if self._proc is not None and self._proc.returncode is None:
                    with contextlib.suppress(Exception):
                        self._proc.kill()
                    with contextlib.suppress(Exception):
                        await self._proc.wait()
                if self._output_path and self._output_path.exists():
                    with contextlib.suppress(Exception):
                        self._output_path.unlink()
                self._output_path = None
                raise
            finally:
                self._is_recording = False
                self._cleanup_session()

    async def cancel_recording(self) -> None:
        """Cancel ongoing recording and discard partial output file."""
        async with self._lock:
            if not self._is_recording:
                return

            self._is_recording = False
            if self._writer_task is not None:
                self._writer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._writer_task

            if self._stderr_task is not None:
                self._stderr_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._stderr_task

            if self._proc is not None:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    with contextlib.suppress(Exception):
                        self._proc.stdin.close()
                with contextlib.suppress(Exception):
                    self._proc.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(self._proc.wait(), timeout=3.0)

            if self._output_path and self._output_path.exists():
                with contextlib.suppress(Exception):
                    self._output_path.unlink()
            self._output_path = None

            self._cleanup_session()

    def _cleanup_session(self) -> None:
        """Reset internal session attributes."""
        self._frames.clear()
        self._frame_count = 0
        self._proc = None
        self._writer_task = None
        self._stderr_task = None
        self._stderr_lines.clear()
        self._frame_queue = asyncio.Queue()
        self._width = 0
        self._height = 0
