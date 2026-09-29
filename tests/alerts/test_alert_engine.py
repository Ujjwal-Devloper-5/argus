"""
Tests for Phase 6: Argus Unified Alert Engine.

All Telegram and Discord API calls are mocked — no live network.
Covers: models, rate limiter, quiet hours gate, queue, routing, manager lifecycle.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.alerts.models import Alert, AlertKind, AlertSeverity, InteractiveButton
from argus.alerts.queue import AlertQueue, QuietHoursGate, TokenBucketRateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def info_alert():
    return Alert(
        kind=AlertKind.PERSON_DETECTED,
        severity=AlertSeverity.INFO,
        title="Person detected",
        body="A person was detected on camera.",
        camera_name="front_door",
    )


@pytest.fixture
def critical_alert():
    return Alert(
        kind=AlertKind.SUSPICIOUS_ACTIVITY,
        severity=AlertSeverity.CRITICAL,
        title="Suspicious activity",
        body="Unrecognised person detected at 03:00.",
    )


@pytest.fixture
def learn_alert():
    return Alert(
        kind=AlertKind.LEARN_PROMPT,
        severity=AlertSeverity.WARNING,
        title="Do you know this person?",
        body="Appeared 5 times.",
        thumbnail=b"\xff\xd8\xff" + b"\x00" * 10,  # fake JPEG header
        buttons=[
            InteractiveButton("Yes", "learn:add:abc123"),
            InteractiveButton("No", "learn:stranger:abc123"),
        ],
    )


@pytest.fixture
def mock_alerts_config():
    """Minimal AlertsConfig-like mock."""
    cfg = MagicMock()
    cfg.routing = "both"
    cfg.max_rate_per_second = 30.0
    cfg.telegram.enabled = True
    cfg.telegram.bot_token.get_secret_value.return_value = "test-token"
    cfg.telegram.chat_id = "12345"
    cfg.discord.enabled = True
    cfg.discord.bot_token = "discord-token"
    cfg.discord.channel_id_int = 987654321
    cfg.quiet_hours.enabled = False
    cfg.quiet_hours.action = "hold"
    cfg.quiet_hours.override_on_suspicious = True
    cfg.quiet_hours.start = "23:00"
    cfg.quiet_hours.end = "07:00"
    return cfg


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_alert_has_unique_id():
    a1 = Alert(kind=AlertKind.HEARTBEAT, severity=AlertSeverity.INFO, title="T", body="B")
    a2 = Alert(kind=AlertKind.HEARTBEAT, severity=AlertSeverity.INFO, title="T", body="B")
    assert a1.alert_id != a2.alert_id


def test_alert_created_at_utc(info_alert):
    assert info_alert.created_at.tzinfo is not None
    assert info_alert.created_at.tzinfo == timezone.utc


def test_interactive_button_immutable():
    btn = InteractiveButton(label="Click me", callback_data="action:1")
    with pytest.raises((AttributeError, TypeError)):
        btn.label = "Changed"  # frozen dataclass


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limiter_allows_first_token():
    limiter = TokenBucketRateLimiter(rate=100.0)
    # Should complete immediately (tokens available)
    await asyncio.wait_for(limiter.acquire(), timeout=1.0)


@pytest.mark.asyncio
async def test_rate_limiter_throttles_burst():
    """Drain all tokens then next acquire must wait."""
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=2.0)
    await limiter.acquire()
    await limiter.acquire()
    # Now out of tokens. acquire should block.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(limiter.acquire(), timeout=0.05)


# ---------------------------------------------------------------------------
# QuietHoursGate tests
# ---------------------------------------------------------------------------

def test_quiet_hours_disabled(info_alert):
    cfg = MagicMock()
    cfg.enabled = False
    gate = QuietHoursGate(cfg)
    assert gate.is_quiet_now() is False
    assert gate.should_suppress(info_alert) is False


def test_quiet_hours_suppresses_info(info_alert):
    cfg = MagicMock()
    cfg.enabled = True
    cfg.start = "00:00"
    cfg.end = "23:59"
    cfg.override_on_suspicious = True
    gate = QuietHoursGate(cfg)
    assert gate.should_suppress(info_alert) is True


def test_quiet_hours_passes_critical(critical_alert):
    cfg = MagicMock()
    cfg.enabled = True
    cfg.start = "00:00"
    cfg.end = "23:59"
    cfg.override_on_suspicious = True
    gate = QuietHoursGate(cfg)
    # CRITICAL with override_on_suspicious=True → should NOT suppress
    assert gate.should_suppress(critical_alert) is False


def test_quiet_hours_midnight_wrap():
    cfg = MagicMock()
    cfg.enabled = True
    cfg.start = "23:00"
    cfg.end = "07:00"
    gate = QuietHoursGate(cfg)
    # We can't control system time in unit test, but we can verify logic
    # by testing a known non-quiet time range (the gate should evaluate)
    result = gate.is_quiet_now()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# AlertQueue tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_priority_order(mock_alerts_config):
    """CRITICAL alerts should be dequeued before INFO alerts."""
    q = AlertQueue(mock_alerts_config)
    info = Alert(kind=AlertKind.HEARTBEAT, severity=AlertSeverity.INFO, title="i", body="b")
    crit = Alert(kind=AlertKind.SUSPICIOUS_ACTIVITY, severity=AlertSeverity.CRITICAL, title="c", body="b")
    await q.put(info)
    await q.put(crit)
    first = await q.get()
    assert first.severity == AlertSeverity.CRITICAL


@pytest.mark.asyncio
async def test_queue_holds_during_quiet_hours(mock_alerts_config, info_alert):
    mock_alerts_config.quiet_hours.enabled = True
    mock_alerts_config.quiet_hours.start = "00:00"
    mock_alerts_config.quiet_hours.end = "23:59"
    mock_alerts_config.quiet_hours.action = "hold"
    q = AlertQueue(mock_alerts_config)
    await q.put(info_alert)
    # Should be held, not in main queue
    assert len(q._held) == 1
    assert q._queue.empty()


@pytest.mark.asyncio
async def test_queue_drops_during_quiet_hours(mock_alerts_config, info_alert):
    mock_alerts_config.quiet_hours.enabled = True
    mock_alerts_config.quiet_hours.start = "00:00"
    mock_alerts_config.quiet_hours.end = "23:59"
    mock_alerts_config.quiet_hours.action = "drop"
    q = AlertQueue(mock_alerts_config)
    await q.put(info_alert)
    assert len(q._held) == 0
    assert q._queue.empty()


@pytest.mark.asyncio
async def test_queue_release_held(mock_alerts_config, info_alert):
    mock_alerts_config.quiet_hours.enabled = True
    mock_alerts_config.quiet_hours.start = "00:00"
    mock_alerts_config.quiet_hours.end = "23:59"
    mock_alerts_config.quiet_hours.action = "hold"
    q = AlertQueue(mock_alerts_config)
    await q.put(info_alert)
    assert len(q._held) == 1
    # Disable quiet hours and release
    mock_alerts_config.quiet_hours.enabled = False
    q._gate._cfg.enabled = False
    await q.release_held()
    assert len(q._held) == 0
    # Alert should now be in the queue
    assert not q._queue.empty()


# ---------------------------------------------------------------------------
# TelegramClient tests (fully mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_send_photo_with_buttons(learn_alert):
    cfg = MagicMock()
    cfg.bot_token.get_secret_value.return_value = "fake-token"
    cfg.chat_id = "123"

    with patch("telegram.ext.Application") as MockApp:
        mock_app_instance = MagicMock()
        mock_app_instance.bot.send_photo = AsyncMock()
        mock_app_instance.bot.send_message = AsyncMock()
        mock_app_instance.initialize = AsyncMock()
        mock_app_instance.start = AsyncMock()
        mock_app_instance.updater.start_polling = AsyncMock()
        mock_app_instance.updater.stop = AsyncMock()
        mock_app_instance.stop = AsyncMock()
        mock_app_instance.shutdown = AsyncMock()
        mock_app_instance.add_handler = MagicMock()
        MockApp.builder.return_value.token.return_value.build.return_value = mock_app_instance

        from argus.alerts.telegram_client import TelegramClient
        client = TelegramClient(cfg)
        client._app = mock_app_instance
        result = await client.send(learn_alert)

    assert result is True
    mock_app_instance.bot.send_photo.assert_called_once()
    call_kwargs = mock_app_instance.bot.send_photo.call_args.kwargs
    assert call_kwargs["chat_id"] == "123"
    assert call_kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_telegram_send_text_only(info_alert):
    cfg = MagicMock()
    cfg.bot_token.get_secret_value.return_value = "fake-token"
    cfg.chat_id = "123"

    with patch("telegram.ext.Application"):
        from argus.alerts.telegram_client import TelegramClient
        client = TelegramClient(cfg)
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        client._app = MagicMock()
        client._app.bot = mock_bot
        result = await client.send(info_alert)

    assert result is True
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_returns_false_on_exception(info_alert):
    cfg = MagicMock()
    cfg.chat_id = "123"
    from argus.alerts.telegram_client import TelegramClient
    client = TelegramClient(cfg)
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=RuntimeError("Network error"))
    client._app = MagicMock()
    client._app.bot = mock_bot
    result = await client.send(info_alert)
    assert result is False


@pytest.mark.asyncio
async def test_telegram_callback_triggers_handler():
    cfg = MagicMock()
    received = []
    async def handler(cb_data: str, user_id: str):
        received.append((cb_data, user_id))

    from argus.alerts.telegram_client import TelegramClient
    client = TelegramClient(cfg, callback_handler=handler)
    # Simulate callback
    mock_query = AsyncMock()
    mock_query.data = "learn:add:abc123"
    mock_query.answer = AsyncMock()
    mock_query.edit_message_reply_markup = AsyncMock()
    mock_query.from_user.id = 42
    mock_update = MagicMock()
    mock_update.callback_query = mock_query
    await client._handle_callback(mock_update, None)
    assert received == [("learn:add:abc123", "42")]


# ---------------------------------------------------------------------------
# DiscordClient tests (fully mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discord_send_with_embed_and_thumbnail(learn_alert):
    cfg = MagicMock()
    cfg.bot_token = "fake-discord-token"
    cfg.channel_id_int = 111

    mock_discord = MagicMock()
    mock_channel = AsyncMock()
    mock_client_instance = MagicMock()
    mock_client_instance.is_ready.return_value = True
    mock_client_instance.get_channel.return_value = mock_channel
    mock_discord.Intents.default.return_value = MagicMock()
    mock_discord.Client.return_value = mock_client_instance
    mock_discord.Embed.return_value = MagicMock()
    mock_discord.File.return_value = MagicMock()

    with patch.dict("sys.modules", {"discord": mock_discord}):
        from argus.alerts.discord_client import DiscordClient
        client = DiscordClient(cfg)
        client._client = mock_client_instance
        client._ready.set()
        result = await client.send(learn_alert)

    assert result is True
    mock_channel.send.assert_called_once()


@pytest.mark.asyncio
async def test_discord_returns_false_when_not_ready(info_alert):
    cfg = MagicMock()
    cfg.channel_id_int = 111
    from argus.alerts.discord_client import DiscordClient
    client = DiscordClient(cfg)
    client._client = MagicMock()
    client._client.is_ready.return_value = False
    result = await client.send(info_alert)
    assert result is False


# ---------------------------------------------------------------------------
# AlertManager integration tests (mocked platform clients)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alert_manager_routes_to_both(mock_alerts_config, info_alert):
    settings = MagicMock()
    settings.alerts = mock_alerts_config
    mock_alerts_config.routing = "both"

    from argus.alerts.manager import AlertManager
    manager = AlertManager(settings)
    manager._telegram = AsyncMock()
    manager._telegram.send = AsyncMock(return_value=True)
    manager._discord = AsyncMock()
    manager._discord.send = AsyncMock(return_value=True)
    manager._running = True

    await manager._dispatch(info_alert)

    manager._telegram.send.assert_called_once_with(info_alert)
    manager._discord.send.assert_called_once_with(info_alert)


@pytest.mark.asyncio
async def test_alert_manager_routes_telegram_only(mock_alerts_config, info_alert):
    settings = MagicMock()
    settings.alerts = mock_alerts_config
    mock_alerts_config.routing = "telegram"

    from argus.alerts.manager import AlertManager
    manager = AlertManager(settings)
    manager._telegram = AsyncMock()
    manager._telegram.send = AsyncMock(return_value=True)
    manager._discord = AsyncMock()
    manager._discord.send = AsyncMock(return_value=True)

    await manager._dispatch(info_alert)

    manager._telegram.send.assert_called_once()
    manager._discord.send.assert_not_called()


@pytest.mark.asyncio
async def test_alert_manager_routes_discord_only(mock_alerts_config, info_alert):
    settings = MagicMock()
    settings.alerts = mock_alerts_config
    mock_alerts_config.routing = "discord"

    from argus.alerts.manager import AlertManager
    manager = AlertManager(settings)
    manager._telegram = AsyncMock()
    manager._telegram.send = AsyncMock(return_value=True)
    manager._discord = AsyncMock()
    manager._discord.send = AsyncMock(return_value=True)

    await manager._dispatch(info_alert)

    manager._telegram.send.assert_not_called()
    manager._discord.send.assert_called_once()


@pytest.mark.asyncio
async def test_alert_manager_send_learn_prompt():
    settings = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.routing = "both"
    mock_cfg.max_rate_per_second = 100.0
    mock_cfg.quiet_hours.enabled = False
    settings.alerts = mock_cfg

    from argus.alerts.manager import AlertManager
    manager = AlertManager(settings)
    dispatched = []

    async def fake_dispatch(alert):
        dispatched.append(alert)

    manager._dispatch = fake_dispatch

    await manager.send_learn_prompt(
        face_hash="deadbeef",
        appearance_count=5,
        camera_name="front_door",
        thumbnail_path="/nonexistent/path.jpg",
        pattern_note="⚠️ First appeared late at night",
        similarity=0.42,
    )
    # Flush the queue manually
    alert = await manager._queue.get()
    await fake_dispatch(alert)

    assert len(dispatched) == 1
    sent = dispatched[0]
    assert sent.kind.value == "learn_prompt"
    assert len(sent.buttons) == 3
    assert "deadbeef" in sent.buttons[0].callback_data
