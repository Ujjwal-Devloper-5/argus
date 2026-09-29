"""
Argus Alert Engine — Core data models.

All alert payloads flowing through the system are typed here.
Designed to be platform-agnostic: the same Alert is dispatched
to Telegram, Discord, or any future channel without modification.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertKind(StrEnum):
    MOTION_DETECTED = "motion_detected"
    PERSON_DETECTED = "person_detected"
    UNKNOWN_FACE = "unknown_face"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    SYSTEM_ERROR = "system_error"
    LEARN_PROMPT = "learn_prompt"  # AutoLearner asks user to identify a face
    HEARTBEAT = "heartbeat"


@dataclass(frozen=True, slots=True)
class InteractiveButton:
    """A single interactive button attached to an alert message."""
    label: str
    callback_data: str  # Opaque payload routed back to the callback handler


@dataclass
class Alert:
    """
    Platform-agnostic alert payload.

    Every field is optional except kind and severity — channels
    render only what is present.
    """
    kind: AlertKind
    severity: AlertSeverity
    title: str
    body: str
    camera_name: str | None = None
    thumbnail: bytes | None = None          # JPEG bytes of the face crop or frame
    video_clip_path: Path | None = None     # Path to a short MP4 clip
    buttons: list[InteractiveButton] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _delivery_attempts: int = field(default=0, repr=False, compare=False)
