"""
Argus Dashboard — FastAPI application factory.
"""
import asyncio
import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from argus.config import get_settings
from argus.dashboard.backend.routes.cameras import router as cameras_router
from argus.dashboard.backend.routes.events import router as events_router
from argus.dashboard.backend.routes.faces import router as faces_router
from argus.dashboard.backend.routes.settings import router as settings_router
from argus.dashboard.backend.routes.setup import router as setup_router
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
    if engine_created_here:
        await close_engine()

app = FastAPI(
    title="Argus Security Dashboard",
    version="0.9.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup wizard — no auth required (runs before user exists)
app.include_router(setup_router)

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

if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

def run():
    uvicorn.run(
        "argus.dashboard.backend.app:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=settings.debug
    )
