"""Adversarial stress-testing suite for Argus Settings (Milestone 1).

Covers:
- Extreme snowflake IDs (signed/unsigned 64-bit max, negative, non-numeric, floats, large ints)
- Boundary 24-hour time strings and malformed times
- Boundary rate limits (inf, nan, negative, zero, fractional)
- Environment variable permutations and legacy vs nested precedence
- Fuzzing / exception safety: invalid inputs raise ValidationError, never unhandled exceptions.
- Bug reproductions for trailing newlines and null channel/guild IDs.
"""

from __future__ import annotations

import random
import string
from datetime import datetime

import pytest
from pydantic import SecretStr, ValidationError

from argus.config.settings import (
    AlertsConfig,
    DiscordConfig,
    QuietHoursConfig,
    Settings,
    get_settings,
)

# ===========================================================================
# 1. Extreme Snowflake IDs & DiscordConfig Boundaries
# ===========================================================================

class TestDiscordSnowflakeAdversarial:
    """Stress test DiscordConfig channel_id and guild_id edge cases."""

    @pytest.mark.parametrize(
        ("val", "expected_int"),
        [
            (0, 0),
            ("0", 0),
            ("", 0),
            ("   ", 0),
            (123456789012345678, 123456789012345678),
            ("123456789012345678", 123456789012345678),
            # Signed 64-bit max (2^63 - 1)
            (9223372036854775807, 9223372036854775807),
            (str(9223372036854775807), 9223372036854775807),
            # Unsigned 64-bit max (2^64 - 1) - standard Discord snowflake ceiling
            (18446744073709551615, 18446744073709551615),
            (str(18446744073709551615), 18446744073709551615),
            # Extreme arbitrary precision integer (100 digits)
            (10**100, 10**100),
            (str(10**100), 10**100),
            # Negative integers
            (-1, -1),
            ("-1", -1),
            (-9223372036854775808, -9223372036854775808),
            # Non-numeric strings safe fallback to 0
            ("non_numeric", 0),
            ("123.456", 0),
            ("1e18", 0),
            ("0x1234", 0),
            ("!@#$%^&*()_+", 0),
            ("   123   ", 123),  # int("   123   ") parses as 123 in Python
            ("true", 0),
            ("false", 0),
        ],
    )
    def test_channel_id_edge_cases(self, val, expected_int):
        cfg = DiscordConfig(channel_id=val)
        assert cfg.channel_id_int == expected_int

    @pytest.mark.parametrize(
        ("val", "expected_int"),
        [
            (0, 0),
            ("0", 0),
            (18446744073709551615, 18446744073709551615),
            ("-999", -999),
            ("invalid_guild", 0),
        ],
    )
    def test_guild_id_edge_cases(self, val, expected_int):
        cfg = DiscordConfig(guild_id=val)
        assert cfg.guild_id_int == expected_int

    def test_discord_unsupported_complex_types_raise(self):
        """Objects, dicts, lists must raise ValidationError on channel_id/guild_id."""
        with pytest.raises(ValidationError):
            DiscordConfig(channel_id=[12345])  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            DiscordConfig(channel_id={"id": 12345})  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            DiscordConfig(guild_id=[98765])  # type: ignore[arg-type]

    def test_discord_token_coercion_adversarial(self):
        # SecretStr unwraps
        assert DiscordConfig(bot_token=SecretStr("sec_val")).bot_token == "sec_val"
        # None coerces to empty string
        assert DiscordConfig(bot_token=None).bot_token == ""
        # Numbers coerce to string
        assert DiscordConfig(bot_token=123456).bot_token == "123456"
        # Long token with punctuation
        long_tok = "MTAwMTIzNDU2Nzg5MDEyMzQ1Ng.G1xYzA." + "A" * 64
        assert DiscordConfig(bot_token=long_tok).bot_token == long_tok

    def test_discord_null_id_accepted(self):
        """Verify passing channel_id=None or guild_id=None is accepted and evaluates to 0.

        In YAML, 'channel_id: null' or leaving the key empty results in None, which is
        safely accepted with type `int | str | None = 0` and helper properties return 0.
        """
        d_chan = DiscordConfig(channel_id=None)
        assert d_chan.channel_id is None
        assert d_chan.channel_id_int == 0

        d_guild = DiscordConfig(guild_id=None)
        assert d_guild.guild_id is None
        assert d_guild.guild_id_int == 0

        d_both = DiscordConfig(channel_id=None, guild_id=None)
        assert d_both.channel_id is None
        assert d_both.guild_id is None
        assert d_both.channel_id_int == 0
        assert d_both.guild_id_int == 0


# ===========================================================================
# 2. Boundary Time Values & Malformed Times (QuietHoursConfig)
# ===========================================================================

class TestQuietHoursAdversarial:
    """Stress test 24h time regex, boundary values, and action options."""

    @pytest.mark.parametrize(
        "valid_boundary_time",
        [
            "00:00",  # Midnight boundary
            "00:01",
            "01:00",
            "09:59",
            "10:00",
            "11:59",
            "12:00",  # Noon
            "12:01",
            "13:00",
            "22:59",
            "23:00",
            "23:58",
            "23:59",  # Last minute of 24h day
        ],
    )
    def test_valid_boundary_times(self, valid_boundary_time: str):
        q = QuietHoursConfig(start=valid_boundary_time, end=valid_boundary_time)
        assert q.start == valid_boundary_time
        assert q.end == valid_boundary_time

    @pytest.mark.parametrize(
        "malformed_time",
        [
            # Overflow hours
            "24:00",
            "24:01",
            "25:00",
            "99:00",
            # Overflow minutes
            "00:60",
            "12:60",
            "23:60",
            "05:99",
            # Single digit hour / minute (missing leading zeros)
            "0:00",
            "7:00",
            "9:30",
            "09:5",
            "23:0",
            # Internal whitespace / malformed spacing
            "00: 00",
            "0 0:00",
            "00 :00",
            "23:59:00",  # 3-part time with seconds
            "23:59.00",
            # Separators
            "12-00",
            "12.00",
            "1200",
            "12 00",
            # Alphabetic / textual
            "noon",
            "midnight",
            "now",
            "12:00pm",
            "11:00am",
            # Empty / whitespace
            "",
            "   ",
            ":",
            "::",
            # Negative
            "-01:00",
            "00:-05",
        ],
    )
    def test_malformed_times_raise_validation_error(self, malformed_time: str):
        with pytest.raises(ValidationError) as exc_info:
            QuietHoursConfig(start=malformed_time)
        assert "HH:MM format" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            QuietHoursConfig(end=malformed_time)
        assert "HH:MM format" in str(exc_info.value)

    def test_quiet_hours_trailing_newline_and_whitespace_sanitization(self):
        """Verify trailing newlines and surrounding whitespace are stripped and normalized."""
        q = QuietHoursConfig(start="00:00\n", end="23:59\n")
        assert q.start == "00:00"
        assert q.end == "23:59"

        t_start = datetime.strptime(q.start, "%H:%M")
        t_end = datetime.strptime(q.end, "%H:%M")
        assert t_start.hour == 0 and t_start.minute == 0
        assert t_end.hour == 23 and t_end.minute == 59

    @pytest.mark.parametrize(
        ("raw_input", "expected_output"),
        [
            (" 00:00", "00:00"),
            ("00:00 ", "00:00"),
            ("00:00\t", "00:00"),
            ("\r\n23:00\r\n", "23:00"),
            ("   12:30   ", "12:30"),
        ],
    )
    def test_quiet_hours_surrounding_whitespace_sanitized(self, raw_input: str, expected_output: str):
        q = QuietHoursConfig(start=raw_input, end=raw_input)
        assert q.start == expected_output
        assert q.end == expected_output
        t = datetime.strptime(q.start, "%H:%M")
        assert t.strftime("%H:%M") == expected_output

    def test_quiet_hours_validate_assignment(self):
        """Verify validate_assignment enforces time format on post-init attribute assignment."""
        q = QuietHoursConfig(start="10:00", end="18:00")
        with pytest.raises(ValidationError):
            q.start = "99:99"
        with pytest.raises(ValidationError):
            q.end = "invalid"
        q.start = " 11:00\n "
        assert q.start == "11:00"

    @pytest.mark.parametrize(
        "invalid_action",
        [
            "HOLD",
            "DROP",
            "Hold",
            "Drop",
            "discard",
            "ignore",
            "suppress",
            "queue",
            "",
            "hold ",
            " drop",
        ],
    )
    def test_invalid_action_raises(self, invalid_action: str):
        with pytest.raises(ValidationError):
            QuietHoursConfig(action=invalid_action)  # type: ignore[arg-type]

    def test_same_start_and_end_allowed_at_schema_level(self):
        """Schema allows start == end ('00:00'); runtime evaluation handles duration."""
        q = QuietHoursConfig(start="00:00", end="00:00")
        assert q.start == "00:00"
        assert q.end == "00:00"


# ===========================================================================
# 3. Boundary Rate Limits (AlertsConfig)
# ===========================================================================

class TestRateLimitsAdversarial:
    """Stress test max_rate_per_second boundaries and special floats."""

    @pytest.mark.parametrize(
        "valid_rate",
        [
            0.0001,
            0.01,
            0.5,
            1.0,
            15.0,
            30.0,
            100.0,
            1000.0,
        ],
    )
    def test_valid_rate_limits(self, valid_rate: float):
        cfg = AlertsConfig(max_rate_per_second=valid_rate)
        assert cfg.max_rate_per_second == valid_rate

    @pytest.mark.parametrize(
        "invalid_rate",
        [
            0.0,
            -0.0,
            -0.00001,
            -1.0,
            -30.0,
            -1000.0,
            1000.001,
            1e6,
            float("-inf"),
            float("inf"),
            float("nan"),
        ],
    )
    def test_invalid_rate_limits_raise(self, invalid_rate: float):
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=invalid_rate)

    def test_inf_rate_limit(self):
        """Verify IEEE 754 infinity and non-finite floats are rejected."""
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=float("inf"))
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=float("-inf"))
        with pytest.raises(ValidationError):
            AlertsConfig(max_rate_per_second=float("nan"))

    @pytest.mark.parametrize("invalid_routing", ["matrix", "signal", "sms", "email", "", "BOTH", "Discord"])
    def test_invalid_routing_raises(self, invalid_routing: str):
        with pytest.raises(ValidationError):
            AlertsConfig(routing=invalid_routing)  # type: ignore[arg-type]


# ===========================================================================
# 4. Environment Variable Permutations & Precedence
# ===========================================================================

class TestEnvVarsAdversarial:
    """Stress test environment variable parsing, case variations, and precedence."""

    def test_nested_env_var_overrides_legacy_flat_env_var(self, monkeypatch):
        """When both nested and legacy flat env vars exist, nested MUST take precedence."""
        get_settings.cache_clear()
        # Legacy flat env vars specify 21:00 to 06:00
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_START", "21:00")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS_END", "06:00")
        # Nested env vars specify 23:30 to 07:30
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__START", "23:30")
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__END", "07:30")

        s = Settings()
        assert s.alerts.quiet_hours.start == "23:30"
        assert s.alerts.quiet_hours.end == "07:30"
        # Backward compatibility properties match nested value
        assert s.alerts.quiet_hours_start == "23:30"
        assert s.alerts.quiet_hours_end == "07:30"
        get_settings.cache_clear()

    def test_case_insensitive_env_vars(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("argus__alerts__routing", "telegram")
        monkeypatch.setenv("argus__alerts__max_rate_per_second", "12.5")
        monkeypatch.setenv("argus__alerts__discord__enabled", "true")
        s = Settings()
        assert s.alerts.routing == "telegram"
        assert s.alerts.max_rate_per_second == 12.5
        assert s.alerts.discord.enabled is True
        get_settings.cache_clear()

    def test_invalid_env_vars_raise_validation_error(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__MAX_RATE_PER_SECOND", "-5.0")
        with pytest.raises(ValidationError):
            Settings()

        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__MAX_RATE_PER_SECOND", "0.0")
        with pytest.raises(ValidationError):
            Settings()

        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__START", "25:00")
        with pytest.raises(ValidationError):
            Settings()

        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__ALERTS__QUIET_HOURS__ACTION", "invalid_action")
        with pytest.raises(ValidationError):
            Settings()

        get_settings.cache_clear()
        monkeypatch.setenv("ARGUS__RECOGNITION__AUTO_LEARN__PROMPT_VIA", "slack")
        with pytest.raises(ValidationError):
            Settings()
        get_settings.cache_clear()


# ===========================================================================
# 5. Fuzzing & Exception Safety Harness
# ===========================================================================

class TestFuzzingAndExceptionSafety:
    """Randomized fuzzing harness verifying that malformed inputs raise ValidationError, never crash."""

    def test_fuzz_quiet_hours_times(self):
        """Generate 200 random strings of varied lengths and characters."""
        random.seed(42)
        charset = string.ascii_letters + string.digits + string.punctuation + " \t\n\r"

        for _ in range(200):
            # random string of length 0 to 15
            length = random.randint(0, 15)
            fuzz_str = "".join(random.choice(charset) for _ in range(length))

            # If it happens to match 24h format, it may pass; otherwise it must raise ValidationError
            try:
                QuietHoursConfig(start=fuzz_str)
                assert len(fuzz_str) in (5, 6)  # 5 or 6 (if trailing \n)
            except ValidationError:
                pass  # expected
            except Exception as exc:
                pytest.fail(f"Unhandled exception on fuzz input {fuzz_str!r}: {type(exc).__name__}: {exc}")

    def test_fuzz_discord_ids(self):
        """Verify arbitrary fuzz values never crash channel_id_int or guild_id_int."""
        random.seed(1337)
        charset = string.ascii_letters + string.digits + string.punctuation + " \t\n"

        for _ in range(200):
            length = random.randint(0, 30)
            fuzz_str = "".join(random.choice(charset) for _ in range(length))

            try:
                cfg = DiscordConfig(channel_id=fuzz_str, guild_id=fuzz_str)
                val_c = cfg.channel_id_int
                val_g = cfg.guild_id_int
                assert isinstance(val_c, int)
                assert isinstance(val_g, int)
            except ValidationError:
                pass
            except Exception as exc:
                pytest.fail(f"Unhandled exception on Discord ID fuzz {fuzz_str!r}: {type(exc).__name__}: {exc}")

    def test_fuzz_rate_limits(self):
        """Random numerical rates: negative, zero, positive within bounds, and overflowing."""
        random.seed(999)
        test_values = [
            random.uniform(-1000.0, 0.0) for _ in range(50)
        ] + [
            random.uniform(0.0001, 1000.0) for _ in range(50)
        ] + [
            random.uniform(1000.001, 10000.0) for _ in range(25)
        ] + [0.0, -0.0]

        for rate in test_values:
            if rate <= 0.0 or rate > 1000.0:
                with pytest.raises(ValidationError):
                    AlertsConfig(max_rate_per_second=rate)
            else:
                cfg = AlertsConfig(max_rate_per_second=rate)
                assert cfg.max_rate_per_second == rate
