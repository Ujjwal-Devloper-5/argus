"""
Argus Dashboard Schemas Package
"""
from argus.dashboard.backend.schemas.settings import (
    CameraUpdateRequest,
    DetectionUpdateRequest,
    LayaUpdateRequest,
    LLMUpdateRequest,
    QuietHoursUpdateRequest,
    AlertsUpdateRequest,
    StorageUpdateRequest,
    FullSettingsUpdateRequest,
)

__all__ = [
    "CameraUpdateRequest",
    "DetectionUpdateRequest",
    "LayaUpdateRequest",
    "LLMUpdateRequest",
    "QuietHoursUpdateRequest",
    "AlertsUpdateRequest",
    "StorageUpdateRequest",
    "FullSettingsUpdateRequest",
]
