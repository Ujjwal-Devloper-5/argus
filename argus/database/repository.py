"""
Argus Repository — All database access goes through here.

Rules:
- NO raw SQL anywhere in business logic — use these functions only.
- All functions are async.
- All functions accept an `AsyncSession` parameter (dependency-injected).
- Functions return ORM model instances or None. Never raise on not-found.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from argus.database.models import (
    Camera,
    Clip,
    Event,
    FaceProfile,
    UnknownFaceTracker,
)

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


async def get_or_create_camera(session: AsyncSession, name: str, rtsp_url: str) -> Camera:
    """Get an existing camera by name, or create it if it doesn't exist."""
    stmt = select(Camera).where(Camera.name == name)
    result = await session.execute(stmt)
    camera = result.scalar_one_or_none()

    if camera is None:
        camera = Camera(name=name, rtsp_url=rtsp_url)
        session.add(camera)
        await session.flush()  # Get ID without committing
        logger.info("Camera created", name=name)

    return camera


async def get_camera_by_name(session: AsyncSession, name: str) -> Camera | None:
    """Fetch a camera by its unique name."""
    result = await session.execute(select(Camera).where(Camera.name == name))
    return result.scalar_one_or_none()


async def list_cameras(session: AsyncSession, active_only: bool = True) -> list[Camera]:
    """List all cameras, optionally filtering to active only."""
    stmt = select(Camera)
    if active_only:
        stmt = stmt.where(Camera.is_active == True)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# FaceProfile
# ---------------------------------------------------------------------------


async def create_face_profile(
    session: AsyncSession,
    name: str,
    embeddings: list,
    is_trusted: bool = True,
) -> FaceProfile:
    """Enroll a new known person."""
    profile = FaceProfile(
        name=name,
        embeddings_json=FaceProfile.serialize_embeddings(embeddings),
        is_trusted=is_trusted,
    )
    session.add(profile)
    await session.flush()
    logger.info("Face profile created", name=name, id=profile.id)
    return profile


async def get_all_face_profiles(session: AsyncSession) -> list[FaceProfile]:
    """Fetch all enrolled face profiles (for loading into FAISS index on startup)."""
    result = await session.execute(select(FaceProfile))
    return list(result.scalars().all())


async def get_face_profile(session: AsyncSession, profile_id: int) -> FaceProfile | None:
    """Fetch a face profile by ID."""
    result = await session.execute(select(FaceProfile).where(FaceProfile.id == profile_id))
    return result.scalar_one_or_none()


async def update_face_last_seen(session: AsyncSession, profile_id: int) -> None:
    """Update the last_seen_at timestamp for a recognized face."""
    await session.execute(
        update(FaceProfile)
        .where(FaceProfile.id == profile_id)
        .values(last_seen_at=datetime.now(timezone.utc))
    )


async def delete_face_profile(session: AsyncSession, profile_id: int) -> bool:
    """Delete a face profile by ID. Returns True if deleted, False if not found."""
    profile = await get_face_profile(session, profile_id)
    if profile is None:
        return False
    await session.delete(profile)
    logger.info("Face profile deleted", id=profile_id)
    return True


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


async def create_event(
    session: AsyncSession,
    camera_id: int,
    face_profile_id: int | None = None,
    thumbnail_path: str | None = None,
    similarity_score: float | None = None,
) -> Event:
    """Create a new security event record."""
    event = Event(
        camera_id=camera_id,
        face_profile_id=face_profile_id,
        thumbnail_path=thumbnail_path,
        similarity_score=similarity_score,
    )
    session.add(event)
    await session.flush()
    logger.info("Event created", event_id=event.id, camera_id=camera_id)
    return event


async def update_event_with_analysis(
    session: AsyncSession,
    event_id: int,
    llm_analysis: str,
    is_suspicious: bool,
    alert_sent: bool,
) -> None:
    """Patch an event with LLM analysis results and alert status."""
    await session.execute(
        update(Event)
        .where(Event.id == event_id)
        .values(
            llm_analysis=llm_analysis,
            is_suspicious=is_suspicious,
            alert_sent=alert_sent,
        )
    )


async def list_events(
    session: AsyncSession,
    camera_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Event]:
    """List recent events, newest first."""
    stmt = select(Event).order_by(Event.triggered_at.desc()).limit(limit).offset(offset)
    if camera_id is not None:
        stmt = stmt.where(Event.camera_id == camera_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


async def create_clip(
    session: AsyncSession,
    event_id: int,
    local_path: str,
    duration_seconds: float = 0.0,
    file_size_bytes: int = 0,
) -> Clip:
    """Record a new video clip linked to an event."""
    clip = Clip(
        event_id=event_id,
        local_path=local_path,
        duration_seconds=duration_seconds,
        file_size_bytes=file_size_bytes,
    )
    session.add(clip)
    await session.flush()
    return clip


async def update_clip_remote_url(session: AsyncSession, clip_id: int, remote_url: str) -> None:
    """Set the remote URL after successful cloud upload."""
    await session.execute(
        update(Clip).where(Clip.id == clip_id).values(remote_url=remote_url)
    )


# ---------------------------------------------------------------------------
# UnknownFaceTracker (auto-learning)
# ---------------------------------------------------------------------------


async def get_or_create_unknown_tracker(
    session: AsyncSession,
    face_hash: str,
) -> UnknownFaceTracker:
    """
    Fetch an existing tracker for this face hash, or create a new one.
    Called every time an unknown face is seen.
    """
    result = await session.execute(
        select(UnknownFaceTracker).where(UnknownFaceTracker.face_hash == face_hash)
    )
    tracker = result.scalar_one_or_none()

    if tracker is None:
        tracker = UnknownFaceTracker(face_hash=face_hash)
        session.add(tracker)
        await session.flush()
    else:
        tracker.appearance_count += 1
        tracker.last_seen = datetime.now(timezone.utc)

    return tracker


async def mark_tracker_prompted(
    session: AsyncSession,
    tracker_id: int,
    thumbnail_path: str,
) -> None:
    """Mark that the Telegram approval prompt was sent for this unknown face."""
    await session.execute(
        update(UnknownFaceTracker)
        .where(UnknownFaceTracker.id == tracker_id)
        .values(prompted_user=True, sample_thumbnail=thumbnail_path)
    )


async def mark_tracker_ignored(session: AsyncSession, tracker_id: int) -> None:
    """User chose 'Ignore' on the Telegram prompt — suppress future prompts."""
    await session.execute(
        update(UnknownFaceTracker)
        .where(UnknownFaceTracker.id == tracker_id)
        .values(is_ignored=True)
    )
