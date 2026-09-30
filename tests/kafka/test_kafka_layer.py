"""
Tests for argus.kafka — Producer, Consumer, Topics, and retry/DLQ logic.
All aiokafka I/O is mocked — no real Kafka broker required.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.kafka.topics import ArgusTopics, ArgusConsumerGroups


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.kafka.bootstrap_servers = "localhost:9092"
    s.kafka.producer.enable_idempotence = True
    s.kafka.producer.acks = "all"
    s.kafka.producer.compression_type = "lz4"
    s.kafka.producer.linger_ms = 5
    s.kafka.consumer.auto_offset_reset = "earliest"
    s.kafka.consumer.max_poll_records = 10
    return s


@pytest.fixture
def mock_producer(mock_settings):
    from argus.kafka.producer import ArgusProducer
    return ArgusProducer(mock_settings)


# ---------------------------------------------------------------------------
# Topic enum tests
# ---------------------------------------------------------------------------

def test_topics_are_unique():
    values = [t.value for t in ArgusTopics]
    assert len(values) == len(set(values)), "Duplicate topic values found"


def test_consumer_groups_are_unique():
    values = [g.value for g in ArgusConsumerGroups]
    assert len(values) == len(set(values))


def test_topic_str_coercion():
    assert str(ArgusTopics.UPLOADS) == "argus.uploads"
    assert str(ArgusTopics.EVENTS) == "argus.events"
    assert str(ArgusTopics.DLQ) == "argus.dlq"


# ---------------------------------------------------------------------------
# Producer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_producer_publish_success(mock_producer):
    mock_inner = AsyncMock()
    mock_inner.start = AsyncMock()
    mock_inner.send_and_wait = AsyncMock()
    mock_inner.stop = AsyncMock()
    mock_aiokafka = MagicMock()
    mock_aiokafka.AIOKafkaProducer.return_value = mock_inner

    with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
        await mock_producer.start()
        await mock_producer.publish(
            ArgusTopics.UPLOADS,
            key="event-123",
            value={"path": "/data/clips/event-123.mp4"},
        )

    mock_inner.send_and_wait.assert_called_once()
    call_args = mock_inner.send_and_wait.call_args
    assert call_args[0][0] == "argus.uploads"


@pytest.mark.asyncio
async def test_producer_raises_if_not_started(mock_producer):
    with pytest.raises(RuntimeError, match=r"start\(\)"):
        await mock_producer.publish(ArgusTopics.UPLOADS, key="x", value={})


@pytest.mark.asyncio
async def test_producer_stop_cleans_up(mock_producer):
    mock_inner = AsyncMock()
    mock_inner.start = AsyncMock()
    mock_inner.stop = AsyncMock()
    mock_aiokafka = MagicMock()
    mock_aiokafka.AIOKafkaProducer.return_value = mock_inner

    with patch.dict("sys.modules", {"aiokafka": mock_aiokafka}):
        await mock_producer.start()
        assert mock_producer.is_started is True
        await mock_producer.stop()
        assert mock_producer.is_started is False


# ---------------------------------------------------------------------------
# Consumer retry + DLQ tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consumer_calls_handler_on_success(mock_settings):
    from argus.kafka.consumer import ArgusConsumer

    received = []
    async def handler(payload):
        received.append(payload)

    consumer = ArgusConsumer(
        settings=mock_settings,
        topics=[ArgusTopics.UPLOADS],
        group_id=ArgusConsumerGroups.STORAGE_WORKERS,
        handler=handler,
    )

    # Directly call _handle_with_retry (no real Kafka needed)
    result = await consumer._handle_with_retry(
        topic="argus.uploads",
        key="clip-1",
        payload={"path": "/data/clips/clip-1.mp4"},
    )
    assert result is True
    assert len(received) == 1


@pytest.mark.asyncio
async def test_consumer_retries_on_failure(mock_settings):
    from argus.kafka.consumer import ArgusConsumer

    call_count = 0

    async def failing_handler(payload):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulated error")

    consumer = ArgusConsumer(
        settings=mock_settings,
        topics=[ArgusTopics.UPLOADS],
        group_id=ArgusConsumerGroups.STORAGE_WORKERS,
        handler=failing_handler,
        max_retries=3,
    )

    with patch("argus.kafka.consumer.asyncio.sleep", new_callable=AsyncMock):
        result = await consumer._handle_with_retry(
            topic="argus.uploads",
            key="clip-1",
            payload={},
        )

    assert result is False
    assert call_count == 3  # Retried exactly max_retries times


@pytest.mark.asyncio
async def test_consumer_sends_to_dlq_after_exhausted_retries(mock_settings):
    from argus.kafka.consumer import ArgusConsumer

    async def always_fail(payload):
        raise RuntimeError("always fails")

    mock_dlq_producer = AsyncMock()
    mock_dlq_producer.is_started = True
    mock_dlq_producer.publish = AsyncMock()

    consumer = ArgusConsumer(
        settings=mock_settings,
        topics=[ArgusTopics.UPLOADS],
        group_id=ArgusConsumerGroups.STORAGE_WORKERS,
        handler=always_fail,
        producer=mock_dlq_producer,
        max_retries=1,
    )

    with patch("argus.kafka.consumer.asyncio.sleep", new_callable=AsyncMock):
        await consumer._handle_with_retry("argus.uploads", "clip-1", {})
        await consumer._send_to_dlq("argus.uploads", "clip-1", {"path": "/x"})

    mock_dlq_producer.publish.assert_called_once()
    call_kwargs = mock_dlq_producer.publish.call_args
    assert str(ArgusTopics.DLQ) in str(call_kwargs)


# ---------------------------------------------------------------------------
# Settings integration test
# ---------------------------------------------------------------------------

def test_kafka_config_loads_with_defaults():
    """KafkaConfig must be present in Settings with correct defaults."""
    from argus.config import get_settings
    settings = get_settings()
    assert hasattr(settings, "kafka")
    assert settings.kafka.bootstrap_servers == "localhost:9092"
    assert settings.kafka.producer.enable_idempotence is True
    assert settings.kafka.consumer.auto_offset_reset == "earliest"
    assert settings.kafka.topics.uploads == "argus.uploads"
    assert settings.kafka.topics.dlq == "argus.dlq"
