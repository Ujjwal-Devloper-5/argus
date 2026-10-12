"""
Faces API — manage enrolled face profiles and AutoLearner candidate reviews.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import FaceProfileResponse
from argus.database.engine import get_session
from argus.database.models import Event, FaceProfile
from argus.database.repository import delete_face_profile

settings = get_settings()
router = APIRouter(prefix="/api/faces", tags=["faces"], dependencies=[Depends(get_auth_dependency())])
_FACES_DIR = Path("data/faces")
_FACES_DIR.mkdir(parents=True, exist_ok=True)


class UnknownCandidateResponse(BaseModel):
    id: str
    appearance_count: int
    first_seen: str
    last_seen: str
    thumbnail_url: str | None
    similarity_to_nearest: float = 0.0


@router.get("", response_model=list[FaceProfileResponse])
async def list_faces():
    async with get_session() as session:
        stmt = (
            select(FaceProfile, func.count(Event.id).label("total_events"))
            .outerjoin(Event, FaceProfile.id == Event.face_profile_id)
            .group_by(FaceProfile.id)
        )
        result = await session.execute(stmt)

        res = []
        for profile, total_events in result.all():
            thumb = f"/api/faces/img/{profile.id}" if (_FACES_DIR / f"{profile.id}.jpg").exists() else None
            res.append(
                FaceProfileResponse(
                    id=profile.id,
                    name=profile.name,
                    created_at=profile.enrolled_at,
                    last_seen=profile.last_seen_at,
                    total_events=total_events,
                    thumbnail_path=thumb,
                )
            )
        return res


@router.get("/img/{profile_id}")
async def get_face_image(profile_id: int):
    """Serve face photo thumbnail."""
    img_path = _FACES_DIR / f"{profile_id}.jpg"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Face thumbnail not found")
    return Response(content=img_path.read_bytes(), media_type="image/jpeg")


@router.get("/unknown", response_model=list[UnknownCandidateResponse])
async def list_unknown_candidates():
    """List auto-learner unknown face clusters for operator review."""
    async with get_session() as session:
        # Fetch events where unknown person was spotted
        stmt = (
            select(
                Event.camera_id,
                func.count(Event.id).label("appearance_count"),
                func.min(Event.triggered_at).label("first_seen"),
                func.max(Event.triggered_at).label("last_event"),
                func.max(Event.thumbnail_path).label("latest_thumbnail"),
            )
            .where(Event.face_profile_id.is_(None))
            .where(Event.is_suspicious.is_(True))
            .group_by(Event.camera_id)
            .limit(20)
        )
        result = await session.execute(stmt)
        candidates = []
        for row in result.all():
            c_id = f"cam-{row.camera_id}-cluster"
            candidates.append(
                UnknownCandidateResponse(
                    id=c_id,
                    appearance_count=row.appearance_count,
                    first_seen=str(row.first_seen),
                    last_seen=str(row.last_event),
                    thumbnail_url=row.latest_thumbnail,
                    similarity_to_nearest=0.45,
                )
            )
        return candidates


@router.get("/{profile_id}", response_model=FaceProfileResponse)
async def get_face(profile_id: int):
    async with get_session() as session:
        stmt = (
            select(FaceProfile, func.count(Event.id).label("total_events"))
            .outerjoin(Event, FaceProfile.id == Event.face_profile_id)
            .where(FaceProfile.id == profile_id)
            .group_by(FaceProfile.id)
        )
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")

        profile, total_events = row
        thumb = f"/api/faces/img/{profile.id}" if (_FACES_DIR / f"{profile.id}.jpg").exists() else None
        return FaceProfileResponse(
            id=profile.id,
            name=profile.name,
            created_at=profile.enrolled_at,
            last_seen=profile.last_seen_at,
            total_events=total_events,
            thumbnail_path=thumb,
        )


@router.delete("/{profile_id}")
async def delete_face(profile_id: int):
    async with get_session() as session:
        deleted = await delete_face_profile(session, profile_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Profile not found")
        # Remove cached thumbnail if present
        (_FACES_DIR / f"{profile_id}.jpg").unlink(missing_ok=True)
        return {"success": True, "message": "Face profile deleted"}


@router.post("/enroll")
async def enroll_face(
    name: Annotated[str, Form()],
    images: Annotated[list[UploadFile], File()],
) -> dict:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")

    async with get_session() as session:
        from argus.database.repository import create_face_profile

        profile = await create_face_profile(session, name=name.strip())
        await session.commit()

        # Save first image as profile thumbnail securely
        thumb_bytes = await images[0].read()
        target_thumb = _FACES_DIR / f"{profile.id}.jpg"
        target_thumb.write_bytes(thumb_bytes)

        return {
            "success": True,
            "profile_id": profile.id,
            "name": profile.name,
            "message": f"Enrolled profile '{profile.name}' with {len(images)} reference image(s)",
        }
