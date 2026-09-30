"""
Argus Kafka Consumer — at-least-once delivery with retry and DLQ.

Behaviour:
  - Commits offset ONLY after handler succeeds
  - On failure: exponential backoff, retries up to max_retries
  - After max_retries: publishes failed message to argus.dlq
  - Consumer group ID governs partition assignment

Usage:
    consumer = ArgusConsumer(
        settings=settings,
        topics=[ArgusTopics.UPLOADS],
        group_id=ArgusConsumerGroups.STORAGE_WORKERS,
        handler=my_async_handler,
        producer=producer,  # for DLQ
    )
    await consumer.start()
    await consumer.consume()  # runs forever until stop() is called
    await consumer.stop()
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from argus.kafka.topics import ArgusTopics

logger = structlog.get_logger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]

_RETRY_DELAYS: tuple[float, ...] = (1.0, 5.0, 15.0)  # seconds between retries


class ArgusConsumer:
    """
    Resilient Kafka consumer.

    Commits offsets only after successful handler execution.
    Failed messages are retried with exponential backoff, then
    sent to argus.dlq before the offset is committed and
    processing continues.
    """

    def __init__(
        self,
        settings,
        topics: list[ArgusTopics | str],
        group_id: str,
        handler: MessageHandler,
        producer=None,  # ArgusProducer — needed for DLQ publishing
        max_retries: int = 3,
    ) -> None:
        self._settings = settings
        self._topics = [str(t) for t in topics]
        self._group_id = group_id
        self._handler = handler
        self._producer = producer
        self._max_retries = max_retries
        self._consumer = None
        self._running = False

    async def start(self) -> None:
        """Initialise and connect the underlying AIOKafkaConsumer."""
        try:
            from aiokafka import AIOKafkaConsumer

            cfg = self._settings.kafka
            self._consumer = AIOKafkaConsumer(
                *self._topics,
                bootstrap_servers=cfg.bootstrap_servers,
                group_id=self._group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                key_deserializer=lambda k: k.decode("utf-8") if k else None,
                auto_offset_reset=cfg.consumer.auto_offset_reset,
                enable_auto_commit=False,  # CRITICAL: manual commit after handler
                max_poll_records=cfg.consumer.max_poll_records,
                session_timeout_ms=30_000,
                heartbeat_interval_ms=10_000,
            )
            await self._consumer.start()
            self._running = True
            logger.info(
                "Kafka consumer started",
                topics=self._topics,
                group_id=self._group_id,
            )
        except Exception as exc:
            logger.error("Failed to start Kafka consumer", error=str(exc))
            raise

    async def stop(self) -> None:
        """Commit pending offsets and close the consumer gracefully."""
        self._running = False
        if self._consumer:
            try:
                await self._consumer.commit()
                await self._consumer.stop()
                logger.info("Kafka consumer stopped", group_id=self._group_id)
            except Exception as exc:
                logger.warning("Error stopping Kafka consumer", error=str(exc))

    async def consume(self) -> None:
        """
        Run the consume loop indefinitely until stop() is called.

        For each message:
          1. Call handler(payload)
          2. On success: commit offset
          3. On failure: retry up to max_retries with backoff
          4. After all retries fail: publish to DLQ, commit offset, continue
        """
        if not self._consumer or not self._running:
            raise RuntimeError("ArgusConsumer.start() must be called before consume()")

        async for msg in self._consumer:
            if not self._running:
                break

            payload = msg.value
            key = msg.key or ""
            topic = msg.topic

            success = await self._handle_with_retry(topic, key, payload)

            if not success:
                await self._send_to_dlq(topic, key, payload)

            # Commit offset only after handler completes (success OR DLQ)
            try:
                await self._consumer.commit()
            except Exception as exc:
                logger.warning("Offset commit failed", error=str(exc))

    async def _handle_with_retry(
        self,
        topic: str,
        key: str,
        payload: dict[str, Any],
    ) -> bool:
        """Attempt handler up to max_retries times. Returns True on success."""
        for attempt in range(self._max_retries):
            try:
                await self._handler(payload)
                logger.debug(
                    "Message handled",
                    topic=topic,
                    key=key,
                    attempt=attempt + 1,
                )
                return True
            except Exception as exc:
                delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                logger.warning(
                    "Message handler failed — retrying",
                    topic=topic,
                    key=key,
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    retry_in_seconds=delay,
                    error=str(exc),
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(delay)
        return False

    async def _send_to_dlq(
        self,
        topic: str,
        key: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish an unprocessable message to the Dead Letter Queue."""
        logger.error(
            "Message exhausted retries — sending to DLQ",
            topic=topic,
            key=key,
        )
        if self._producer and self._producer.is_started:
            try:
                await self._producer.publish(
                    ArgusTopics.DLQ,
                    key=key,
                    value={
                        "original_topic": topic,
                        "original_key": key,
                        "payload": payload,
                        "consumer_group": self._group_id,
                    },
                )
            except Exception as exc:
                logger.error("Failed to publish to DLQ", error=str(exc))
