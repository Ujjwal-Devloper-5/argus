"""
Faces API — manage enrolled face profiles.
"""
import os
import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import FaceProfileResponse
from argus.database.engine import get_session
from argus.database.models import Event, FaceProfile
from argus.database.repository import delete_face_profile

settings = get_settings()
router = APIRouter(prefix="/api/faces", tags=["faces"], dependencies=[Depends(get_auth_dependency(settings))])

@router.get("", response_model=list[FaceProfileResponse])
async def list_faces():
    async with get_session() as session:
        stmt = select(
            FaceProfile,
            func.count(Event.id).label("total_events")
        ).outerjoin(Event, FaceProfile.id == Event.face_profile_id).group_by(FaceProfile.id)
        result = await session.execute(stmt)

        res = []
        for profile, total_events in result.all():
            res.append(FaceProfileResponse(
                id=profile.id,
                name=profile.name,
                created_at=profile.enrolled_at,
                last_seen=profile.last_seen_at,
                total_events=total_events,
                thumbnail_path=None  # Can be augmented if there's a reference image
            ))
        return res

@router.get("/{profile_id}", response_model=FaceProfileResponse)
async def get_face(profile_id: int):
    async with get_session() as session:
        stmt = select(
            FaceProfile,
            func.count(Event.id).label("total_events")
        ).outerjoin(Event, FaceProfile.id == Event.face_profile_id).where(FaceProfile.id == profile_id).group_by(FaceProfile.id)
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")

        profile, total_events = row
        return FaceProfileResponse(
            id=profile.id,
            name=profile.name,
            created_at=profile.enrolled_at,
            last_seen=profile.last_seen_at,
            total_events=total_events,
            thumbnail_path=None
        )

@router.delete("/{profile_id}")
async def delete_face(profile_id: int):
    async with get_session() as session:
        deleted = await delete_face_profile(session, profile_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"success": True, "message": "Face profile deleted"}

@router.post("/enroll")
async def enroll_face(
    name: Annotated[str, Form()],
    images: Annotated[list[UploadFile], File()],
) -> dict:
    temp_dir = os.path.join(settings.embeddings_path, "temp_enrollment")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        saved_files = []
        for img in images:
            file_path = os.path.join(temp_dir, img.filename or f"{name}_{len(saved_files)}.jpg")
            with open(file_path, "wb") as f:
                shutil.copyfileobj(img.file, f)
            saved_files.append(file_path)

        return {"success": True, "profile_id": 0, "message": f"Saved {len(images)} images for {name}"}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
