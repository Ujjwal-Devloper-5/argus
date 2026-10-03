"""
WebSocket endpoint that pushes live security events to the browser.
"""
import asyncio
import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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

async def ws_kafka_bridge():
    """Background task to bridge Kafka events to WebSockets."""
    if not settings.kafka.enabled or ArgusConsumer is None:
        logger.info("Kafka disabled. Starting fallback heartbeat generator for WS.")
        while True:
            await asyncio.sleep(30)
            heartbeat = {"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()}
            await events_manager.broadcast(json.dumps(heartbeat))
        return

    async def handler(payload):
        # Translate event payload to WS model format
        try:
            ws_msg = AlertEventWS(
                id=payload.get("id", 0),
                camera_name=payload.get("camera_name", "unknown"),
                severity="critical" if payload.get("is_suspicious") else "info",
                is_suspicious=payload.get("is_suspicious", False),
                thumbnail_path=payload.get("thumbnail_path"),
                created_at=payload.get("timestamp", datetime.now(UTC).isoformat()),
                message=payload.get("llm_analysis")
            )
            await events_manager.broadcast(ws_msg.model_dump_json())
        except Exception as e:
            logger.error("Error processing WS event", error=str(e))

    consumer = ArgusConsumer(
        settings=settings,
        topics=[settings.kafka.topics.events],
        group_id="argus-dashboard-events",
        handler=handler
    )

    try:
        await consumer.start()
        await consumer.consume()
    except asyncio.CancelledError:
        await consumer.stop()

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    # Basic token check could be implemented here
    await events_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        events_manager.disconnect(websocket)
