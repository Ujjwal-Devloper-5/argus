"""
Argus Frame Hub — High-performance in-memory live video distribution bus.

Bridges camera stream ingestion (StreamWorker / EventOrchestrator) with the
web dashboard (MJPEG streaming and snapshot endpoints).

Key Capabilities:
  - Zero-copy / low-overhead in-memory frame buffering.
  - On-demand JPEG compression: only encodes frames when active viewers are subscribed.
  - Async pub/sub multiplexing: multiple dashboard browser tabs can watch simultaneously.
  - On-demand StreamWorker launcher for dynamically added cameras.
  - Hardware/PyAV RTSP live probe with video decoding and base64 preview thumbnails.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import socket
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlparse

import av
import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FrameHub:
    """
    Central in-memory frame broker for live video streams and snapshots.
    """

    def __init__(self) -> None:
        self._latest_jpeg: dict[str, tuple[float, bytes]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[bytes]]] = {}
        self._active_workers: dict[str, asyncio.Task[None]] = {}
        self._last_published_time: dict[str, float] = {}
        self._pipeline_active_cameras: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="framehub-probe")
        self._lock = asyncio.Lock()

    def register_pipeline_camera(self, camera_name: str) -> None:
        """Register that a primary camera pipeline is actively streaming for this camera."""
        self._pipeline_active_cameras.add(camera_name)

    def unregister_pipeline_camera(self, camera_name: str) -> None:
        """Unregister active primary pipeline."""
        self._pipeline_active_cameras.discard(camera_name)

    def has_subscribers(self, camera_name: str) -> bool:
        """Check if any dashboard client is actively watching this camera."""
        subs = self._subscribers.get(camera_name)
        return bool(subs and len(subs) > 0)

    def publish_frame(self, camera_name: str, frame: np.ndarray | bytes) -> None:
        """
        Publish a decoded video frame to the hub.

        Args:
            camera_name: Name of the camera emitting the frame.
            frame: Either raw BGR24 numpy array or pre-encoded JPEG bytes.
        """
        now = time.time()
        self._last_published_time[camera_name] = now

        # Only encode to JPEG if someone is watching or if last JPEG is > 1.0s old (for snapshots)
        subs = self._subscribers.get(camera_name)
        has_watchers = bool(subs and len(subs) > 0)
        cached = self._latest_jpeg.get(camera_name)
        needs_snapshot_refresh = cached is None or (now - cached[0] > 1.0)

        if not has_watchers and not needs_snapshot_refresh:
            return

        jpeg_bytes: bytes
        if isinstance(frame, np.ndarray):
            try:
                # Downscale for web stream if larger than 1280 wide to save CPU/bandwidth
                h, w = frame.shape[:2]
                if w > 1280:
                    scale = 1280.0 / w
                    target_w = 1280
                    target_h = int(h * scale)
                    resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                else:
                    resized = frame

                success, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not success:
                    return
                jpeg_bytes = buf.tobytes()
            except Exception as exc:
                logger.debug("Failed to encode frame to JPEG", camera=camera_name, error=str(exc))
                return
        elif isinstance(frame, (bytes, bytearray)):
            jpeg_bytes = bytes(frame)
        else:
            return

        self._latest_jpeg[camera_name] = (now, jpeg_bytes)

        if subs:
            dead_queues = []
            for q in list(subs):
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except (asyncio.QueueEmpty, ValueError):
                            pass
                    q.put_nowait(jpeg_bytes)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                subs.discard(dq)

    def get_latest_jpeg(self, camera_name: str, max_age_seconds: float = 5.0) -> bytes | None:
        """Return the latest cached JPEG frame if within max_age_seconds."""
        record = self._latest_jpeg.get(camera_name)
        if not record:
            return None
        timestamp, jpeg_bytes = record
        if time.time() - timestamp > max_age_seconds:
            return None
        return jpeg_bytes

    def generate_placeholder_frame(self, message: str = "Connecting to RTSP Feed...") -> bytes:
        """Generate a sleek, dark-mode SVG-styled placeholder JPEG."""
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        img[:] = (18, 18, 20)  # Dark background #121214

        # Inner border
        cv2.rectangle(img, (10, 10), (630, 350), (45, 45, 50), 1)

        # Brand header
        cv2.putText(img, "ARGUS SURVEILLANCE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 120), 1, cv2.LINE_AA)

        # Status text
        (text_w, text_h), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        text_x = max(20, (640 - text_w) // 2)
        cv2.putText(img, message, (text_x, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 225), 2, cv2.LINE_AA)

        # Timestamp
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        cv2.putText(img, ts, (20, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 90), 1, cv2.LINE_AA)

        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes()

    async def ensure_camera_streaming(self, camera_name: str) -> None:
        """
        Start an on-demand stream worker for this camera if no active pipeline is feeding it.
        """
        if camera_name in self._pipeline_active_cameras:
            return

        now = time.time()
        last_pub = self._last_published_time.get(camera_name, 0.0)

        # If frames arrived within the last 3 seconds or worker already running, do nothing
        if (now - last_pub < 3.0) or (camera_name in self._active_workers and not self._active_workers[camera_name].done()):
            return

        from argus.config import get_settings
        settings = get_settings()
        cam_cfg = next((c for c in settings.cameras if c.name == camera_name and not c.disabled), None)
        if not cam_cfg:
            return

        async with self._lock:
            if camera_name in self._active_workers and not self._active_workers[camera_name].done():
                return

            task = asyncio.create_task(
                self._run_standalone_stream(cam_cfg),
                name=f"framehub-stream-{camera_name}",
            )
            self._active_workers[camera_name] = task
            logger.info("Started on-demand camera stream worker", camera=camera_name)

    async def _run_standalone_stream(self, cam_cfg) -> None:
        """Stand-alone stream reader loop pushing directly to FrameHub."""
        from argus.core.stream import StreamWorker
        worker = StreamWorker(cam_cfg)
        try:
            # Run worker in background
            stream_task = asyncio.create_task(worker.start())

            while worker.is_running or not stream_task.done():
                try:
                    frame = await asyncio.wait_for(worker.queue.get(), timeout=1.5)
                    self.publish_frame(cam_cfg.name, frame)
                    # Stop if no viewers for > 15 seconds
                    if not self.has_subscribers(cam_cfg.name):
                        # Give grace period
                        await asyncio.sleep(1.0)
                        if not self.has_subscribers(cam_cfg.name):
                            break
                except TimeoutError:
                    if stream_task.done():
                        break
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Standalone stream worker exception", camera=cam_cfg.name, error=str(exc))
        finally:
            with contextlib.suppress(Exception):
                await worker.stop()
            self._active_workers.pop(cam_cfg.name, None)
            logger.info("Stopped on-demand camera stream worker", camera=cam_cfg.name)

    @staticmethod
    def _format_mjpeg_chunk(data: bytes) -> bytes:
        """Format a single JPEG frame as a standard MIME multipart boundary part."""
        return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"

    async def subscribe(self, camera_name: str) -> AsyncIterator[bytes]:
        """
        Async generator yielding multipart MJPEG frame chunks:
        b"--frame\\r\\nContent-Type: image/jpeg\\r\\nContent-Length: <LEN>\\r\\n\\r\\n<BYTES>\\r\\n"
        """
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=3)
        if camera_name not in self._subscribers:
            self._subscribers[camera_name] = set()
        self._subscribers[camera_name].add(queue)

        # Trigger on-demand streaming if not already active
        await self.ensure_camera_streaming(camera_name)

        # Yield immediate frame: either latest cached frame or placeholder
        latest = self.get_latest_jpeg(camera_name)
        if latest:
            yield self._format_mjpeg_chunk(latest)
        else:
            initial_placeholder = self.generate_placeholder_frame(f"Connecting to {camera_name}...")
            yield self._format_mjpeg_chunk(initial_placeholder)

        consecutive_timeouts = 0
        try:
            while True:
                try:
                    frame_bytes = await asyncio.wait_for(queue.get(), timeout=2.5)
                    consecutive_timeouts = 0
                    yield self._format_mjpeg_chunk(frame_bytes)
                except TimeoutError:
                    consecutive_timeouts += 1
                    # Ensure stream is healthy
                    await self.ensure_camera_streaming(camera_name)
                    if consecutive_timeouts >= 2:
                        timeout_frame = self.generate_placeholder_frame(f"Camera {camera_name}: Signal Idle / Reconnecting")
                        yield self._format_mjpeg_chunk(timeout_frame)
                        await asyncio.sleep(1.0)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            subs = self._subscribers.get(camera_name)
            if subs:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(camera_name, None)

    async def probe_rtsp(self, rtsp_url: str, timeout_seconds: float = 6.0) -> dict[str, Any]:
        """
        Enterprise RTSP stream prober:
          1. Validates URL and tests TCP connectivity to host:port.
          2. Connects with PyAV over TCP transport.
          3. Decodes 1 real video frame and extracts resolution, codec, and fps.
          4. Encodes a JPEG thumbnail and returns base64 preview string.
        """
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554

        if not host:
            return {
                "success": False,
                "message": "Invalid RTSP URL: hostname or IP address is missing",
            }

        loop = asyncio.get_running_loop()

        # Step 1: TCP check
        def _check_tcp() -> tuple[bool, str]:
            try:
                with socket.create_connection((host, port), timeout=min(2.0, timeout_seconds)):
                    return True, "Port open"
            except socket.timeout:
                return False, f"Connection timed out: camera host {host}:{port} is unreachable"
            except ConnectionRefusedError:
                return False, f"Connection refused on {host}:{port} (RTSP server is not running)"
            except Exception as exc:
                return False, f"Network error connecting to {host}:{port}: {str(exc)}"

        tcp_ok, tcp_msg = await loop.run_in_executor(self._executor, _check_tcp)
        if not tcp_ok:
            return {
                "success": False,
                "message": tcp_msg,
                "host": host,
                "port": port,
            }

        # Step 2: PyAV Frame Decode + Metadata Extraction
        def _decode_probe() -> dict[str, Any]:
            container = None
            try:
                options = {
                    "rtsp_transport": "tcp",
                    "stimeout": str(int(timeout_seconds * 1_000_000)),
                }
                container = av.open(rtsp_url, options=options)
                video_streams = getattr(container.streams, "video", None)
                if not video_streams:
                    return {
                        "success": False,
                        "message": "Connected to RTSP server, but no video stream track was found",
                        "host": host,
                        "port": port,
                    }

                v_stream = video_streams[0]
                codec_name = getattr(v_stream.codec_context, "name", "unknown")
                width = v_stream.width or getattr(v_stream.codec_context, "width", 0)
                height = v_stream.height or getattr(v_stream.codec_context, "height", 0)
                fps = float(v_stream.average_rate or v_stream.base_rate or 15.0)

                # Decode 1 video frame
                frame = next(container.decode(v_stream))
                if frame is None:
                    return {
                        "success": False,
                        "message": "Connected to stream, but failed to decode video frame",
                        "host": host,
                        "port": port,
                    }

                bgr_frame = frame.to_ndarray(format="bgr24")

                # Resize to max 640px wide for preview payload
                fh, fw = bgr_frame.shape[:2]
                if fw > 640:
                    scale = 640.0 / fw
                    target_w = 640
                    target_h = int(fh * scale)
                    preview_frame = cv2.resize(bgr_frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                else:
                    preview_frame = bgr_frame

                ok, buf = cv2.imencode(".jpg", preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    return {
                        "success": True,
                        "message": f"Verified {width}x{height} {codec_name.upper()} stream",
                        "codec": codec_name,
                        "resolution": f"{width}x{height}",
                        "fps": round(fps, 1),
                        "host": host,
                        "port": port,
                    }

                b64_data = base64.b64encode(buf.tobytes()).decode("ascii")
                return {
                    "success": True,
                    "message": f"Verified {width}x{height} {codec_name.upper()} stream @ {round(fps, 1)} FPS",
                    "codec": codec_name,
                    "resolution": f"{width}x{height}",
                    "fps": round(fps, 1),
                    "preview_base64": f"data:image/jpeg;base64,{b64_data}",
                    "host": host,
                    "port": port,
                }
            except av.error.InvalidDataError:
                return {
                    "success": False,
                    "message": "Invalid RTSP credentials or corrupt stream data (check username/password)",
                    "host": host,
                    "port": port,
                }
            except av.error.HTTPUnauthorizedError:
                return {
                    "success": False,
                    "message": "Authentication failed: invalid RTSP username or password",
                    "host": host,
                    "port": port,
                }
            except Exception as exc:
                err_str = str(exc)
                if "401" in err_str or "Unauthorized" in err_str:
                    msg = "Authentication failed: invalid RTSP username or password"
                elif "timed out" in err_str.lower() or "timeout" in err_str.lower():
                    msg = f"RTSP handshake timed out after {timeout_seconds}s"
                else:
                    msg = f"RTSP stream error: {err_str}"
                return {
                    "success": False,
                    "message": msg,
                    "host": host,
                    "port": port,
                }
            finally:
                if container is not None:
                    with contextlib.suppress(Exception):
                        container.close()

        return await loop.run_in_executor(self._executor, _decode_probe)


# Global singleton instance
frame_hub = FrameHub()
