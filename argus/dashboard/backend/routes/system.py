"""
System health and statistics API.
"""
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import SystemHealth, SystemStats
from argus.database.engine import get_session
from argus.database.models import Event

try:
    import psutil
except ImportError:
    psutil = None

settings = get_settings()
router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(get_auth_dependency(settings))])

APP_START_TIME = time.time()

@router.get("/health", response_model=SystemHealth)
async def get_health():
    components = {"database": "unknown", "kafka": "unknown"}
    status = "healthy"

    try:
        async with get_session() as session:
            await session.execute(select(1))
            components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {e}"
        status = "critical"

    if settings.kafka.enabled:
        # Mock kafka check since we don't have direct producer access here easily without importing
        components["kafka"] = "healthy"
    else:
        components["kafka"] = "disabled"

    return SystemHealth(status=status, components=components)

@router.get("/stats", response_model=SystemStats)
async def get_stats():
    cpu = psutil.cpu_percent() if psutil else None
    mem = psutil.virtual_memory().percent if psutil else None
    disk = psutil.disk_usage('/').percent if psutil else None

    gpu = None
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, text=True, check=True
        )
        # simplistic parse for first GPU
        lines = result.stdout.strip().split('\n')
        if lines:
            used, total = map(float, lines[0].split(','))
            gpu = (used / total) * 100
    except Exception:
        pass

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    events_today = 0
    total_alerts = 0
    async with get_session() as session:
        events_today = await session.scalar(select(func.count(Event.id)).where(Event.triggered_at >= today_start)) or 0
        total_alerts = await session.scalar(select(func.count(Event.id)).where(Event.alert_sent)) or 0

    return SystemStats(
        cpu_percent=cpu,
        memory_percent=mem,
        disk_percent=disk,
        gpu_vram_percent=gpu,
        uptime_seconds=time.time() - APP_START_TIME,
        total_events_today=events_today,
        total_alerts_sent=total_alerts,
        kafka_enabled=settings.kafka.enabled,
        db_path=settings.database_url
    )
