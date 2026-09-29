"""
Argus Alert Engine — Async priority queue with rate limiting & quiet hours.

Architecture:
  - TokenBucketRateLimiter  — leaky bucket, refills at max_rate tokens/sec
  - AlertQueue              — asyncio.PriorityQueue-backed queue
  - QuietHoursGate          — suppresses / holds non-critical alerts in window

The queue is a singleton managed by AlertManager. Nothing outside the
alerts package should interact with it directly.
"""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class TokenBucketRateLimiter:
    """
    Token-bucket rate limiter.
    Allows up to `rate` tokens per second (bursty OK up to `capacity`).
    Callers await acquire() before dispatching.
    """

    __slots__ = ("_rate", "_capacity", "_tokens", "_last_refill", "_lock")

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self._rate = rate
        self._capacity = capacity or rate
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_for = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait_for)


class QuietHoursGate:
    """
    Evaluates whether an alert should be held/dropped during quiet hours.
    CRITICAL alerts always bypass quiet hours (unless override_on_suspicious=False).
    """

    def __init__(self, config) -> None:  # AlertsConfig.quiet_hours
        self._cfg = config

    def is_quiet_now(self) -> bool:
        if not self._cfg.enabled:
            return False
        now = datetime.now(UTC).strftime("%H:%M")
        start, end = self._cfg.start, self._cfg.end
        if start <= end:
            return start <= now < end
        # Wraps midnight: e.g. 23:00 - 07:00
        return now >= start or now < end

    def should_suppress(self, alert) -> bool:
        """Return True if this alert should be suppressed (held or dropped)."""
        from argus.alerts.models import AlertSeverity
        if not self.is_quiet_now():
            return False
        return not (self._cfg.override_on_suspicious and alert.severity == AlertSeverity.CRITICAL)


class AlertQueue:
    """
    Priority-aware alert queue.

    Priority mapping: CRITICAL=0, WARNING=1, INFO=2 (lower = higher priority).
    Held alerts (quiet hours + action=hold) are stored in _held and re-queued
    after the quiet window closes.
    """

    _PRIORITY = {"critical": 0, "warning": 1, "info": 2}

    def __init__(self, config) -> None:  # AlertsConfig
        self._cfg = config
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._held: list = []
        self._gate = QuietHoursGate(config.quiet_hours)
        self._limiter = TokenBucketRateLimiter(config.max_rate_per_second)
        self._running = False
        self._task: asyncio.Task | None = None

    async def put(self, alert) -> None:
        """Enqueue an alert, applying quiet-hours policy."""
        if self._gate.should_suppress(alert):
            action = self._cfg.quiet_hours.action
            if action == "hold":
                self._held.append(alert)
                logger.debug("Alert held (quiet hours)", alert_id=alert.alert_id, kind=alert.kind)
            else:
                logger.debug("Alert dropped (quiet hours)", alert_id=alert.alert_id, kind=alert.kind)
            return
        prio = self._PRIORITY.get(alert.severity.value, 1)
        await self._queue.put((prio, alert.created_at.timestamp(), alert))

    async def get(self):
        """Dequeue next alert (blocks until one is available)."""
        _, _, alert = await self._queue.get()
        return alert

    async def release_held(self) -> None:
        """Re-enqueue held alerts when quiet window closes."""
        if not self._held:
            return
        released = self._held[:]
        self._held.clear()
        for alert in released:
            await self.put(alert)
        logger.info("Released held alerts", count=len(released))

    def task_done(self) -> None:
        self._queue.task_done()
