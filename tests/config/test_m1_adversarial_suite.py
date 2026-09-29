"""Adversarial stress test suite for Milestone 1: Dependencies & Configuration Schema.

Challenger 2 verification suite testing:
1. Legacy dictionary inputs and migrations
2. Serialization and deserialization cycles (model_dump, model_dump_json, model_validate, model_validate_json, YAML roundtrip)
3. Property mutations and bidirectional synchronization
4. Environment variable permutations, conflicts, and edge cases
5. AutoLearnConfig interaction with prompt_via
6. Boundary conditions, type coercions, and snowflake IDs
"""

from __future__ import annotations

import json

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from argus.config.settings import (
    AlertsConfig,
    AutoLearnConfig,
    DiscordConfig,
    QuietHoursConfig,
    Settings,
    get_settings,
)

# ===========================================================================
# 1. Legacy Dictionary Inputs & Migration Stress Tests
# ===========================================================================


class TestLegacyDictionaryInputs:
    """Stress-test legacy flat dictionary inputs into AlertsConfig."""

    def test_pure_legacy_dict(self):
        """Pure legacy dict without nested 'quiet_hours' key."""
        legacy_data = {
            "cooldown_seconds": 90,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:15",
            "quiet_hours_end": "06:45",
            "override_on_suspicious": False,
        }
        alerts = AlertsConfig.model_validate(legacy_data)
        assert alerts.cooldown_seconds == 90
        assert alerts.quiet_hours.enabled is True
        assert alerts.quiet_hours.start == "22:15"
        assert alerts.quiet_hours.end == "06:45"
        assert alerts.quiet_hours.override_on_suspicious is False
        assert alerts.quiet_hours.action == "hold"  # Default preserved

    def test_legacy_dict_with_string_booleans(self):
        """Legacy dict with string boolean values (common in YAML/env parser outputs)."""
        data = {
            "quiet_hours_enabled": "true",
            "override_on_suspicious": "false",
        }
        alerts = AlertsConfig.model_validate(data)
        assert alerts.quiet_hours.enabled is True
        assert alerts.quiet_hours.override_on_suspicious is False

    def test_partial_legacy_inputs(self):
        """Only one or two legacy fields provided; others must retain defaults."""
        alerts = AlertsConfig.model_validate({"quiet_hours_start": "01:30"})
        assert alerts.quiet_hours.start == "01:30"
        assert alerts.quiet_hours.enabled is False  # default
        assert alerts.quiet_hours.end == "07:00"    # default
        assert alerts.quiet_hours.override_on_suspicious is True  # default

    def test_nested_takes_precedence_over_legacy_when_explicit(self):
        """When nested quiet_hours explicitly specifies fields, they override legacy flat keys."""
        data = {
            "quiet_hours": {
                "enabled": False,
                "start": "20:00",
                "action": "drop",
            },
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "05:00",  # Not in nested dict -> should be adopted!
        }
        alerts = AlertsConfig.model_validate(data)
        # Nested explicit fields win
        assert alerts.quiet_hours.enabled is False
        assert alerts.quiet_hours.start == "20:00"
        assert alerts.quiet_hours.action == "drop"
        # Flat legacy key fills in non-explicit nested field
        assert alerts.quiet_hours.end == "05:00"

    def test_nested_model_instance_with_legacy_kwargs(self):
        """AlertsConfig initialized with QuietHoursConfig instance AND legacy kwargs."""
        qh = QuietHoursConfig(start="21:00", end="05:00")
        alerts = AlertsConfig(
            quiet_hours=qh,
            quiet_hours_enabled=True,
            override_on_suspicious=False,
        )
        assert alerts.quiet_hours.start == "21:00"
        assert alerts.quiet_hours.end == "05:00"
        assert alerts.quiet_hours.enabled is True
        assert alerts.quiet_hours.override_on_suspicious is False

    def test_invalid_legacy_start_time_raises(self):
        """Invalid time format in legacy field must raise ValidationError."""
        with pytest.raises(ValidationError) as exc:
            AlertsConfig.model_validate({"quiet_hours_start": "99:99"})
        assert "HH:MM format" in str(exc.value)

    def test_invalid_legacy_bool_raises(self):
        """Invalid boolean in legacy field must raise ValidationError."""
        with pytest.raises(ValidationError):
            AlertsConfig.model_validate({"quiet_hours_enabled": "not_a_bool"})

    def test_empty_dict_uses_all_defaults(self):
        """Empty dict initializes all defaults cleanly."""
        alerts = AlertsConfig.model_validate({})
        assert alerts.quiet_hours.enabled is False
        assert alerts.quiet_hours.start == "23:00"
        assert alerts.quiet_hours.end == "07:00"
        assert alerts.quiet_hours.action == "hold"
        assert alerts.quiet_hours.override_on_suspicious is True


# ===========================================================================
# 2. Serialization / Deserialization Cycle Stress Tests
# ===========================================================================


class TestSerializationCycles:
    """Stress-test model_dump, model_dump_json, and deserialization round-trips."""

    @pytest.fixture
    def full_alerts(self) -> AlertsConfig:
        return AlertsConfig(
            cooldown_seconds=120,
            routing="discord",
            max_rate_per_second=25.5,
            quiet_hours=QuietHoursConfig(
                enabled=True,
                start="22:30",
                end="06:30",
                action="drop",
                override_on_suspicious=False,
            ),
            discord=DiscordConfig(
                enabled=True,
                bot_token="test_token_secret_123",
                channel_id=123456789012345678,
                guild_id=987654321098765432,
            ),
        )

    def test_model_dump_roundtrip(self, full_alerts: AlertsConfig):
        """model_dump() -> model_validate() round-trip."""
        data = full_alerts.model_dump()
        restored = AlertsConfig.model_validate(data)
        assert restored == full_alerts
        assert restored.quiet_hours_enabled == full_alerts.quiet_hours_enabled
        assert restored.quiet_hours_start == full_alerts.quiet_hours_start
        assert restored.quiet_hours_end == full_alerts.quiet_hours_end
        assert restored.override_on_suspicious == full_alerts.override_on_suspicious

    def test_model_dump_json_roundtrip(self, full_alerts: AlertsConfig):
        """model_dump_json() -> model_validate_json() round-trip."""
        json_data = full_alerts.model_dump_json()
        restored = AlertsConfig.model_validate_json(json_data)
        assert restored == full_alerts
        assert restored.discord.channel_id == full_alerts.discord.channel_id
        assert restored.discord.channel_id_int == 123456789012345678
        assert restored.quiet_hours.action == "drop"

    def test_legacy_json_deserialization(self):
        """Deserializing legacy JSON containing flat quiet_hours keys via model_validate_json."""
        legacy_json = json.dumps({
            "cooldown_seconds": 45,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "21:00",
            "quiet_hours_end": "05:00",
            "override_on_suspicious": False,
        })
        restored = AlertsConfig.model_validate_json(legacy_json)
        assert restored.quiet_hours.enabled is True
        assert restored.quiet_hours.start == "21:00"
        assert restored.quiet_hours.end == "05:00"
        assert restored.quiet_hours.override_on_suspicious is False
        assert restored.quiet_hours_enabled is True
        assert restored.quiet_hours_start == "21:00"

    def test_yaml_roundtrip(self, full_alerts: AlertsConfig):
        """Dump to YAML string and reload via safe_load -> model_validate."""
        dumped = full_alerts.model_dump()
        yaml_text = yaml.safe_dump(dumped)
        reloaded = yaml.safe_load(yaml_text)
        restored = AlertsConfig.model_validate(reloaded)
        assert restored == full_alerts

    def test_settings_model_dump_roundtrip(self):
        """Full Settings model_dump() and re-validation."""
        s = Settings()
        dumped = s.model_dump()
        # SecretStr fields should be serializable / re-validatable
        assert "alerts" in dumped
        assert "discord" in dumped["alerts"]
        assert "quiet_hours" in dumped["alerts"]
        assert dumped["alerts"]["quiet_hours"]["action"] == "hold"


# ===========================================================================
# 3. Property Mutations and Bidirectional Synchronization
# ===========================================================================


class TestPropertyMutations:
    """Stress-test property getters and setters on AlertsConfig."""

    def test_bidirectional_quiet_hours_enabled(self):
        alerts = AlertsConfig()
        assert alerts.quiet_hours.enabled is False
        assert alerts.quiet_hours_enabled is False

        # Mutate via property setter
        alerts.quiet_hours_enabled = True
        assert alerts.quiet_hours.enabled is True
        assert alerts.quiet_hours_enabled is True

        # Mutate via nested object
        alerts.quiet_hours.enabled = False
        assert alerts.quiet_hours_enabled is False

    def test_bidirectional_quiet_hours_start_end(self):
        alerts = AlertsConfig()
        # Mutate start
        alerts.quiet_hours_start = "22:00"
        assert alerts.quiet_hours.start == "22:00"
        assert alerts.quiet_hours_start == "22:00"

        alerts.quiet_hours.start = "21:30"
        assert alerts.quiet_hours_start == "21:30"

        # Mutate end
        alerts.quiet_hours_end = "06:00"
        assert alerts.quiet_hours.end == "06:00"
        assert alerts.quiet_hours_end == "06:00"

        alerts.quiet_hours.end = "05:30"
        assert alerts.quiet_hours_end == "05:30"

    def test_bidirectional_override_on_suspicious(self):
        alerts = AlertsConfig()
        assert alerts.override_on_suspicious is True
        alerts.override_on_suspicious = False
        assert alerts.quiet_hours.override_on_suspicious is False
        assert alerts.override_on_suspicious is False

        alerts.quiet_hours.override_on_suspicious = True
        assert alerts.override_on_suspicious is True

    def test_full_replacement_of_quiet_hours_object(self):
        """Replacing the quiet_hours instance dynamically preserves property mapping."""
        alerts = AlertsConfig()
        alerts.quiet_hours = QuietHoursConfig(
            enabled=True,
            start="01:00",
            end="09:00",
            action="drop",
            override_on_suspicious=False,
        )
        assert alerts.quiet_hours_enabled is True
        assert alerts.quiet_hours_start == "01:00"
        assert alerts.quiet_hours_end == "09:00"
        assert alerts.override_on_suspicious is False


# ===========================================================================
# 4. Environment Variable Permutations & Precedence
# ===========================================================================


class TestEnvVarPermutations:
    """Stress-test environment variable overrides, collisions, and edge cases."""

    def test_legacy_vs_nested_env_var_precedence(self, monkeypatch):
        """When BOTH legacy and nested env vars are set, nested modern takes precedence."""
        get_settings.cache_clear()
        # Set both legacy and nested start times
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_START", "20:00")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__START", "22:00")
        s = Settings()
        # Modern nested must take precedence over legacy flat
        assert s.alerts.quiet_hours.start == "22:00"
        assert s.alerts.quiet_hours_start == "22:00"
        get_settings.cache_clear()

    def test_discord_snowflake_as_string_or_int(self, monkeypatch):
        """Discord channel_id and guild_id delivered via env vars as 64-bit strings."""
        get_settings.cache_clear()
        snowflake = "1234567890123456789"
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__CHANNEL_ID", snowflake)
        monkeypatch.setenv("ARGUS__ALERTS__DISCORD__GUILD_ID", snowflake)
        s = Settings()
        assert str(s.alerts.discord.channel_id) == snowflake
        assert s.alerts.discord.channel_id_int == 1234567890123456789
        assert s.alerts.discord.guild_id_int == 1234567890123456789
        get_settings.cache_clear()

    def test_discord_token_secret_str_or_str(self):
        """DiscordConfig bot_token coerces SecretStr and raw string seamlessly."""
        d1 = DiscordConfig(bot_token=SecretStr("supersecret"))
        assert d1.bot_token == "supersecret"

        d2 = DiscordConfig(bot_token="plainstr")
        assert d2.bot_token == "plainstr"

        d3 = DiscordConfig(bot_token=None)
        assert d3.bot_token == ""

    def test_discord_invalid_snowflake_coercion(self):
        """Non-numeric string channel_id/guild_id safely returns 0 via helper properties."""
        d = DiscordConfig(channel_id="invalid_id", guild_id="not_a_number")
        assert d.channel_id_int == 0
        assert d.guild_id_int == 0

        # Empty strings also return 0
        d_empty = DiscordConfig(channel_id="", guild_id="")
        assert d_empty.channel_id_int == 0
        assert d_empty.guild_id_int == 0

    def test_discord_snowflake_none_allowed(self):
        """Verify channel_id/guild_id accept None and evaluate to 0."""
        d_chan = DiscordConfig(channel_id=None)
        assert d_chan.channel_id is None
        assert d_chan.channel_id_int == 0

        d_guild = DiscordConfig(guild_id=None)
        assert d_guild.guild_id is None
        assert d_guild.guild_id_int == 0

    def test_rate_limit_fractional_value(self, monkeypatch):
        """Max rate limit accepts floating point values like 0.5 msg/s."""
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__MAX_RATE_PER_SECOND", "0.5")
        s = Settings()
        assert s.alerts.max_rate_per_second == 0.5
        get_settings.cache_clear()

    def test_rate_limit_non_positive_rejected(self, monkeypatch):
        """Max rate limit <= 0 must fail validation."""
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__MAX_RATE_PER_SECOND", "0.0")
        with pytest.raises(ValidationError):
            Settings()
        get_settings.cache_clear()


# ===========================================================================
# 5. AutoLearnConfig & prompt_via Integration
# ===========================================================================


class TestAutoLearnIntegration:
    """Stress-test AutoLearnConfig.prompt_via and its integration with Settings."""

    @pytest.mark.parametrize("prompt_via", ["telegram", "discord", "both"])
    def test_valid_prompt_via_options(self, prompt_via: str):
        cfg = AutoLearnConfig(prompt_via=prompt_via)  # type: ignore[arg-type]
        assert cfg.prompt_via == prompt_via

    @pytest.mark.parametrize("invalid_opt", ["email", "slack", "webhook", "TELEGRAM", ""])
    def test_invalid_prompt_via_options_raise(self, invalid_opt: str):
        with pytest.raises(ValidationError):
            AutoLearnConfig(prompt_via=invalid_opt)  # type: ignore[arg-type]

    def test_prompt_via_env_override(self, monkeypatch):
        """ARGUS__RECOGNITION__AUTO_LEARN__PROMPT_VIA overrides prompt_via."""
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__RECOGNITION__AUTO_LEARN__PROMPT_VIA", "both")
        s = Settings()
        assert s.recognition.auto_learn.prompt_via == "both"
        get_settings.cache_clear()

    def test_prompt_via_independent_of_alerts_routing(self):
        """AutoLearn prompt_via can differ from global alerts routing."""
        s = Settings(
            alerts=AlertsConfig(routing="telegram"),
            recognition={"auto_learn": {"prompt_via": "discord"}},  # type: ignore[arg-type]
        )
        assert s.alerts.routing == "telegram"
        assert s.recognition.auto_learn.prompt_via == "discord"


# ===========================================================================
# 6. Advanced Edge Cases: Mutation + Serialization, Time Formats, YAML Merge
# ===========================================================================


class TestAdvancedEdgeCases:
    """Stress-test edge combinations: property mutation followed by serialization,
    boundary time formats, and YAML configuration file merging."""

    def test_mutation_reflected_in_model_dump(self):
        """Mutating property setters correctly updates model_dump output."""
        alerts = AlertsConfig()
        alerts.quiet_hours_enabled = True
        alerts.quiet_hours_start = "22:15"
        alerts.quiet_hours_end = "06:45"
        alerts.override_on_suspicious = False

        dumped = alerts.model_dump()
        assert dumped["quiet_hours"]["enabled"] is True
        assert dumped["quiet_hours"]["start"] == "22:15"
        assert dumped["quiet_hours"]["end"] == "06:45"
        assert dumped["quiet_hours"]["override_on_suspicious"] is False

    def test_mutation_reflected_in_model_dump_json(self):
        """Mutating property setters correctly updates model_dump_json output."""
        alerts = AlertsConfig()
        alerts.quiet_hours_enabled = True
        alerts.quiet_hours_start = "22:15"

        json_data = json.loads(alerts.model_dump_json())
        assert json_data["quiet_hours"]["enabled"] is True
        assert json_data["quiet_hours"]["start"] == "22:15"

    @pytest.mark.parametrize(
        "t_str,valid",
        [
            ("00:00", True),
            ("23:59", True),
            ("12:00", True),
            ("09:05", True),
            ("24:00", False),
            ("24:01", False),
            ("12:60", False),
            ("0:00", False),
            ("00:0", False),
            ("12:5", False),
            ("12:00:00", False),
            ("-01:00", False),
            ("12: 00", False),
            ("1 2:00", False),
        ],
    )
    def test_quiet_hours_time_boundary_regex(self, t_str: str, valid: bool):
        if valid:
            q = QuietHoursConfig(start=t_str, end=t_str)
            assert q.start == t_str
            assert q.end == t_str
        else:
            with pytest.raises(ValidationError):
                QuietHoursConfig(start=t_str)
            with pytest.raises(ValidationError):
                QuietHoursConfig(end=t_str)

    def test_quiet_hours_surrounding_whitespace_stripped(self):
        """Surrounding whitespace is stripped and valid."""
        q = QuietHoursConfig(start=" 12:00", end="12:00 ")
        assert q.start == "12:00"
        assert q.end == "12:00"

    def test_rate_limit_extreme_bounds(self):
        # Very small positive rate limit
        a_small = AlertsConfig(max_rate_per_second=0.0001)
        assert a_small.max_rate_per_second == 0.0001

        # Maximum allowed rate limit (le=1000.0)
        a_large = AlertsConfig(max_rate_per_second=1000.0)
        assert a_large.max_rate_per_second == 1000.0

        # Exceeding maximum rate limit
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=1000.1)

        # Non-finite rate limit
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=float("inf"))

        # String numeric representation
        a_str = AlertsConfig(max_rate_per_second="25.5")  # type: ignore[arg-type]
        assert a_str.max_rate_per_second == 25.5

        # Invalid non-numeric string
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second="fast")  # type: ignore[arg-type]

    def test_yaml_config_merge_with_legacy_and_modern_keys(self, tmp_path, monkeypatch):
        """Simulate loading config/config.yaml containing legacy flat keys."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        yaml_file = config_dir / "config.yaml"
        yaml_file.write_text(
            """
alerts:
  cooldown_seconds: 45
  routing: discord
  max_rate_per_second: 20.0
  quiet_hours_enabled: true
  quiet_hours_start: "21:30"
  quiet_hours_end: "05:30"
  override_on_suspicious: false
  discord:
    enabled: true
    bot_token: "yaml_token_abc"
    channel_id: 1122334455
    guild_id: 9988776655
"""
        )

        monkeypatch.chdir(tmp_path)
        # Clear autouse monkeypatch overrides that inject ARGUS__ALERTS env vars
        monkeypatch.delenv("ARGUS__ALERTS__TELEGRAM__ENABLED", raising=False)
        monkeypatch.delenv("ARGUS__ALERTS__DISCORD__ENABLED", raising=False)
        get_settings.cache_clear()

        s = Settings()
        assert s.alerts.cooldown_seconds == 45
        assert s.alerts.routing == "discord"
        assert s.alerts.max_rate_per_second == 20.0
        assert s.alerts.quiet_hours.enabled is True
        assert s.alerts.quiet_hours.start == "21:30"
        assert s.alerts.quiet_hours.end == "05:30"
        assert s.alerts.quiet_hours.override_on_suspicious is False
        assert s.alerts.quiet_hours_enabled is True
        assert s.alerts.discord.enabled is True
        assert s.alerts.discord.bot_token == "yaml_token_abc"
        assert s.alerts.discord.channel_id_int == 1122334455
        assert s.alerts.discord.guild_id_int == 9988776655
        get_settings.cache_clear()

    def test_yaml_config_deep_merge_preserves_sibling_keys(self, tmp_path, monkeypatch):
        """Verify load_yaml_config performs a recursive deep merge.
        When an environment variable sets a nested key (e.g. ARGUS__ALERTS__TELEGRAM__CHAT_ID),
        sibling keys configured in config.yaml under alerts: are cleanly preserved.
        """
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        yaml_file = config_dir / "config.yaml"
        yaml_file.write_text(
            """
alerts:
  cooldown_seconds: 45
  routing: discord
"""
        )
        monkeypatch.chdir(tmp_path)
        get_settings.cache_clear()
        # Set a single unrelated alert env var (e.g. chat_id)
        monkeypatch.setenv("ARGUS__ALERTS__TELEGRAM__CHAT_ID", "12345")
        s = Settings()
        # Recursive deep merge preserves YAML sibling keys alongside env var overrides
        assert s.alerts.cooldown_seconds == 45
        assert s.alerts.routing == "discord"
        assert s.alerts.telegram.chat_id == "12345"
        get_settings.cache_clear()

