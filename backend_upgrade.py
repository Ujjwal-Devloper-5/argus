import os
import secrets
import textwrap

BACKEND_DIR = "/home/ujjwal/homelab/argus/argus/dashboard/backend"

# 1. Update auth.py
auth_py = os.path.join(BACKEND_DIR, "auth.py")
with open(auth_py, "w") as f:
    f.write(textwrap.dedent('''\
    """
    Argus Dashboard Authentication using JWT & HttpOnly Cookies.
    """
    import json
    import os
    import time
    from typing import Annotated, Optional

    import jwt
    from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
    from fastapi.security import HTTPBasicCredentials
    from pydantic import BaseModel
    import hashlib

    from argus.config import get_settings

    # Secret key for JWT
    JWT_SECRET = os.environ.get("ARGUS_JWT_SECRET", secrets.token_hex(32))
    ALGORITHM = "HS256"

    router = APIRouter(prefix="/api/auth", tags=["auth"])

    class LoginRequest(BaseModel):
        username: str
        password: str

    def verify_password(username: str, password: str) -> bool:
        users_file = "data/.dashboard_users.json"
        if os.path.exists(users_file):
            with open(users_file) as f:
                users = json.load(f)
            if username in users:
                stored = users[username]
                salt = bytes.fromhex(stored["salt"])
                key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
                return key.hex() == stored["hash"]
        
        # Fallback to settings
        settings = get_settings()
        return username == settings.dashboard.username and password == settings.dashboard.password

    @router.post("/login")
    async def login(req: LoginRequest, response: Response):
        if not verify_password(req.username, req.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create JWT token
        payload = {
            "sub": req.username,
            "exp": time.time() + (24 * 3600)  # 24 hours
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
        
        # Set HttpOnly Cookie
        response.set_cookie(
            key="argus_token",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=24 * 3600
        )
        return {"success": True, "username": req.username}

    @router.post("/logout")
    async def logout(response: Response):
        response.delete_cookie("argus_token")
        return {"success": True}

    @router.get("/ticket")
    async def get_ws_ticket(request: Request):
        # Must be authenticated to get a ticket
        token = request.cookies.get("argus_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Generate short-lived ticket
        ticket_payload = {
            "sub": payload["sub"],
            "type": "ws_ticket",
            "exp": time.time() + 60  # 60 seconds to connect
        }
        ticket = jwt.encode(ticket_payload, JWT_SECRET, algorithm=ALGORITHM)
        return {"ticket": ticket}

    def get_auth_dependency():
        def dependency(request: Request):
            token = request.cookies.get("argus_token")
            if not token:
                raise HTTPException(status_code=401, detail="Not authenticated")
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
                return payload["sub"]
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token expired")
            except jwt.PyJWTError:
                raise HTTPException(status_code=401, detail="Invalid token")
        return dependency

    def verify_ws_ticket(ticket: str) -> bool:
        if not ticket:
            return False
        try:
            payload = jwt.decode(ticket, JWT_SECRET, algorithms=[ALGORITHM])
            return payload.get("type") == "ws_ticket"
        except jwt.PyJWTError:
            return False
    '''))

# 2. Update app.py to mount auth router
app_py = os.path.join(BACKEND_DIR, "app.py")
with open(app_py, "r") as f:
    content = f.read()

if "from argus.dashboard.backend.auth import router as auth_router" not in content:
    content = content.replace(
        "from argus.dashboard.backend.routes.setup import router as setup_router",
        "from argus.dashboard.backend.routes.setup import router as setup_router\nfrom argus.dashboard.backend.auth import router as auth_router"
    )
    content = content.replace(
        "app.include_router(setup_router)",
        "app.include_router(setup_router)\napp.include_router(auth_router)"
    )
    with open(app_py, "w") as f:
        f.write(content)

# 3. Update cameras.py to add MJPEG streaming
cameras_py = os.path.join(BACKEND_DIR, "routes/cameras.py")
with open(cameras_py, "w") as f:
    f.write(textwrap.dedent('''\
    import asyncio
    import glob
    import os
    import time
    from fastapi import APIRouter, Depends, HTTPException, Response
    from fastapi.responses import StreamingResponse
    from sqlalchemy import func, select
    from argus.config import get_settings
    from argus.dashboard.backend.auth import get_auth_dependency
    from argus.dashboard.backend.models import CameraStatus
    from argus.database.engine import get_session
    from argus.database.models import Camera, Event

    settings = get_settings()
    router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(get_auth_dependency())])

    @router.get("", response_model=list[CameraStatus])
    async def list_cameras():
        async with get_session() as session:
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
                    is_online=not cam.disabled,
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

    async def mjpeg_generator(name: str):
        search_pattern = os.path.join(settings.thumbnails_path, f"{name}_*.jpg")
        last_mtime = 0
        last_file = None
        while True:
            files = glob.glob(search_pattern)
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
                    yield (b'--frame\\r\\n'
                           b'Content-Type: image/jpeg\\r\\n\\r\\n' + frame + b'\\r\\n')
                except Exception:
                    pass
            await asyncio.sleep(0.1)  # Max 10fps

    @router.get("/{name}/stream")
    async def get_camera_stream(name: str):
        return StreamingResponse(mjpeg_generator(name), media_type="multipart/x-mixed-replace; boundary=frame")
    '''))

# 4. Update events_ws.py to use tickets
ws_py = os.path.join(BACKEND_DIR, "websocket/events_ws.py")
with open(ws_py, "r") as f:
    ws_content = f.read()

if "verify_ws_ticket" not in ws_content:
    ws_content = ws_content.replace(
        "from fastapi import APIRouter, WebSocket, WebSocketDisconnect",
        "from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query\nfrom argus.dashboard.backend.auth import verify_ws_ticket"
    )
    ws_content = ws_content.replace(
        "async def websocket_endpoint(websocket: WebSocket, token: str | None = None):",
        "async def websocket_endpoint(websocket: WebSocket, ticket: str = Query(...)):\n    if not verify_ws_ticket(ticket):\n        await websocket.close(code=1008)\n        return"
    )
    with open(ws_py, "w") as f:
        f.write(ws_content)

# 5. Update stats_ws.py to use tickets
stats_py = os.path.join(BACKEND_DIR, "websocket/stats_ws.py")
with open(stats_py, "r") as f:
    stats_content = f.read()

if "verify_ws_ticket" not in stats_content:
    stats_content = stats_content.replace(
        "from fastapi import APIRouter, WebSocket, WebSocketDisconnect",
        "from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query\nfrom argus.dashboard.backend.auth import verify_ws_ticket"
    )
    stats_content = stats_content.replace(
        "async def stats_websocket_endpoint(websocket: WebSocket):",
        "async def stats_websocket_endpoint(websocket: WebSocket, ticket: str = Query(...)):\n    if not verify_ws_ticket(ticket):\n        await websocket.close(code=1008)\n        return"
    )
    with open(stats_py, "w") as f:
        f.write(stats_content)

# 6. Create system restart endpoint
sys_py = os.path.join(BACKEND_DIR, "routes/system.py")
with open(sys_py, "r") as f:
    sys_content = f.read()

if "/restart" not in sys_content:
    sys_content += textwrap.dedent('''
    import sys
    @router.post("/restart")
    async def restart_system():
        """Restart the entire Argus pipeline dynamically."""
        # Cleanly exits the process. In a production environment (systemd/Docker), 
        # it will automatically restart. During local dev, we use os.execv.
        import threading
        def _restart():
            time.sleep(1)
            os.execv(sys.executable, ['python', '-m', 'argus'])
        threading.Thread(target=_restart).start()
        return {"success": True, "message": "Restarting system..."}
    ''')
    with open(sys_py, "w") as f:
        f.write(sys_content)

print("Backend refactor complete.")
