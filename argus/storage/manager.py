"""
Argus Storage Manager — Kafka-backed async upload coordinator.

The StorageManager is the single entry-point for all clip upload operations.
It decouples the recording pipeline from the upload I/O:

  RecorderWorker
      │
      └─ enqueue(clip_path, event_id)  ← non-blocking, returns immediately
              │
         publish to [Kafka: argus.uploads]
              │
    [Background Kafka consumer]
              │
         backend.upload(clip_path)
              │
         DB: update Clip.remote_url
              │
         commit Kafka offset

If the upload fails, the Kafka consumer retries with backoff.
After max_retries, the message goes to argus.dlq.
Crash the process at any point — on restart, the consumer
picks up from the last committed offset. No clips are lost.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from argus.storage.base import StorageBackend, StorageUploadError

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class StorageManager:
    """
    Kafka-backed async upload coordinator.

    Accepts upload jobs via enqueue() and processes them in the background
    using the configured StorageBackend.

    Lifecycle:
        manager = StorageManager(backend, producer, consumer)
        await manager.start()            # verify backend + start Kafka consumer
        await manager.enqueue(path, id)  # non-blocking
        await manager.stop()             # drain + commit offsets
    """

    def __init__(
        self,
        backend: StorageBackend,
        producer,   # ArgusProducer
        consumer,   # ArgusConsumer
        session_factory=None,  # async DB session factory (optional)
    ) -> None:
        self._backend = backend
        self._producer = producer
        self._consumer = consumer
        self._session_factory = session_factory
        self._consumer_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Verify the backend is reachable, then start the Kafka consumer task."""
        ok = await self._backend.verify_connectivity()
        if not ok:
            logger.warning(
                "Storage backend connectivity check failed — uploads may not work"
            )

        self._running = True
        self._consumer_task = asyncio.create_task(
            self._consumer.consume(),
            name="argus-storage-consumer",
        )
        logger.info("StorageManager started")

    async def stop(self) -> None:
        """Stop the consumer task and flush pending offsets."""
        self._running = False
        await self._consumer.stop()
        if self._consumer_task:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
        logger.info("StorageManager stopped")

    async def enqueue(
        self,
        local_path: str | Path,
        event_id: int,
        camera_name: str = "",
    ) -> None:
        """
        Publish an upload job to Kafka.

        Non-blocking — returns immediately. The Kafka consumer
        will process this message asynchronously.

        Args:
            local_path:  Absolute path to the local MP4 clip.
            event_id:    DB Event ID to update with the remote URL.
            camera_name: Camera name for structured logging.
        """
        from argus.kafka.topics import ArgusTopics

        path_str = str(local_path)
        await self._producer.publish(
            topic=ArgusTopics.UPLOADS,
            key=str(event_id),
            value={
                "path": path_str,
                "event_id": event_id,
                "camera": camera_name,
                "enqueued_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info(
            "Upload job enqueued",
            path=path_str,
            event_id=event_id,
            camera=camera_name,
        )

    async def handle_upload_message(self, payload: dict) -> None:
        """
        Kafka consumer handler — called by ArgusConsumer for each upload message.

        This method is passed as the handler to ArgusConsumer.
        It performs the actual upload and updates the DB.
        """
        local_path = payload.get("path", "")
        event_id = payload.get("event_id")
        camera = payload.get("camera", "")

        if not local_path:
            raise ValueError(f"Invalid upload message — missing path: {payload}")

        logger.info(
            "Processing upload job",
            path=local_path,
            event_id=event_id,
            camera=camera,
        )

        try:
            remote_url = await self._backend.upload(local_path)
        except StorageUploadError as exc:
            logger.error(
                "Upload failed",
                path=local_path,
                event_id=event_id,
                error=str(exc),
            )
            raise  # Let ArgusConsumer handle retry + DLQ

        # Update DB if session factory is available
        if self._session_factory and event_id is not None:
            try:
                async with self._session_factory() as session:
                    from argus.database import repository
                    await repository.update_clip_remote_url(
                        session, event_id=event_id, remote_url=remote_url
                    )
                    await session.commit()
                    logger.info(
                        "Clip remote URL updated in DB",
                        event_id=event_id,
                        remote_url=remote_url,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to update Clip.remote_url in DB",
                    event_id=event_id,
                    error=str(exc),
                )
