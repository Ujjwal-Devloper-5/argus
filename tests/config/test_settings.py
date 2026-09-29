"""Tests for Argus Settings (argus/config/settings.py)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from argus.config.settings import (
    AlertsConfig,
    AutoLearnConfig,
    CameraConfig,
    DetectionConfig,
    DiscordConfig,
    QuietHoursConfig,
    Settings,
    get_settings,
)


class TestCameraConfig:
    def test_valid_camera_name(self):
        cam = CameraConfig(name="front_door", rtsp_url="rtsp://test/stream")
        assert cam.name == "front_door"

    def test_camera_name_lowercased(self):
        cam = CameraConfig(name="FrontDoor", rtsp_url="rtsp://test/stream")
        assert cam.name == "frontdoor"

    def test_invalid_camera_name_raises(self):
        with pytest.raises(ValueError, match="Camera name must contain only"):
            CameraConfig(name="front door!", rtsp_url="rtsp://test/stream")

    def test_disabled_defaults_to_false(self):
        cam = CameraConfig(name="cam1", rtsp_url="rtsp://test/stream")
        assert cam.disabled is False


class TestDetectionConfig:
    def test_defaults(self):
        d = DetectionConfig()
        assert d.model == "yolov8n.pt"
        assert d.confidence == 0.60
        assert d.classes == [0]
        assert d.device == "auto"

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            DetectionConfig(confidence=1.5)
        with pytest.raises(ValueError):
            DetectionConfig(confidence=0.0)


class TestSettings:
    def test_settings_loads_with_defaults(self, settings: Settings):
        assert settings.app_name == "Argus"
        assert settings.llm.provider == "disabled"
        assert settings.alerts.telegram.enabled is False

    def test_database_url_overridden_in_tests(self, settings: Settings):
        assert ":memory:" in settings.database_url

    def test_no_active_cameras_warning(self, settings: Settings):
        # No cameras configured — should warn but not raise
        assert settings.cameras == []

    def test_get_settings_is_cached(self, settings: Settings):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_openai_provider_without_key_raises(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__LLM__PROVIDER", "openai")
        monkeypatch.delenv("ARGUS__LLM__OPENAI__API_KEY", raising=False)
        with pytest.raises(ValueError, match="ARGUS__LLM__OPENAI__API_KEY"):
            Settings()
        get_settings.cache_clear()


class TestDiscordConfig:
    def test_discord_defaults(self):
        d = DiscordConfig()
        assert d.enabled is False
        assert d.bot_token == ""
        assert d.channel_id in (0, "0", "", None)
        assert d.guild_id in (0, "0", "", None)
        assert d.channel_id_int == 0
        assert d.guild_id_int == 0

    def test_discord_custom_values(self):
        d = DiscordConfig(
            enabled=True,
            bot_token="test_token_123",
            channel_id=123456789012345678,
            guild_id=987654321098765432,
        )
        assert d.enabled is True
        token = d.bot_token.get_secret_value() if hasattr(d.bot_token, "get_secret_value") else d.bot_token
        assert token == "test_token_123"
        assert int(d.channel_id) == 123456789012345678
        assert int(d.guild_id) == 987654321098765432
        assert d.channel_id_int == 123456789012345678
        assert d.guild_id_int == 987654321098765432

    def test_discord_token_coercion(self):
        d_str = DiscordConfig(bot_token="token_xyz")
        assert d_str.bot_token == "token_xyz"

        d_secret = DiscordConfig(bot_token=SecretStr("token_sec"))
        assert d_secret.bot_token == "token_sec"

        d_none = DiscordConfig(bot_token=None)
        assert d_none.bot_token == ""

    def test_discord_channel_id_helpers(self):
        d1 = DiscordConfig(channel_id="123456789012345678", guild_id="9876543210")
        assert str(d1.channel_id) == "123456789012345678"
        assert d1.channel_id_int == 123456789012345678
        assert d1.guild_id_int == 9876543210

        d2 = DiscordConfig(channel_id=42, guild_id=99)
        assert int(d2.channel_id) == 42
        assert d2.channel_id_int == 42
        assert d2.guild_id_int == 99

        d3 = DiscordConfig(channel_id="invalid", guild_id="")
        assert d3.channel_id_int == 0
        assert d3.guild_id_int == 0

        d4 = DiscordConfig(channel_id=None, guild_id=None)
        assert d4.channel_id is None
        assert d4.guild_id is None
        assert d4.channel_id_int == 0
        assert d4.guild_id_int == 0


class TestQuietHoursConfig:
    def test_quiet_hours_defaults(self):
        q = QuietHoursConfig()
        assert q.enabled is False
        assert q.start == "23:00"
        assert q.end == "07:00"
        assert q.override_on_suspicious is True
        assert q.action == "hold"

    def test_quiet_hours_action_options(self):
        q_hold = QuietHoursConfig(action="hold")
        assert q_hold.action == "hold"
        q_drop = QuietHoursConfig(action="drop")
        assert q_drop.action == "drop"

    def test_quiet_hours_invalid_action_raises(self):
        with pytest.raises(ValidationError):
            QuietHoursConfig(action="discard")
        with pytest.raises(ValidationError):
            QuietHoursConfig(action="ignore")

    @pytest.mark.parametrize("valid_time", ["00:00", "07:00", "12:30", "23:59", "22:00"])
    def test_quiet_hours_valid_times(self, valid_time: str):
        q = QuietHoursConfig(start=valid_time, end=valid_time)
        assert q.start == valid_time
        assert q.end == valid_time

    def test_quiet_hours_whitespace_stripped(self):
        q = QuietHoursConfig(start=" 23:00\n", end="\t07:00\r\n")
        assert q.start == "23:00"
        assert q.end == "07:00"

    @pytest.mark.parametrize("invalid_time", ["25:00", "12:60", "7:00", "noon", "24:00", ""])
    def test_quiet_hours_invalid_times_raise(self, invalid_time: str):
        with pytest.raises(ValidationError):
            QuietHoursConfig(start=invalid_time)
        with pytest.raises(ValidationError):
            QuietHoursConfig(end=invalid_time)

    def test_quiet_hours_custom_schedule(self):
        q = QuietHoursConfig(
            enabled=True,
            start="22:00",
            end="06:00",
            override_on_suspicious=False,
            action="drop",
        )
        assert q.enabled is True
        assert q.start == "22:00"
        assert q.end == "06:00"
        assert q.override_on_suspicious is False
        assert q.action == "drop"


class TestAlertsConfig:
    def test_alerts_config_defaults(self):
        a = AlertsConfig()
        assert a.cooldown_seconds == 60
        assert a.telegram.enabled is False
        assert a.discord.enabled is False
        assert a.quiet_hours.enabled is False
        assert a.quiet_hours.action == "hold"
        assert a.routing == "both"
        assert a.max_rate_per_second == 30.0

    @pytest.mark.parametrize("routing_opt", ["telegram", "discord", "both"])
    def test_alerts_routing_valid(self, routing_opt: str):
        a = AlertsConfig(routing=routing_opt)  # type: ignore[arg-type]
        assert a.routing == routing_opt

    def test_alerts_routing_invalid_raises(self):
        with pytest.raises(ValidationError):
            AlertsConfig(routing="slack")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            AlertsConfig(routing="all")  # type: ignore[arg-type]

    def test_alerts_rate_limit_bounds(self):
        a = AlertsConfig(max_rate_per_second=15.0)
        assert a.max_rate_per_second == 15.0
        a_max = AlertsConfig(max_rate_per_second=1000.0)
        assert a_max.max_rate_per_second == 1000.0
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=0.0)
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=-5.0)
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=1001.0)
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=float("inf"))

    def test_alerts_backward_compatibility_properties(self):
        a = AlertsConfig(
            quiet_hours=QuietHoursConfig(
                enabled=True,
                start="21:00",
                end="08:00",
                override_on_suspicious=False,
                action="drop",
            )
        )
        assert a.quiet_hours_enabled is True
        assert a.quiet_hours_start == "21:00"
        assert a.quiet_hours_end == "08:00"
        assert a.override_on_suspicious is False

        # Property setters
        a.quiet_hours_enabled = False
        a.quiet_hours_start = "22:00"
        a.quiet_hours_end = "06:00"
        a.override_on_suspicious = True
        assert a.quiet_hours.enabled is False
        assert a.quiet_hours.start == "22:00"
        assert a.quiet_hours.end == "06:00"
        assert a.quiet_hours.override_on_suspicious is True

    def test_alerts_backward_compatibility_flat_kwargs(self):
        a = AlertsConfig(
            quiet_hours_enabled=True,
            quiet_hours_start="22:30",
            quiet_hours_end="06:30",
            override_on_suspicious=False,
        )
        assert a.quiet_hours.enabled is True
        assert a.quiet_hours.start == "22:30"
        assert a.quiet_hours.end == "06:30"
        assert a.quiet_hours.override_on_suspicious is False

    def test_alerts_backward_compatibility_nested_and_flat_mixed(self):
        a = AlertsConfig(
            quiet_hours=QuietHoursConfig(start="22:00"),
            quiet_hours_end="05:00",
        )
        assert a.quiet_hours.start == "22:00"
        assert a.quiet_hours.end == "05:00"


class TestAutoLearnConfig:
    def test_autolearn_defaults(self):
        al = AutoLearnConfig()
        assert al.enabled is True
        assert al.appearances_before_prompt == 5
        assert al.prompt_via == "telegram"

    @pytest.mark.parametrize("prompt_opt", ["telegram", "discord", "both"])
    def test_autolearn_prompt_via_valid(self, prompt_opt: str):
        al = AutoLearnConfig(prompt_via=prompt_opt)  # type: ignore[arg-type]
        assert al.prompt_via == prompt_opt

    def test_autolearn_prompt_via_invalid_raises(self):
        with pytest.raises(ValidationError):
            AutoLearnConfig(prompt_via="slack")  # type: ignore[arg-type]


class TestAlertSettingsIntegration:
    def test_settings_alerts_defaults(self, settings: Settings):
        assert settings.alerts.discord.enabled is False
        assert settings.alerts.routing == "both"
        assert settings.alerts.max_rate_per_second == 30.0
        assert settings.alerts.quiet_hours.action == "hold"

    def test_settings_discord_env_overrides(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__ENABLED", "true")
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__BOT_TOKEN", "mock-bot-token")
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__CHANNEL_ID", "999888777")
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__GUILD_ID", "111222333")
        s = Settings()
        assert s.alerts.discord.enabled is True
        token = (
            s.alerts.discord.bot_token.get_secret_value()
            if hasattr(s.alerts.discord.bot_token, "get_secret_value")
            else s.alerts.discord.bot_token
        )
        assert token == "mock-bot-token"
        assert str(s.alerts.discord.channel_id) == "999888777"
        assert s.alerts.discord.channel_id_int == 999888777
        assert s.alerts.discord.guild_id_int == 111222333
        get_settings.cache_clear()

    def test_settings_quiet_hours_env_overrides(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__ENABLED", "true")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__START", "22:15")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__END", "05:45")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__ACTION", "drop")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__OVERRIDE_ON_SUSPICIOUS", "false")
        s = Settings()
        assert s.alerts.quiet_hours.enabled is True
        assert s.alerts.quiet_hours.start == "22:15"
        assert s.alerts.quiet_hours.end == "05:45"
        assert s.alerts.quiet_hours.action == "drop"
        assert s.alerts.quiet_hours.override_on_suspicious is False
        get_settings.cache_clear()

    def test_settings_legacy_quiet_hours_env_overrides(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_ENABLED", "true")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_START", "21:00")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_END", "06:00")
        monkeypatch.setenv("ARGUS__ALERTS__OVERRIDE_ON_SUSPICIOUS", "false")
        s = Settings()
        assert s.alerts.quiet_hours_enabled is True
        assert s.alerts.quiet_hours.enabled is True
        assert s.alerts.quiet_hours.start == "21:00"
        assert s.alerts.quiet_hours.end == "06:00"
        assert s.alerts.override_on_suspicious is False
        assert s.alerts.quiet_hours.override_on_suspicious is False
        get_settings.cache_clear()

    def test_settings_routing_and_rate_limit_env_overrides(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__ROUTING", "discord")
        monkeypatch.setenv("ARGUS__ALERTS__MAX_RATE_PER_SECOND", "15.5")
        s = Settings()
        assert s.alerts.routing == "discord"
        assert s.alerts.max_rate_per_second == 15.5
        get_settings.cache_clear()

    def test_settings_invalid_routing_env_raises(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__ROUTING", "invalid_platform")
        with pytest.raises(ValidationError):
            Settings()
        get_settings.cache_clear()
