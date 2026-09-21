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
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
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
    prompt_via: Literal["telegram"] = "telegram"


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


class LLMConfig(BaseModel):
    """LLM provider settings — swap providers without touching code."""

    provider: Literal["ollama", "openai", "anthropic", "gemini", "disabled"] = "ollama"
    ollama: OllamaConfig = OllamaConfig()
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


class AlertsConfig(BaseModel):
    """Alert routing and throttling settings."""

    cooldown_seconds: Annotated[int, Field(ge=0, le=3600)] = 60
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "07:00"
    # Even in quiet hours, alert immediately if LLM says suspicious
    override_on_suspicious: bool = True
    telegram: TelegramConfig = TelegramConfig()
    email: EmailConfig = EmailConfig()
    webhook: WebhookConfig = WebhookConfig()
    ntfy: NtfyConfig = NtfyConfig()


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


# ---------------------------------------------------------------------------
# Root Settings
# ---------------------------------------------------------------------------


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

    @model_validator(mode="before")
    @classmethod
    def load_yaml_config(cls, values: Any) -> Any:
        """Merge config.yaml into settings before validation."""
        config_path = Path("config/config.yaml")
        if config_path.exists():
            with config_path.open() as f:
                yaml_data = yaml.safe_load(f) or {}
            # YAML values are defaults — env vars / .env override them
            for key, val in yaml_data.items():
                if key not in values:
                    values[key] = val
        return values

    @model_validator(mode="after")
    def ensure_data_dirs_exist(self) -> "Settings":
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
    def validate_llm_credentials(self) -> "Settings":
        """Ensure API keys are present for non-Ollama providers."""
        p = self.llm.provider
        if p == "openai" and not self.llm.openai.api_key:
            raise ValueError("LLM provider is 'openai' but ARGUS__LLM__OPENAI__API_KEY is not set.")
        if p == "anthropic" and not self.llm.anthropic.api_key:
            raise ValueError("LLM provider is 'anthropic' but ARGUS__LLM__ANTHROPIC__API_KEY is not set.")
        if p == "gemini" and not self.llm.gemini.api_key:
            raise ValueError("LLM provider is 'gemini' but ARGUS__LLM__GEMINI__API_KEY is not set.")
        return self

    @model_validator(mode="after")
    def validate_active_cameras(self) -> "Settings":
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
