"""
WebSocket endpoint that pushes live security events to the browser.
"""
import asyncio
import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from argus.dashboard.backend.auth import verify_ws_ticket

from argus.config import get_settings
from argus.dashboard.backend.models import AlertEventWS

try:
    from argus.kafka.consumer import ArgusConsumer
except ImportError:
    ArgusConsumer = None

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/ws/events", tags=["ws"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

events_manager = ConnectionManager()


async def broadcast_event(payload: dict | AlertEventWS) -> None:
    """Broadcast a normalized security event to all active WebSocket clients."""
    try:
        if isinstance(payload, AlertEventWS):
            ws_msg = payload
        else:
            event_id = payload.get("id") or payload.get("event_id") or 0
            cam_name = payload.get("camera_name") or payload.get("camera") or "unknown"
            is_susp = bool(payload.get("is_suspicious", False))
            sev = payload.get("severity") or ("critical" if is_susp else "info")
            
            raw_thumb = payload.get("thumbnail_path")
            thumb_url = f"/api/events/{event_id}/thumbnail" if (raw_thumb and event_id) else raw_thumb
            
            created_at = (
                payload.get("created_at")
                or payload.get("timestamp")
                or payload.get("triggered_at")
                or datetime.now(UTC).isoformat()
            )
            msg = (
                payload.get("message")
                or payload.get("llm_analysis")
                or payload.get("llm_description")
                or payload.get("action_recommendation")
                or ("Suspicious person detected" if is_susp else "Person detected")
            )
            
            ws_msg = AlertEventWS(
                id=int(event_id),
                camera_name=str(cam_name),
                severity=str(sev),
                is_suspicious=is_susp,
                thumbnail_path=thumb_url,
                created_at=str(created_at),
                message=str(msg) if msg else None,
            )
        
        await events_manager.broadcast(ws_msg.model_dump_json())
    except Exception as exc:
        logger.error("Error broadcasting WS event", error=str(exc))


async def _run_db_event_poller() -> None:
    """Poll SQLite Event table for newly inserted records when Kafka is disabled."""
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    from argus.database.engine import get_session
    from argus.database.models import Event

    last_seen_id = 0
    try:
        async with get_session() as session:
            stmt = select(func.max(Event.id))
            max_id = await session.scalar(stmt)
            if max_id:
                last_seen_id = max_id
    except Exception as exc:
        logger.warning("Could not initialize last_seen_id for WS poller", error=str(exc))

    logger.info("WS SQLite event poller started", initial_id=last_seen_id)
    heartbeat_counter = 0

    while True:
        try:
            await asyncio.sleep(1.0)
            heartbeat_counter += 1
            if heartbeat_counter >= 30:
                heartbeat_counter = 0
                heartbeat = {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
                await events_manager.broadcast(json.dumps(heartbeat))

            async with get_session() as session:
                stmt = (
                    select(Event)
                    .options(selectinload(Event.camera))
                    .where(Event.id > last_seen_id)
                    .order_by(Event.id.asc())
                )
                result = await session.execute(stmt)
                new_events = result.scalars().all()

                for ev in new_events:
                    last_seen_id = max(last_seen_id, ev.id)
                    cam_name = ev.camera.name if ev.camera else "unknown"
                    thumb = f"/api/events/{ev.id}/thumbnail" if ev.thumbnail_path else None
                    ws_msg = AlertEventWS(
                        id=ev.id,
                        camera_name=cam_name,
                        severity="critical" if ev.is_suspicious else "info",
                        is_suspicious=ev.is_suspicious,
                        thumbnail_path=thumb,
                        created_at=ev.triggered_at.isoformat() if hasattr(ev.triggered_at, "isoformat") else str(ev.triggered_at),
                        message=ev.llm_analysis or "Person detected",
                    )
                    await events_manager.broadcast(ws_msg.model_dump_json())
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("WS DB poller transient error", error=str(exc))
            await asyncio.sleep(2.0)


async def ws_kafka_bridge():
    """Background task to bridge Kafka events or database events to WebSockets."""
    if not settings.kafka.enabled or ArgusConsumer is None:
        logger.info("Kafka disabled — using direct DB event poller for WebSockets.")
        await _run_db_event_poller()
        return

    async def handler(payload):
        await broadcast_event(payload)

    consumer = ArgusConsumer(
        settings=settings,
        topics=[settings.kafka.topics.events],
        group_id="argus-dashboard-events",
        handler=handler,
    )

    try:
        await consumer.start()
        await consumer.consume()
    except asyncio.CancelledError:
        await consumer.stop()
    except Exception as exc:
        logger.warning("Kafka consumer error — falling back to SQLite poller", error=str(exc))
        await _run_db_event_poller()

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, ticket: str = Query(default="")):
    if not verify_ws_ticket(ticket):
        await websocket.close(code=1008)  # WS_1008_POLICY_VIOLATION
        return
    await events_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        events_manager.disconnect(websocket)
