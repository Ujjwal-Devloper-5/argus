"""
Argus Kafka Producer — idempotent async publisher.

Wraps aiokafka.AIOKafkaProducer with:
  - JSON serialisation for all values
  - Idempotent delivery (enable_idempotence=True, acks='all')
  - Structured logging on every publish
  - Graceful start/stop lifecycle

Usage:
    producer = ArgusProducer(settings)
    await producer.start()
    await producer.publish(ArgusTopics.UPLOADS, key="cam1", value={"path": "/data/clip.mp4"})
    await producer.stop()
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from argus.kafka.topics import ArgusTopics

logger = structlog.get_logger(__name__)


class ArgusProducer:
    """
    Idempotent Kafka producer.

    Thread-safe for use across asyncio tasks once started.
    All values are JSON-serialised before publishing.
    Keys are UTF-8 encoded strings.
    """

    def __init__(self, settings) -> None:
        self._settings = settings
        self._producer = None
        self._started = False

    async def start(self) -> None:
        """Initialise and connect the underlying AIOKafkaProducer."""
        try:
            from aiokafka import AIOKafkaProducer

            cfg = self._settings.kafka
            self._producer = AIOKafkaProducer(
                bootstrap_servers=cfg.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                enable_idempotence=cfg.producer.enable_idempotence,
                acks=cfg.producer.acks,
                compression_type="lz4",
                max_batch_size=65536,
                linger_ms=5,
            )
            await self._producer.start()
            self._started = True
            logger.info(
                "Kafka producer started",
                bootstrap_servers=cfg.bootstrap_servers,
            )
        except Exception as exc:
            logger.error("Failed to start Kafka producer", error=str(exc))
            raise

    async def stop(self) -> None:
        """Flush pending messages and close the connection gracefully."""
        if self._producer and self._started:
            try:
                await self._producer.stop()
                logger.info("Kafka producer stopped")
            except Exception as exc:
                logger.warning("Error stopping Kafka producer", error=str(exc))
            finally:
                self._started = False

    async def publish(
        self,
        topic: ArgusTopics | str,
        key: str,
        value: dict[str, Any],
    ) -> None:
        """
        Publish a message to a Kafka topic.

        Args:
            topic:  Target topic (use ArgusTopics enum).
            key:    Partition key — determines partition assignment.
                    Use camera_name for frames, face_hash for learn prompts,
                    event_id for events, clip path for uploads.
            value:  Dict payload, serialised to JSON automatically.

        Raises:
            RuntimeError: If producer has not been started.
        """
        if not self._started or self._producer is None:
            raise RuntimeError("ArgusProducer.start() must be called before publish()")

        topic_str = str(topic)
        try:
            await self._producer.send_and_wait(topic_str, key=key, value=value)
            logger.debug("Message published", topic=topic_str, key=key)
        except Exception as exc:
            logger.error(
                "Kafka publish failed",
                topic=topic_str,
                key=key,
                error=str(exc),
            )
            raise

    @property
    def is_started(self) -> bool:
        return self._started
