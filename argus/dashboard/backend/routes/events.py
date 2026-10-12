"""
Events API — lists and retrieves security events, incident clips, and analytics from the Argus database.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import EventDetail, EventSummary
from argus.database.engine import get_session
from argus.database.models import Camera, Event

settings = get_settings()
router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_auth_dependency())])


class EventStatsResponse(BaseModel):
    total_24h: int
    critical_count: int
    warning_count: int
    info_count: int
    threat_level: str
    severity_distribution: dict[str, int]


def get_severity(event: Event) -> str:
    if event.is_suspicious:
        return "critical"
    if event.similarity_score is not None and event.similarity_score < 0.3:
        return "warning"
    return "info"


@router.get("/stats", response_model=EventStatsResponse)
async def get_event_stats():
    """Returns rolling 24-hour incident statistics for the Overview dashboard."""
    async with get_session() as session:
        stmt = select(Event.is_suspicious, Event.similarity_score)
        result = await session.execute(stmt)
        rows = result.all()

        total = len(rows)
        crit = sum(1 for is_susp, _ in rows if is_susp)
        warn = sum(1 for is_susp, sim in rows if not is_susp and sim is not None and sim < 0.3)
        info = total - crit - warn

        if crit >= 5:
            threat = "CRITICAL"
        elif crit >= 2:
            threat = "HIGH"
        elif crit >= 1 or warn >= 3:
            threat = "ELEVATED"
        else:
            threat = "LOW"

        return EventStatsResponse(
            total_24h=total,
            critical_count=crit,
            warning_count=warn,
            info_count=max(0, info),
            threat_level=threat,
            severity_distribution={
                "critical": crit,
                "warning": warn,
                "info": max(0, info),
            },
        )


@router.get("", response_model=list[EventSummary])
async def list_events(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    camera_name: str | None = None,
    severity: str | None = None,
    suspicious_only: bool = False,
    search: str | None = None,
):
    async with get_session() as session:
        stmt = select(Event).options(selectinload(Event.camera)).order_by(desc(Event.triggered_at))

        if camera_name:
            stmt = stmt.join(Camera).where(Camera.name == camera_name)
        if suspicious_only:
            stmt = stmt.where(Event.is_suspicious)
        if search:
            stmt = stmt.where(Event.llm_analysis.ilike(f"%{search}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await session.scalar(count_stmt)
        response.headers["X-Total-Count"] = str(total or 0)

        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        events = result.scalars().all()

        res = []
        for e in events:
            llm_desc = None
            if e.llm_analysis:
                llm_desc = (e.llm_analysis[:97] + "...") if len(e.llm_analysis) > 100 else e.llm_analysis

            # Ensure thumbnail endpoint URL if thumbnail path is available
            thumb_url = f"/api/events/{e.id}/thumbnail" if e.thumbnail_path else None

            res.append(
                EventSummary(
                    id=e.id,
                    camera_name=e.camera.name if e.camera else "unknown",
                    severity=get_severity(e),
                    is_suspicious=e.is_suspicious,
                    thumbnail_path=thumb_url,
                    created_at=e.triggered_at,
                    llm_description=llm_desc,
                    similarity_score=e.similarity_score,
                )
            )

        if severity:
            res = [r for r in res if r.severity == severity]

        return res


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: int):
    async with get_session() as session:
        stmt = (
            select(Event)
            .options(selectinload(Event.camera), selectinload(Event.clips))
            .where(Event.id == event_id)
        )
        result = await session.execute(stmt)
        e = result.scalar_one_or_none()

        if not e:
            raise HTTPException(status_code=404, detail="Event not found")

        clip_path = None
        clip_url = None
        if e.clips:
            clip = e.clips[0]
            clip_path = clip.local_path
            clip_url = clip.remote_url

        thumb_url = f"/api/events/{e.id}/thumbnail" if e.thumbnail_path else None

        return EventDetail(
            id=e.id,
            camera_name=e.camera.name if e.camera else "unknown",
            severity=get_severity(e),
            is_suspicious=e.is_suspicious,
            thumbnail_path=thumb_url,
            created_at=e.triggered_at,
            llm_description=e.llm_analysis,
            similarity_score=e.similarity_score,
            clip_local_path=clip_path,
            clip_remote_url=clip_url,
            camera_id=e.camera_id,
        )


@router.get("/{event_id}/thumbnail")
async def get_event_thumbnail(event_id: int):
    """Serve the thumbnail frame for an incident."""
    async with get_session() as session:
        stmt = select(Event.thumbnail_path).where(Event.id == event_id)
        path = await session.scalar(stmt)
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return FileResponse(path, media_type="image/jpeg")


@router.get("/{event_id}/clip")
async def get_event_clip(event_id: int):
    """Stream the recorded MP4 video clip for an incident."""
    async with get_session() as session:
        stmt = select(Event).options(selectinload(Event.clips)).where(Event.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event or not event.clips:
            raise HTTPException(status_code=404, detail="No recorded clip for this event")
        clip_path = event.clips[0].local_path
        if not clip_path or not os.path.exists(clip_path):
            raise HTTPException(status_code=404, detail="Clip file not found on disk")
        return FileResponse(clip_path, media_type="video/mp4")
