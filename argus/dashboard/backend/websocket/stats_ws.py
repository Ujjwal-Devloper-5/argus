"""
WebSocket endpoint for real-time system statistics.
"""
import asyncio
import time
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.models import SystemStats
from argus.dashboard.backend.websocket.events_ws import ConnectionManager
from argus.database.engine import get_session
from argus.database.models import Event

try:
    import psutil
except ImportError:
    psutil = None

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/ws/stats", tags=["ws"])
stats_manager = ConnectionManager()
APP_START_TIME = time.time()

async def stats_broadcaster():
    """Background task to broadcast system stats every 5s."""
    while True:
        try:
            await asyncio.sleep(5)
            if not stats_manager.active_connections:
                continue

            cpu = psutil.cpu_percent() if psutil else None
            mem = psutil.virtual_memory().percent if psutil else None
            disk = psutil.disk_usage('/').percent if psutil else None

            today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            events_today = 0
            total_alerts = 0

            try:
                async with get_session() as session:
                    events_today = await session.scalar(select(func.count(Event.id)).where(Event.triggered_at >= today_start)) or 0
                    total_alerts = await session.scalar(select(func.count(Event.id)).where(Event.alert_sent)) or 0
            except Exception as e:
                logger.error("DB error in stats broadcaster", error=str(e))

            stats = SystemStats(
                cpu_percent=cpu,
                memory_percent=mem,
                disk_percent=disk,
                gpu_vram_percent=None,
                uptime_seconds=time.time() - APP_START_TIME,
                total_events_today=events_today,
                total_alerts_sent=total_alerts,
                kafka_enabled=settings.kafka.enabled,
                db_path=settings.database_url
            )

            await stats_manager.broadcast(stats.model_dump_json())
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in stats broadcaster", error=str(e))

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    await stats_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        stats_manager.disconnect(websocket)
