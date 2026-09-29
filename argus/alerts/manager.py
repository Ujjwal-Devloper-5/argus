"""
Argus Alert Engine — Unified AlertManager.

The single entry-point for all alert dispatching in the Argus pipeline.
Wires together the queue, rate limiter, quiet hours gate, and platform clients.

Usage:
    manager = AlertManager(settings, callback_handler=my_callback)
    await manager.start()
    await manager.send(alert)
    await manager.send_learn_prompt(face_hash=..., ...)
    await manager.stop()
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import structlog

from argus.alerts.models import Alert, AlertKind, AlertSeverity, InteractiveButton
from argus.alerts.queue import AlertQueue

logger = structlog.get_logger(__name__)

CallbackHandler = Callable[[str, str], Awaitable[None]]


class AlertManager:
    """
    Unified alert dispatch hub.

    Routing is governed by settings.alerts.routing:
      - "telegram" → Telegram only
      - "discord"  → Discord only
      - "both"     → Telegram + Discord in parallel

    All sends are non-blocking from the caller's perspective:
    alerts are enqueued and dispatched by a background worker.
    """

    def __init__(self, settings, callback_handler: CallbackHandler | None = None) -> None:
        self._cfg = settings.alerts
        self._callback_handler = callback_handler
        self._queue = AlertQueue(self._cfg)
        self._telegram = None
        self._discord = None
        self._worker_task: asyncio.Task | None = None
        self._held_release_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start bot clients and background dispatch worker."""
        routing = self._cfg.routing

        if routing in ("telegram", "both") and self._cfg.telegram.enabled:
            from argus.alerts.telegram_client import TelegramClient
            self._telegram = TelegramClient(self._cfg.telegram, self._callback_handler)
            await self._telegram.start()

        if routing in ("discord", "both") and self._cfg.discord.enabled:
            from argus.alerts.discord_client import DiscordClient
            self._discord = DiscordClient(self._cfg.discord, self._callback_handler)
            await self._discord.start()

        self._running = True
        self._worker_task = asyncio.create_task(self._dispatch_worker(), name="argus-alert-worker")
        self._held_release_task = asyncio.create_task(self._held_release_loop(), name="argus-held-release")
        logger.info("AlertManager started", routing=routing)

    async def stop(self) -> None:
        """Gracefully drain the queue and shut down clients."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        if self._held_release_task:
            self._held_release_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._held_release_task
        if self._telegram:
            await self._telegram.stop()
        if self._discord:
            await self._discord.stop()
        logger.info("AlertManager stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(self, alert: Alert) -> None:
        """Enqueue an alert for dispatch (non-blocking, fire-and-forget)."""
        await self._queue.put(alert)

    async def send_learn_prompt(
        self,
        face_hash: str,
        appearance_count: int,
        camera_name: str,
        thumbnail_path: str,
        pattern_note: str,
        similarity: float,
    ) -> None:
        """
        Convenience method called by AutoLearner when an unknown face
        reaches the prompt threshold.
        """
        import pathlib
        thumb_bytes: bytes | None = None
        try:
            p = pathlib.Path(thumbnail_path)
            if p.exists():
                thumb_bytes = p.read_bytes()
        except Exception:
            pass

        body_parts = [
            f"An unknown person has appeared <b>{appearance_count}</b> times.",
            f"Similarity to nearest known face: <b>{similarity:.1%}</b>",
        ]
        if pattern_note:
            body_parts.append(f"Pattern: {pattern_note}")

        alert = Alert(
            kind=AlertKind.LEARN_PROMPT,
            severity=AlertSeverity.WARNING,
            title="🔍 Do you know this person?",
            body="\n".join(body_parts),
            camera_name=camera_name,
            thumbnail=thumb_bytes,
            buttons=[
                InteractiveButton("✅ Yes, add to known faces", f"learn:add:{face_hash}"),
                InteractiveButton("❌ No, mark as stranger",   f"learn:stranger:{face_hash}"),
                InteractiveButton("🔕 Ignore always",         f"learn:ignore:{face_hash}"),
            ],
            metadata={"face_hash": face_hash, "appearance_count": appearance_count},
        )
        await self._queue.put(alert)

    # ------------------------------------------------------------------
    # Internal workers
    # ------------------------------------------------------------------

    async def _dispatch_worker(self) -> None:
        """Background task: dequeue + rate-limit + dispatch to platforms."""
        while self._running:
            try:
                alert = await self._queue.get()
                await self._queue._limiter.acquire()  # honour rate limit
                await self._dispatch(alert)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Alert dispatch error", error=str(exc))

    async def _held_release_loop(self) -> None:
        """Periodically check if quiet hours have ended and release held alerts."""
        while self._running:
            try:
                await asyncio.sleep(60)  # check every minute
                if not self._queue._gate.is_quiet_now():
                    await self._queue.release_held()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Held release loop error", error=str(exc))

    async def _dispatch(self, alert: Alert) -> None:
        """Fan-out to all enabled, configured platform clients."""
        routing = self._cfg.routing
        tasks = []
        if self._telegram and routing in ("telegram", "both"):
            tasks.append(self._telegram.send(alert))
        if self._discord and routing in ("discord", "both"):
            tasks.append(self._discord.send(alert))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("Platform dispatch exception", error=str(r))
        else:
            logger.debug("No active alert clients — alert dropped", alert_id=alert.alert_id)
