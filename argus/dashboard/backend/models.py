from datetime import datetime

from pydantic import BaseModel


class EventSummary(BaseModel):
    id: int
    camera_name: str
    severity: str
    is_suspicious: bool
    thumbnail_path: str | None
    created_at: datetime
    llm_description: str | None
    similarity_score: float | None

class EventDetail(EventSummary):
    clip_local_path: str | None
    clip_remote_url: str | None
    camera_id: int

class FaceProfileResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_seen: datetime | None
    total_events: int
    thumbnail_path: str | None

class CameraStatus(BaseModel):
    name: str
    rtsp_url: str
    disabled: bool
    is_online: bool
    total_events: int
    last_event_at: datetime | None

class SystemStats(BaseModel):
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    gpu_vram_percent: float | None
    uptime_seconds: float
    total_events_today: int
    total_alerts_sent: int
    kafka_enabled: bool
    db_path: str

class SystemHealth(BaseModel):
    status: str
    components: dict[str, str]

class SettingsResponse(BaseModel):
    cameras: list[dict]
    detection: dict
    llm: dict
    alerts: dict
    kafka: dict
    storage: dict

class AlertEventWS(BaseModel):
    id: int
    camera_name: str
    severity: str
    is_suspicious: bool
    thumbnail_path: str | None
    created_at: str
    message: str | None
