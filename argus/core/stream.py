"""
RTSP Stream Ingestor using PyAV.

Connects to RTSP video cameras using TCP transport and stimeout to prevent hanging,
decodes video frames asynchronously in a thread pool executor, and manages an
asyncio frame queue with automatic oldest-frame drop on backpressure.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import av
import av.error
import numpy as np
import structlog

from argus.config.settings import CameraConfig

logger = structlog.get_logger(__name__)

# Ensure av.AVError exists for backwards compatibility and test convenience
if not hasattr(av, "AVError"):
    with contextlib.suppress(Exception):
        av.AVError = av.FFmpegError  # type: ignore[attr-defined]

AV_ERROR_CLASS = getattr(av, "AVError", getattr(av, "FFmpegError", Exception))


def _open_stream(url: str, stimeout: int) -> Any:
    """Open RTSP stream with TCP transport and socket timeout."""
    options = {
        "rtsp_transport": "tcp",
        "stimeout": str(stimeout),
    }
    return av.open(url, options=options)


def _get_frame_gen(c: Any, stream: Any) -> Any:
    """Create PyAV frame decode generator."""
    return iter(c.decode(stream))


def _decode_next(gen: Any) -> np.ndarray | None:
    """Decode the next video frame to a BGR24 numpy array."""
    try:
        f = next(gen)
        if f is None:
            return None
        if hasattr(f, "to_ndarray"):
            return f.to_ndarray(format="bgr24")
        if isinstance(f, np.ndarray):
            return f
        return np.asarray(f)
    except StopIteration:
        return None


class StreamWorker:
    """
    Async RTSP stream ingestor for a single camera.

    Features:
    - PyAV RTSP ingestion over TCP transport with stimeout.
    - Off-event-loop frame decoding using ThreadPoolExecutor.
    - Bounded queue (default maxsize=5) dropping oldest frames on backpressure.
    - Exponential reconnection backoff (5s to 60s) with automatic reset on recovery.
    - Clean async teardown via stop().
    """

    def __init__(
        self,
        camera: CameraConfig,
        queue: asyncio.Queue[np.ndarray] | None = None,
        initial_backoff: float = 5.0,
        max_backoff: float = 60.0,
        backoff_factor: float = 2.0,
        stimeout_us: int = 5_000_000,
        use_substream: bool = False,
    ) -> None:
        """
        Initialize the stream worker.

        Args:
            camera: Camera configuration model.
            queue: Optional pre-configured queue. Defaults to asyncio.Queue(maxsize=5).
            initial_backoff: Initial reconnect delay in seconds (default: 5.0s).
            max_backoff: Maximum reconnect delay in seconds (default: 60.0s).
            backoff_factor: Multiplier for exponential backoff (default: 2.0).
            stimeout_us: Socket timeout in microseconds for FFmpeg/PyAV (default: 5,000,000us = 5s).
            use_substream: If True and camera.rtsp_sub_url is configured, connects to sub stream.
        """
        if not isinstance(camera, CameraConfig):
            raise TypeError(f"camera must be a CameraConfig, got {type(camera).__name__}")
        if isinstance(initial_backoff, bool) or not (
            isinstance(initial_backoff, (int, float))
            and math.isfinite(initial_backoff)
            and initial_backoff > 0
        ):
            raise ValueError(f"initial_backoff must be positive, got {initial_backoff}")
        if isinstance(max_backoff, bool) or not (
            isinstance(max_backoff, (int, float))
            and math.isfinite(max_backoff)
            and max_backoff >= initial_backoff
        ):
            raise ValueError(
                f"max_backoff ({max_backoff}) cannot be less than initial_backoff ({initial_backoff})"
            )
        if isinstance(backoff_factor, bool) or not (
            isinstance(backoff_factor, (int, float))
            and math.isfinite(backoff_factor)
            and backoff_factor >= 1.0
        ):
            raise ValueError(f"backoff_factor must be >= 1.0, got {backoff_factor}")
        if isinstance(stimeout_us, bool) or not (isinstance(stimeout_us, int) and stimeout_us > 0):
            raise ValueError(f"stimeout_us must be positive, got {stimeout_us}")

        self.camera = camera
        self.queue: asyncio.Queue[np.ndarray] = (
            queue if queue is not None else asyncio.Queue(maxsize=5)
        )
        self.initial_backoff = float(initial_backoff)
        self.max_backoff = float(max_backoff)
        self.backoff_factor = float(backoff_factor)
        self.stimeout_us = stimeout_us
        self.use_substream = use_substream

        self.current_backoff: float = self.initial_backoff
        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._start_lock: asyncio.Lock = asyncio.Lock()
        self._stop_lock: asyncio.Lock = asyncio.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._container: Any | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Whether the worker loop is currently running."""
        return self._running

    @property
    def stream_url(self) -> str:
        """Return the RTSP URL to connect to (main or sub stream)."""
        if self.use_substream and self.camera.rtsp_sub_url:
            return self.camera.rtsp_sub_url
        return self.camera.rtsp_url

    def push_frame(self, frame: np.ndarray) -> None:
        """
        Push a decoded BGR24 frame to the queue.

        If the queue is full, the oldest frame is dropped to prevent stale backlog.
        """
        if (
            frame is None
            or not isinstance(frame, np.ndarray)
            or frame.size == 0
            or frame.ndim not in (2, 3)
        ):
            return

        if frame.ndim == 3 and (frame.shape[2] == 0 or frame.shape[2] > 512):
            return

        if self.queue.maxsize > 0:
            while self.queue.full():
                try:
                    self.queue.get_nowait()
                    with contextlib.suppress(ValueError, AttributeError):
                        self.queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    break

        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()
                with contextlib.suppress(ValueError, AttributeError):
                    self.queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                pass
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(frame)

    @staticmethod
    def _close_container(container: Any) -> None:
        """Close an input container safely."""
        if container is not None:
            with contextlib.suppress(Exception):
                container.close()

    async def start(self) -> None:
        """
        Run the stream ingestor loop.

        Connects to the RTSP stream using PyAV with TCP transport and socket timeout,
        decodes frames in a thread pool executor, pushes BGR24 frames to the queue,
        and automatically handles reconnection with exponential backoff on failure.
        """
        if self.camera.disabled:
            logger.info("Camera is disabled, skipping stream worker", camera=self.camera.name)
            return

        async with self._start_lock:
            if self._running:
                logger.warning("StreamWorker is already running", camera=self.camera.name)
                return

            self._running = True
            self._stop_event.clear()
            self._task = asyncio.current_task()
            self.current_backoff = self.initial_backoff

            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix=f"stream-{self.camera.name}",
                )

        loop = asyncio.get_running_loop()
        logger.info(
            "Starting stream worker",
            camera=self.camera.name,
            rtsp_url=self.stream_url,
            stimeout_us=self.stimeout_us,
        )

        try:
            while self._running:
                try:
                    # 1. Connect to RTSP stream in thread pool
                    container = await loop.run_in_executor(
                        self._executor, _open_stream, self.stream_url, self.stimeout_us
                    )
                    self._container = container

                    if not self._running:
                        break

                    # 2. Verify video stream
                    video_streams = getattr(container.streams, "video", None)
                    if not video_streams:
                        raise ValueError(f"No video streams found for camera {self.camera.name}")
                    video_stream = video_streams[0]

                    # 3. Create frame generator in thread pool
                    frame_gen = await loop.run_in_executor(
                        self._executor, _get_frame_gen, container, video_stream
                    )

                    # 4. Stream and decode frames
                    first_frame = True
                    while self._running:
                        frame = await loop.run_in_executor(self._executor, _decode_next, frame_gen)

                        if frame is None:
                            logger.warning(
                                "RTSP stream ended or reached EOF",
                                camera=self.camera.name,
                            )
                            break

                        if first_frame:
                            logger.info(
                                "RTSP stream active and receiving frames",
                                camera=self.camera.name,
                            )
                            self.current_backoff = self.initial_backoff
                            first_frame = False

                        self.push_frame(frame)

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self._running:
                        logger.warning(
                            "Stream read/connection error; will reconnect",
                            camera=self.camera.name,
                            error=str(exc),
                            error_type=type(exc).__name__,
                            backoff=self.current_backoff,
                        )
                finally:
                    # Atomically take ownership of container to prevent double-close race
                    c = self._container
                    self._container = None
                    if c is not None:
                        if self._executor is not None:
                            try:
                                self._executor.submit(self._close_container, c)
                            except Exception:
                                self._close_container(c)
                        else:
                            self._close_container(c)

                # Reconnection backoff if worker is still running
                if self._running:
                    sleep_time = self.current_backoff
                    self.current_backoff = min(
                        self.current_backoff * self.backoff_factor,
                        self.max_backoff,
                    )
                    logger.debug(
                        "Waiting before reconnect attempt",
                        camera=self.camera.name,
                        sleep_time=sleep_time,
                        next_backoff=self.current_backoff,
                    )
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_time)
                        # Stop was requested during backoff sleep
                        break
                    except TimeoutError:
                        # Backoff duration elapsed, proceed to next connection attempt
                        pass

        except asyncio.CancelledError:
            logger.info("StreamWorker task cancelled", camera=self.camera.name)
            raise
        finally:
            self._running = False
            self._task = None
            self._container = None
            if self._executor is not None:
                with contextlib.suppress(Exception):
                    self._executor.shutdown(wait=False, cancel_futures=False)
                self._executor = None
            logger.info("StreamWorker stopped", camera=self.camera.name)

    async def stop(self, timeout: float | None = None) -> None:
        """
        Cleanly stop the stream worker and release all resources.

        Args:
            timeout: Maximum seconds to wait for worker task to complete.
                     If None, defaults to socket timeout plus safety margin.
        """
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError(f"timeout must be a non-negative finite number, got {timeout}")

        async with self._stop_lock:
            if not self._running and self._container is None and self._executor is None:
                return

            if timeout is None:
                timeout = max(2.0, (self.stimeout_us / 1_000_000.0) + 1.0)

            logger.info("Stopping StreamWorker", camera=self.camera.name)
            self._running = False
            self._stop_event.set()

            # Wait for worker task if stopping from outside the task
            if (
                self._task is not None
                and not self._task.done()
                and self._task is not asyncio.current_task()
            ):
                try:
                    await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
                except (TimeoutError, asyncio.CancelledError):
                    self._task.cancel()
                    with contextlib.suppress(TimeoutError, asyncio.CancelledError, Exception):
                        await asyncio.wait_for(self._task, timeout=1.0)

            # If container is still open after task finished, close it safely.
            # Schedule on executor if executor is still alive to prevent concurrent close segfault.
            c = self._container
            self._container = None
            if c is not None:
                if self._executor is not None:
                    try:
                        self._executor.submit(self._close_container, c)
                    except Exception:
                        self._close_container(c)
                else:
                    self._close_container(c)

            # Shutdown thread pool executor if still active
            if self._executor is not None:
                executor = self._executor
                self._executor = None
                with contextlib.suppress(Exception):
                    executor.shutdown(wait=False, cancel_futures=False)

            logger.info("StreamWorker stopped successfully", camera=self.camera.name)
