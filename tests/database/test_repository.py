"""Tests for database models and repository functions."""

from __future__ import annotations

import pytest

from argus.database.models import Camera, FaceProfile
from argus.database.repository import (
    create_clip,
    create_event,
    create_face_profile,
    delete_face_profile,
    get_all_face_profiles,
    get_camera_by_name,
    get_or_create_camera,
    get_or_create_unknown_tracker,
    list_cameras,
    list_events,
    update_event_with_analysis,
    update_face_last_seen,
)


class TestCameraRepository:
    async def test_create_camera(self, db_session):
        cam = await get_or_create_camera(db_session, "front_door", "rtsp://test")
        assert cam.id is not None
        assert cam.name == "front_door"
        assert cam.is_active is True

    async def test_get_or_create_is_idempotent(self, db_session):
        cam1 = await get_or_create_camera(db_session, "cam1", "rtsp://test1")
        cam2 = await get_or_create_camera(db_session, "cam1", "rtsp://test2")
        assert cam1.id == cam2.id  # Same record returned

    async def test_list_cameras(self, db_session):
        await get_or_create_camera(db_session, "cam_a", "rtsp://a")
        await get_or_create_camera(db_session, "cam_b", "rtsp://b")
        cameras = await list_cameras(db_session)
        assert len(cameras) == 2

    async def test_get_camera_by_name_not_found(self, db_session):
        result = await get_camera_by_name(db_session, "nonexistent")
        assert result is None


class TestFaceProfileRepository:
    MOCK_EMBEDDINGS = [[0.1, 0.2, 0.3, 0.4]]  # Simplified 4-dim for testing

    async def test_create_face_profile(self, db_session):
        profile = await create_face_profile(db_session, "Alice", self.MOCK_EMBEDDINGS)
        assert profile.id is not None
        assert profile.name == "Alice"
        assert profile.is_trusted is True

    async def test_embeddings_serialize_roundtrip(self, db_session):
        import math
        original = [[0.1, 0.2, 0.3, 0.4, 0.5]]
        profile = await create_face_profile(db_session, "Bob", original)
        loaded = profile.get_embeddings()
        assert len(loaded) == 1
        assert len(loaded[0]) == len(original[0])
        for a, b in zip(loaded[0], original[0]):
            assert math.isclose(a, b, rel_tol=1e-5)

    async def test_get_all_face_profiles(self, db_session):
        await create_face_profile(db_session, "Alice", self.MOCK_EMBEDDINGS)
        await create_face_profile(db_session, "Bob", self.MOCK_EMBEDDINGS)
        profiles = await get_all_face_profiles(db_session)
        assert len(profiles) == 2

    async def test_delete_face_profile(self, db_session):
        profile = await create_face_profile(db_session, "Charlie", self.MOCK_EMBEDDINGS)
        deleted = await delete_face_profile(db_session, profile.id)
        assert deleted is True

    async def test_delete_nonexistent_profile(self, db_session):
        deleted = await delete_face_profile(db_session, 9999)
        assert deleted is False

    async def test_update_last_seen(self, db_session):
        profile = await create_face_profile(db_session, "Dave", self.MOCK_EMBEDDINGS)
        assert profile.last_seen_at is None
        await update_face_last_seen(db_session, profile.id)
        # Flush and reload
        await db_session.refresh(profile)
        assert profile.last_seen_at is not None


class TestEventRepository:
    async def test_create_event(self, db_session, camera):
        event = await create_event(db_session, camera_id=camera.id)
        assert event.id is not None
        assert event.camera_id == camera.id
        assert event.is_suspicious is False
        assert event.alert_sent is False

    async def test_update_event_with_analysis(self, db_session, camera):
        event = await create_event(db_session, camera_id=camera.id)
        await update_event_with_analysis(
            db_session,
            event_id=event.id,
            llm_analysis="Person is loitering near the door.",
            is_suspicious=True,
            alert_sent=True,
        )
        await db_session.refresh(event)
        assert event.is_suspicious is True
        assert event.alert_sent is True
        assert "loitering" in event.llm_analysis

    async def test_list_events_newest_first(self, db_session, camera):
        for _ in range(3):
            await create_event(db_session, camera_id=camera.id)
        events = await list_events(db_session)
        assert len(events) == 3
        # Should be ordered newest first
        for i in range(len(events) - 1):
            assert events[i].triggered_at >= events[i + 1].triggered_at


class TestClipRepository:
    async def test_create_clip(self, db_session, camera):
        event = await create_event(db_session, camera_id=camera.id)
        clip = await create_clip(
            db_session,
            event_id=event.id,
            local_path="/data/clips/test.mp4",
            duration_seconds=35.5,
            file_size_bytes=10_000_000,
        )
        assert clip.id is not None
        assert clip.remote_url is None
        assert clip.duration_seconds == 35.5


class TestUnknownFaceTracker:
    async def test_create_tracker(self, db_session):
        tracker = await get_or_create_unknown_tracker(db_session, face_hash="abc123")
        assert tracker.id is not None
        assert tracker.appearance_count == 1
        assert tracker.prompted_user is False

    async def test_increment_appearance_count(self, db_session):
        await get_or_create_unknown_tracker(db_session, face_hash="xyz789")
        tracker = await get_or_create_unknown_tracker(db_session, face_hash="xyz789")
        assert tracker.appearance_count == 2

    async def test_idempotent_hash(self, db_session):
        t1 = await get_or_create_unknown_tracker(db_session, face_hash="same_hash")
        t2 = await get_or_create_unknown_tracker(db_session, face_hash="same_hash")
        assert t1.id == t2.id
