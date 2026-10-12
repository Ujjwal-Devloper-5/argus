"""
Argus Dashboard — FastAPI application factory.
"""
import asyncio
import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from argus.config import get_settings
from argus.dashboard.backend.routes.cameras import router as cameras_router
from argus.dashboard.backend.routes.events import router as events_router
from argus.dashboard.backend.routes.faces import router as faces_router
from argus.dashboard.backend.routes.settings import router as settings_router
from argus.dashboard.backend.routes.setup import router as setup_router
from argus.dashboard.backend.auth import router as auth_router
from argus.dashboard.backend.routes.system import router as system_router
from argus.dashboard.backend.websocket.events_ws import router as events_ws_router
from argus.dashboard.backend.websocket.events_ws import ws_kafka_bridge
from argus.dashboard.backend.websocket.stats_ws import router as stats_ws_router
from argus.dashboard.backend.websocket.stats_ws import stats_broadcaster
from argus.database.engine import close_engine, setup_engine

logger = structlog.get_logger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Argus Dashboard")
    from argus.database.engine import _engine
    engine_created_here = False
    if _engine is None:
        setup_engine(settings.database_url)
        engine_created_here = True

    # Start background tasks
    task1 = asyncio.create_task(ws_kafka_bridge())
    task2 = asyncio.create_task(stats_broadcaster())

    yield

    # Shutdown
    logger.info("Shutting down Argus Dashboard")
    task1.cancel()
    task2.cancel()
    await asyncio.gather(task1, task2, return_exceptions=True)
    if engine_created_here:
        await close_engine()

app = FastAPI(
    title="Argus Security Dashboard",
    version="0.9.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8501", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup wizard — no auth required (runs before user exists)
app.include_router(setup_router)
app.include_router(auth_router)

# Authenticated REST routers
app.include_router(events_router)
app.include_router(cameras_router)
app.include_router(faces_router)
app.include_router(system_router)
app.include_router(settings_router)

# Mount WS routers
app.include_router(events_ws_router)
app.include_router(stats_ws_router)

# Serve static files if they exist
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dashboard", "static")

assets_dir = os.path.join(STATIC_DIR, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """Serve the React SPA with strict path containment to prevent path traversal."""
    # Strip leading slashes to prevent os.path.join root discard attack
    safe_subpath = full_path.lstrip("/\\")
    static_root = os.path.abspath(STATIC_DIR)
    target_path = os.path.abspath(os.path.join(STATIC_DIR, safe_subpath))

    # SECURITY: Strict containment check — must be inside STATIC_DIR
    if target_path.startswith(static_root + os.sep) or target_path == static_root:
        if os.path.isfile(target_path):
            return FileResponse(target_path)

    # SPA fallback: serve index.html for client-side routes
    index_file = os.path.join(static_root, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Dashboard UI not found. Run: npm run build")

def run():
    uvicorn.run(
        "argus.dashboard.backend.app:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=settings.debug
    )
