from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, Field, field_validator


class CameraUpdateRequest(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    rtsp_url: str = Field(..., min_length=5)
    rtsp_sub_url: str | None = None
    fps: Annotated[int, Field(ge=1, le=60)] = 15
    pre_buffer_seconds: Annotated[int, Field(ge=1, le=30)] = 5
    post_event_seconds: Annotated[int, Field(ge=5, le=300)] = 30
    motion_threshold: Annotated[float, Field(ge=0.001, le=1.0)] = 0.005
    disabled: bool = False


class DetectionUpdateRequest(BaseModel):
    model: str = Field(default="yolov8n.pt")
    confidence: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    classes: list[str] = Field(default=["person"])
    device: Literal["auto", "cuda", "cpu", "mps"] = "auto"

    @field_validator("classes")
    @classmethod
    def validate_classes(cls, classes: list[str]) -> list[str]:
        valid = {
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
            "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
            "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
            "backpack", "umbrella", "handbag", "tie", "suitcase"
        }
        for c in classes:
            if c.lower() not in valid:
                raise ValueError(f"Unsupported class: {c}")
        return [c.lower() for c in classes]


class LayaUpdateRequest(BaseModel):
    enabled: bool = True
    model_id: str = "convaiinnovations/laya-typed-decisions"
    suspicion_threshold: Annotated[float, Field(ge=0.1, le=1.0)] = 0.60
    urgency_threshold: Annotated[float, Field(ge=1.0, le=10.0)] = 6.0


class LLMUpdateRequest(BaseModel):
    provider: Literal["ollama", "openai", "anthropic", "gemini", "disabled"] = "ollama"
    model: str = "llava"
    ollama_host: str = "http://localhost:11434"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    timeout_seconds: Annotated[int, Field(ge=5, le=120)] = 30
    filter_by_suspicion: bool = False
    scene_prompt: str = Field(default="Describe what is occurring in the scene in detail.", min_length=5)
    laya: LayaUpdateRequest = Field(default_factory=LayaUpdateRequest)


class QuietHoursUpdateRequest(BaseModel):
    enabled: bool = False
    start: str = Field(default="23:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    override_on_suspicious: bool = True
    action: Literal["hold", "drop"] = "hold"


class AlertsUpdateRequest(BaseModel):
    routing: Literal["telegram", "discord", "both"] = "both"
    cooldown_seconds: Annotated[int, Field(ge=0, le=3600)] = 60
    max_rate_per_second: Annotated[float, Field(gt=0.0, le=100.0)] = 30.0
    quiet_hours: QuietHoursUpdateRequest = Field(default_factory=QuietHoursUpdateRequest)
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_enabled: bool = False
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None
    discord_guild_id: str | None = None


class StorageUpdateRequest(BaseModel):
    backend: Literal["local", "rclone"] = "local"
    local_path: str = "./data/clips"
    recordings_path: str = "argus/data/recordings"
    retention_days: Annotated[int, Field(ge=0, le=365)] = 30
    rclone_remote: str | None = None
    rclone_path: str | None = None


class FullSettingsUpdateRequest(BaseModel):
    cameras: list[CameraUpdateRequest] = Field(default_factory=list)
    detection: DetectionUpdateRequest = Field(default_factory=DetectionUpdateRequest)
    llm: LLMUpdateRequest = Field(default_factory=LLMUpdateRequest)
    alerts: AlertsUpdateRequest = Field(default_factory=AlertsUpdateRequest)
    storage: StorageUpdateRequest = Field(default_factory=StorageUpdateRequest)
