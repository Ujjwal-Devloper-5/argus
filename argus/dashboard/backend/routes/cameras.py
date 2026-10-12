from __future__ import annotations

import asyncio
import glob
import os
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import CameraStatus
from argus.dashboard.backend.schemas.settings import CameraUpdateRequest
from argus.database.engine import get_session
from argus.database.models import Camera, Event

router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(get_auth_dependency())])
_CONFIG_PATH = Path("config/config.yaml")


def _redact_rtsp(url: str) -> str:
    """Mask credentials in RTSP URL to prevent credential leakage in UI."""
    return re.sub(r"://([^:@]+):([^@]+)@", r"://***:***@", url)


def _load_yaml() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_yaml(data: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
    get_settings.cache_clear()


class StreamTestRequest(BaseModel):
    rtsp_url: str
    timeout_seconds: int = 5


class StreamTestResponse(BaseModel):
    success: bool
    message: str
    host: str | None = None
    port: int | None = None


@router.get("", response_model=list[CameraStatus])
async def list_cameras():
    settings = get_settings()
    async with get_session() as session:
        stmt = (
            select(
                Camera.name,
                func.count(Event.id).label("total_events"),
                func.max(Event.triggered_at).label("last_event_at"),
            )
            .outerjoin(Event, Camera.id == Event.camera_id)
            .group_by(Camera.name)
        )
        result = await session.execute(stmt)
        db_stats = {
            row.name: {"total_events": row.total_events, "last_event_at": row.last_event_at}
            for row in result.all()
        }

        res = []
        for cam in settings.cameras:
            stats = db_stats.get(cam.name, {"total_events": 0, "last_event_at": None})
            res.append(
                CameraStatus(
                    name=cam.name,
                    rtsp_url=_redact_rtsp(cam.rtsp_url),
                    disabled=cam.disabled,
                    is_online=not cam.disabled,
                    total_events=stats["total_events"],
                    last_event_at=stats["last_event_at"],
                )
            )
        return res


@router.post("", response_model=CameraStatus)
async def add_camera(payload: CameraUpdateRequest):
    settings = get_settings()
    name_clean = payload.name.lower()
    if any(c.name.lower() == name_clean for c in settings.cameras):
        raise HTTPException(status_code=400, detail=f"Camera '{name_clean}' already exists")

    config_data = _load_yaml()
    cams = config_data.get("cameras", [])
    if not isinstance(cams, list):
        cams = []

    cam_dict = payload.model_dump(exclude_unset=True)
    cam_dict["name"] = name_clean
    cams.append(cam_dict)
    config_data["cameras"] = cams
    _save_yaml(config_data)

    return CameraStatus(
        name=name_clean,
        rtsp_url=_redact_rtsp(payload.rtsp_url),
        disabled=payload.disabled,
        is_online=not payload.disabled,
        total_events=0,
        last_event_at=None,
    )


@router.put("/{name}", response_model=CameraStatus)
async def update_camera(name: str, payload: CameraUpdateRequest):
    name_clean = name.lower()
    config_data = _load_yaml()
    cams = config_data.get("cameras", [])
    if not isinstance(cams, list):
        raise HTTPException(status_code=404, detail="No cameras configured")

    idx = next((i for i, c in enumerate(cams) if isinstance(c, dict) and c.get("name", "").lower() == name_clean), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Camera '{name_clean}' not found")

    existing_cam = cams[idx]
    # Preserve existing real RTSP URL if masked value passed
    new_rtsp = payload.rtsp_url
    if "***" in new_rtsp:
        new_rtsp = existing_cam.get("rtsp_url", new_rtsp)

    updated_dict = payload.model_dump(exclude_unset=True)
    updated_dict["name"] = payload.name.lower()
    updated_dict["rtsp_url"] = new_rtsp
    cams[idx] = updated_dict
    config_data["cameras"] = cams
    _save_yaml(config_data)

    return CameraStatus(
        name=updated_dict["name"],
        rtsp_url=_redact_rtsp(new_rtsp),
        disabled=payload.disabled,
        is_online=not payload.disabled,
        total_events=0,
        last_event_at=None,
    )


@router.delete("/{name}")
async def delete_camera(name: str):
    name_clean = name.lower()
    config_data = _load_yaml()
    cams = config_data.get("cameras", [])
    if not isinstance(cams, list):
        raise HTTPException(status_code=404, detail="No cameras configured")

    new_cams = [c for c in cams if isinstance(c, dict) and c.get("name", "").lower() != name_clean]
    if len(new_cams) == len(cams):
        raise HTTPException(status_code=404, detail=f"Camera '{name_clean}' not found")

    config_data["cameras"] = new_cams
    _save_yaml(config_data)
    return {"success": True, "message": f"Camera '{name_clean}' removed"}


@router.post("/test-stream", response_model=StreamTestResponse)
async def test_stream(req: StreamTestRequest):
    """Test TCP socket connectivity to the RTSP host and port."""
    parsed = urlparse(req.rtsp_url)
    host = parsed.hostname
    port = parsed.port or 554

    if not host:
        return StreamTestResponse(success=False, message="Invalid RTSP URL: hostname missing")

    loop = asyncio.get_running_loop()

    def _probe_tcp():
        try:
            with socket.create_connection((host, port), timeout=req.timeout_seconds):
                return True, "Connection established successfully"
        except socket.timeout:
            return False, f"Connection timed out after {req.timeout_seconds}s"
        except ConnectionRefusedError:
            return False, f"Port {port} connection refused on host {host}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    success, message = await loop.run_in_executor(None, _probe_tcp)
    return StreamTestResponse(success=success, message=message, host=host, port=port)


@router.get("/{name}/snapshot")
async def get_camera_snapshot(name: str):
    settings = get_settings()
    search_pattern = os.path.join(settings.thumbnails_path, f"{name}_*.jpg")
    loop = asyncio.get_running_loop()
    files = await loop.run_in_executor(None, glob.glob, search_pattern)
    if not files:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    latest_file = max(files, key=os.path.getctime)
    with open(latest_file, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="image/jpeg")


async def mjpeg_generator(name: str):
    settings = get_settings()
    search_pattern = os.path.join(settings.thumbnails_path, f"{name}_*.jpg")
    last_mtime = 0
    last_file = None
    loop = asyncio.get_running_loop()

    while True:
        files = await loop.run_in_executor(None, glob.glob, search_pattern)
        if not files:
            await asyncio.sleep(0.5)
            continue

        latest_file = max(files, key=os.path.getctime)
        mtime = os.path.getmtime(latest_file)

        if mtime > last_mtime or latest_file != last_file:
            last_mtime = mtime
            last_file = latest_file
            try:
                with open(latest_file, "rb") as f:
                    frame = f.read()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            except Exception:
                pass
        await asyncio.sleep(0.1)  # Max 10fps


@router.get("/{name}/stream")
async def get_camera_stream(name: str):
    return StreamingResponse(
        mjpeg_generator(name), media_type="multipart/x-mixed-replace; boundary=frame"
    )
