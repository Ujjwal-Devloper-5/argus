"""
Argus Settings — Single source of truth for all configuration.

Load order (later overrides earlier):
  1. Default values defined here
  2. config/config.yaml
  3. .env file
  4. Environment variables (ARGUS__ prefix for nested)

Usage:
    from argus.config import get_settings
    settings = get_settings()
    print(settings.llm.provider)
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Sub-models — each section of the config has its own typed model
# ---------------------------------------------------------------------------


class CameraConfig(BaseModel):
    """Configuration for a single RTSP camera."""

    name: str = Field(..., description="Unique camera identifier (used in filenames and logs)")
    rtsp_url: str = Field(..., description="Main stream RTSP URL (1080p)")
    rtsp_sub_url: str | None = Field(None, description="Sub stream URL (lower resolution, optional)")
    fps: Annotated[int, Field(ge=1, le=60)] = 15
    pre_buffer_seconds: Annotated[int, Field(ge=1, le=60)] = 5
    post_event_seconds: Annotated[int, Field(ge=5, le=300)] = 30
    motion_threshold: Annotated[float, Field(ge=0.001, le=1.0)] = 0.005
    disabled: bool = False

    @field_validator("name")
    @classmethod
    def name_must_be_slug(cls, v: str) -> str:
        """Camera name is used in file paths — only allow safe chars."""
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Camera name must contain only letters, digits, hyphens, underscores.")
        return v.lower()


class DetectionConfig(BaseModel):
    """YOLOv8 detection settings."""

    model: str = "yolov8n.pt"
    confidence: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    # COCO class IDs to detect. 0 = person. Add more as needed.
    classes: list[int] = [0]
    device: Literal["auto", "cuda", "cpu", "mps"] = "auto"


class AutoLearnConfig(BaseModel):
    """Settings for the auto-learning unknown face tracker."""

    enabled: bool = True
    appearances_before_prompt: Annotated[int, Field(ge=2, le=100)] = 5
    prompt_via: Literal["telegram", "discord", "both"] = "telegram"


class RecognitionConfig(BaseModel):
    """InsightFace recognition settings."""

    similarity_threshold: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    auto_learn: AutoLearnConfig = AutoLearnConfig()


# --- LLM Provider sub-configs ---

class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "llava"
    timeout_seconds: int = 30


class OpenAIConfig(BaseModel):
    api_key: SecretStr | None = None
    model: str = "gpt-4o"
    timeout_seconds: int = 30


class AnthropicConfig(BaseModel):
    api_key: SecretStr | None = None
    model: str = "claude-3-5-sonnet-20241022"
    timeout_seconds: int = 30


class GeminiConfig(BaseModel):
    api_key: SecretStr | None = None
    model: str = "gemini-1.5-pro"
    timeout_seconds: int = 30


class LayaConfig(BaseModel):
    """Laya 421M decision model config — the fast System 1 gate before full LLM analysis."""

    enabled: bool = True
    model_id: str = "convaiinnovations/laya-typed-decisions"  # HuggingFace model ID, fully configurable
    suspicion_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.60
    urgency_threshold: Annotated[float, Field(ge=0.0, le=10.0)] = 6.0


class LLMConfig(BaseModel):
    """LLM provider settings — swap providers without touching code."""

    provider: Literal["ollama", "openai", "anthropic", "gemini", "disabled"] = "ollama"
    ollama: OllamaConfig = OllamaConfig()
    laya: LayaConfig = LayaConfig()
    openai: OpenAIConfig = OpenAIConfig()
    anthropic: AnthropicConfig = AnthropicConfig()
    gemini: GeminiConfig = GeminiConfig()
    # If True: only alert when LLM explicitly flags behaviour as suspicious
    filter_by_suspicion: bool = False
    scene_prompt: str = (
        "Describe what this person is doing in one concise sentence. "
        "Are they behaving suspiciously? Respond ONLY with valid JSON matching this schema: "
        '{"description": "...", "is_suspicious": true/false, '
        '"confidence": 0.0-1.0, "action_recommendation": "..."}'
    )


# --- Alert channel sub-configs ---

class DiscordConfig(BaseModel):
    """Discord bot alert channel settings."""

    enabled: bool = False
    bot_token: str = ""
    channel_id: int | str | None = 0
    guild_id: int | str | None = 0

    @field_validator("bot_token", mode="before")
    @classmethod
    def _coerce_token(cls, v: Any) -> str:
        """Coerce SecretStr or None to plain string."""
        if isinstance(v, SecretStr):
            return v.get_secret_value()
        if v is None:
            return ""
        return str(v)

    @property
    def channel_id_int(self) -> int:
        """Helper returning channel_id as int (0 if unset/invalid)."""
        if not self.channel_id:
            return 0
        try:
            return int(self.channel_id)
        except (ValueError, TypeError):
            return 0

    @property
    def guild_id_int(self) -> int:
        """Helper returning guild_id as int (0 if unset/invalid)."""
        if not self.guild_id:
            return 0
        try:
            return int(self.guild_id)
        except (ValueError, TypeError):
            return 0


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: SecretStr | None = None
    chat_id: str | None = None


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    from_addr: str = ""
    to_addr: str = ""
    password: SecretStr | None = None


class WebhookConfig(BaseModel):
    enabled: bool = False
    url: str | None = None
    secret_header: SecretStr | None = None


class NtfyConfig(BaseModel):
    enabled: bool = False
    topic: str = "argus-alerts"
    server: str = "https://ntfy.sh"
    token: SecretStr | None = None


class QuietHoursConfig(BaseModel):
    """Quiet hours suppression window and policy."""

    model_config = ConfigDict(validate_assignment=True)

    enabled: bool = False
    start: str = "23:00"
    end: str = "07:00"
    override_on_suspicious: bool = True
    action: Literal["hold", "drop"] = "hold"

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM 24-hour time format."""
        import re

        v = v.strip()
        if not re.match(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z", v):
            raise ValueError(f"Quiet hours time must be in HH:MM format (e.g. '23:00'), got '{v}'")
        return v


class AlertsConfig(BaseModel):
    """Alert routing and throttling settings."""

    cooldown_seconds: Annotated[int, Field(ge=0, le=3600)] = 60
    routing: Literal["telegram", "discord", "both"] = "both"
    max_rate_per_second: Annotated[float, Field(gt=0.0, le=1000.0, allow_inf_nan=False)] = 30.0
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_quiet_hours(cls, values: Any) -> Any:
        """Migrate legacy flat quiet hours fields into nested QuietHoursConfig."""
        if isinstance(values, dict):
            qh_data = values.get("quiet_hours")
            if isinstance(qh_data, QuietHoursConfig):
                qh_dict = qh_data.model_dump()
                explicit_fields = qh_data.model_fields_set
            elif isinstance(qh_data, dict):
                qh_dict = dict(qh_data)
                explicit_fields = set(qh_data.keys())
            else:
                qh_dict = {}
                explicit_fields = set()

            for old_key, new_key in [
                ("quiet_hours_enabled", "enabled"),
                ("quiet_hours_start", "start"),
                ("quiet_hours_end", "end"),
                ("override_on_suspicious", "override_on_suspicious"),
            ]:
                if old_key in values:
                    val = values.pop(old_key)
                    if new_key not in explicit_fields:
                        qh_dict[new_key] = val

            if qh_dict:
                values["quiet_hours"] = qh_dict
        return values

    # -----------------------------------------------------------------------
    # Backward compatibility properties (read & write)
    # -----------------------------------------------------------------------

    @property
    def quiet_hours_enabled(self) -> bool:
        return self.quiet_hours.enabled

    @quiet_hours_enabled.setter
    def quiet_hours_enabled(self, val: bool) -> None:
        self.quiet_hours.enabled = val

    @property
    def quiet_hours_start(self) -> str:
        return self.quiet_hours.start

    @quiet_hours_start.setter
    def quiet_hours_start(self, val: str) -> None:
        self.quiet_hours.start = val

    @property
    def quiet_hours_end(self) -> str:
        return self.quiet_hours.end

    @quiet_hours_end.setter
    def quiet_hours_end(self, val: str) -> None:
        self.quiet_hours.end = val

    @property
    def override_on_suspicious(self) -> bool:
        return self.quiet_hours.override_on_suspicious

    @override_on_suspicious.setter
    def override_on_suspicious(self, val: bool) -> None:
        self.quiet_hours.override_on_suspicious = val


class StorageConfig(BaseModel):
    """Where and how to store incident clips."""

    backend: Literal["local", "rclone"] = "local"
    local_path: str = "./data/clips"
    retention_days: Annotated[int, Field(ge=0)] = 30
    # rclone backend settings (only used when backend="rclone")
    rclone_remote: str | None = None
    rclone_path: str | None = None


class DashboardConfig(BaseModel):
    """Streamlit dashboard settings."""

    port: Annotated[int, Field(ge=1024, le=65535)] = 8501
    host: str = "0.0.0.0"
    username: str = "admin"
    password: SecretStr = SecretStr("changeme")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override dictionary into base dictionary.

    Keys in base are preserved unless present in override. Nested dictionaries
    are merged recursively; non-dict values in override replace base values.
    """
    res = dict(base)
    for k, v in override.items():
        if k in res and isinstance(res[k], dict) and isinstance(v, dict):
            res[k] = _deep_merge(res[k], v)
        else:
            res[k] = v
    return res


# ---------------------------------------------------------------------------
# Root Settings
# ---------------------------------------------------------------------------


class KafkaTopicsConfig(BaseModel):
    """Topic name overrides — defaults match ArgusTopics enum values."""
    uploads: str = "argus.uploads"
    frames: str = "argus.frames"
    events: str = "argus.events"
    learn: str = "argus.learn"
    dlq: str = "argus.dlq"


class KafkaProducerConfig(BaseModel):
    """Producer tuning — idempotent by default for exactly-once semantics."""
    enable_idempotence: bool = True
    acks: str = "all"  # Wait for all ISR replicas
    compression_type: str = "lz4"
    linger_ms: int = 5


class KafkaConsumerConfig(BaseModel):
    """Consumer tuning — manual commit enforced by ArgusConsumer."""
    auto_offset_reset: str = "earliest"
    max_poll_records: int = 10
    session_timeout_ms: int = 30_000
    heartbeat_interval_ms: int = 10_000


class KafkaConfig(BaseModel):
    """Apache Kafka connection and topic configuration."""
    enabled: bool = True
    bootstrap_servers: str = "localhost:9092"
    topics: KafkaTopicsConfig = Field(default_factory=KafkaTopicsConfig)
    producer: KafkaProducerConfig = Field(default_factory=KafkaProducerConfig)
    consumer: KafkaConsumerConfig = Field(default_factory=KafkaConsumerConfig)


class Settings(BaseSettings):
    """
    Root settings model. Reads from .env, environment variables, and config.yaml.

    Nested values can be set via env vars using double underscores:
      ARGUS__LLM__PROVIDER=openai
      ARGUS__ALERTS__TELEGRAM__ENABLED=true
    """

    model_config = SettingsConfigDict(
        env_prefix="ARGUS__",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Top-level ---
    app_name: str = "Argus"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["pretty", "json"] = "pretty"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/argus.db"

    # --- Thumbnail path ---
    thumbnails_path: str = "./data/events"
    embeddings_path: str = "./data/embeddings"
    recordings_path: str = "argus/data/recordings"

    # --- Sub-configs ---
    cameras: list[CameraConfig] = []
    detection: DetectionConfig = DetectionConfig()
    recognition: RecognitionConfig = RecognitionConfig()
    llm: LLMConfig = LLMConfig()
    alerts: AlertsConfig = AlertsConfig()
    storage: StorageConfig = StorageConfig()
    dashboard: DashboardConfig = DashboardConfig()
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)

    @model_validator(mode="before")
    @classmethod
    def load_yaml_config(cls, values: Any) -> Any:
        """Merge config.yaml into settings before validation."""
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with config_path.open() as f:
                yaml_data = yaml.safe_load(f) or {}
            # YAML values are defaults — env vars / .env override them (via recursive deep merge)
            if isinstance(yaml_data, dict) and isinstance(values, dict):
                return _deep_merge(yaml_data, values)
            if isinstance(yaml_data, dict) and not values:
                return yaml_data
        return values

    @model_validator(mode="after")
    def ensure_data_dirs_exist(self) -> Settings:
        """Create required runtime directories if they don't exist."""
        for path_str in [
            self.storage.local_path,
            self.thumbnails_path,
            self.embeddings_path,
            self.recordings_path,
            "./data",
        ]:
            Path(path_str).mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def validate_llm_credentials(self) -> Settings:
        """Ensure API keys are present for cloud providers.

        Note: ollama is a local provider — no API key required.
        laya is a decision gate (not an LLM provider) configured separately via llm.laya.
        """
        p = self.llm.provider
        if p == "openai" and not self.llm.openai.api_key:
            raise ValueError("LLM provider is 'openai' but ARGUS__LLM__OPENAI__API_KEY is not set.")
        if p == "anthropic" and not self.llm.anthropic.api_key:
            raise ValueError("LLM provider is 'anthropic' but ARGUS__LLM__ANTHROPIC__API_KEY is not set.")
        if p == "gemini" and not self.llm.gemini.api_key:
            raise ValueError("LLM provider is 'gemini' but ARGUS__LLM__GEMINI__API_KEY is not set.")
        return self

    @model_validator(mode="after")
    def validate_active_cameras(self) -> Settings:
        """Warn (not error) if no cameras are configured."""
        active = [c for c in self.cameras if not c.disabled]
        if not active:
            import warnings
            warnings.warn(
                "No active cameras configured. Add cameras to config/config.yaml.",
                stacklevel=2,
            )
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.
    Call `get_settings.cache_clear()` in tests to reset.
    """
    return Settings()
