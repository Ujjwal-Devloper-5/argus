"""
Cameras API — returns camera status from settings + last event info from DB.
"""
import glob
import os

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import CameraStatus
from argus.database.engine import get_session
from argus.database.models import Camera, Event

settings = get_settings()
router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(get_auth_dependency(settings))])

@router.get("", response_model=list[CameraStatus])
async def list_cameras():
    async with get_session() as session:
        # Get DB stats
        stmt = select(
            Camera.name,
            func.count(Event.id).label("total_events"),
            func.max(Event.triggered_at).label("last_event_at")
        ).outerjoin(Event, Camera.id == Event.camera_id).group_by(Camera.name)

        result = await session.execute(stmt)
        db_stats = {row.name: {"total_events": row.total_events, "last_event_at": row.last_event_at} for row in result.all()}

        res = []
        for cam in settings.cameras:
            stats = db_stats.get(cam.name, {"total_events": 0, "last_event_at": None})
            res.append(CameraStatus(
                name=cam.name,
                rtsp_url=cam.rtsp_url,
                disabled=cam.disabled,
                is_online=not cam.disabled,  # Basic logic for now
                total_events=stats["total_events"],
                last_event_at=stats["last_event_at"]
            ))
        return res

@router.get("/{name}/snapshot")
async def get_camera_snapshot(name: str):
    search_pattern = os.path.join(settings.thumbnails_path, f"{name}_*.jpg")
    files = glob.glob(search_pattern)
    if not files:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    latest_file = max(files, key=os.path.getctime)
    with open(latest_file, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="image/jpeg")
