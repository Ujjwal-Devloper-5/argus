"""Tests for Argus Settings (argus/config/settings.py)."""

from __future__ import annotations

import pytest

from argus.config.settings import (
    CameraConfig,
    DetectionConfig,
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
