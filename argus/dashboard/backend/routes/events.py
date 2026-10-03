"""
Events API — lists and retrieves security events from the Argus database.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import selectinload

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import EventDetail, EventSummary
from argus.database.engine import get_session
from argus.database.models import Camera, Event

settings = get_settings()
router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_auth_dependency(settings))])

def get_severity(event: Event) -> str:
    if event.is_suspicious:
        return 'critical'
    if event.similarity_score is not None and event.similarity_score < 0.3:
        return 'warning'
    return 'info'

@router.get("", response_model=list[EventSummary])
async def list_events(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    camera_name: str | None = None,
    severity: str | None = None,
    suspicious_only: bool = False,
    search: str | None = None
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
                llm_desc = (e.llm_analysis[:97] + '...') if len(e.llm_analysis) > 100 else e.llm_analysis

            res.append(EventSummary(
                id=e.id,
                camera_name=e.camera.name if e.camera else "unknown",
                severity=get_severity(e),
                is_suspicious=e.is_suspicious,
                thumbnail_path=e.thumbnail_path,
                created_at=e.triggered_at,
                llm_description=llm_desc,
                similarity_score=e.similarity_score
            ))

        if severity:
            res = [r for r in res if r.severity == severity]

        return res

@router.get("/{event_id}", response_model=EventDetail)
async def get_event(event_id: int):
    async with get_session() as session:
        stmt = select(Event).options(selectinload(Event.camera), selectinload(Event.clips)).where(Event.id == event_id)
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

        return EventDetail(
            id=e.id,
            camera_name=e.camera.name if e.camera else "unknown",
            severity=get_severity(e),
            is_suspicious=e.is_suspicious,
            thumbnail_path=e.thumbnail_path,
            created_at=e.triggered_at,
            llm_description=e.llm_analysis,
            similarity_score=e.similarity_score,
            clip_local_path=clip_path,
            clip_remote_url=clip_url,
            camera_id=e.camera_id
        )
