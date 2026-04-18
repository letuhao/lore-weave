"""K14.1 + K14.8 — Unit tests for event consumer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.consumer import EventConsumer
from app.events.dispatcher import EventDispatcher


@pytest.fixture
def dispatcher():
    d = EventDispatcher()
    d.register("test.event", AsyncMock())
    return d


@pytest.fixture
def pool():
    return AsyncMock()


def test_parse_event():
    """Consumer correctly parses Redis Stream fields."""
    consumer = EventConsumer.__new__(EventConsumer)
    consumer._running = False

    fields = {
        "event_type": "chapter.saved",
        "aggregate_id": str(uuid4()),
        "payload": json.dumps({"book_id": str(uuid4())}),
        "source": "book",
    }
    event = consumer._parse_event("loreweave:events:chapter", "1-0", fields)
    assert event is not None
    assert event.event_type == "chapter.saved"
    assert event.stream == "loreweave:events:chapter"
    assert isinstance(event.payload, dict)


def test_parse_event_missing_type():
    """Missing event_type returns None."""
    consumer = EventConsumer.__new__(EventConsumer)
    event = consumer._parse_event("stream", "1-0", {"payload": "{}"})
    assert event is None


def test_parse_event_invalid_json():
    """Invalid JSON payload still parses (empty dict)."""
    consumer = EventConsumer.__new__(EventConsumer)
    event = consumer._parse_event("stream", "1-0", {
        "event_type": "test",
        "payload": "not json!!!",
    })
    assert event is not None
    assert event.payload == {}


@pytest.mark.asyncio
async def test_handle_message_dispatches_and_acks(dispatcher, pool):
    """Successful dispatch → ack."""
    consumer = EventConsumer.__new__(EventConsumer)
    consumer._dispatcher = dispatcher
    consumer._pool = pool

    redis = AsyncMock()
    fields = {
        "event_type": "test.event",
        "aggregate_id": str(uuid4()),
        "payload": "{}",
    }
    await consumer._handle_message(redis, "stream", "1-0", fields)
    redis.xack.assert_called_once_with("stream", "knowledge-extractor", "1-0")


@pytest.mark.asyncio
async def test_handle_message_dlq_after_retries(pool):
    """Handler failure → DLQ after MAX_RETRIES."""
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    d = EventDispatcher()
    d.register("fail.event", handler)

    consumer = EventConsumer.__new__(EventConsumer)
    consumer._dispatcher = d
    consumer._pool = pool

    redis = AsyncMock()
    # Simulate retry count exceeding MAX_RETRIES
    redis.incr = AsyncMock(return_value=3)
    redis.expire = AsyncMock()
    redis.xack = AsyncMock()
    redis.delete = AsyncMock()

    fields = {
        "event_type": "fail.event",
        "aggregate_id": str(uuid4()),
        "payload": "{}",
    }
    await consumer._handle_message(redis, "stream", "1-0", fields)

    # Should have written to DLQ and acked
    pool.execute.assert_called_once()  # DLQ insert
    redis.xack.assert_called_once()  # ack after DLQ


@pytest.mark.asyncio
async def test_handle_message_retry_does_not_ack(pool):
    """Handler failure with retries remaining → don't ack."""
    handler = AsyncMock(side_effect=RuntimeError("transient"))
    d = EventDispatcher()
    d.register("retry.event", handler)

    consumer = EventConsumer.__new__(EventConsumer)
    consumer._dispatcher = d
    consumer._pool = pool

    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=1)  # first retry
    redis.expire = AsyncMock()

    fields = {
        "event_type": "retry.event",
        "aggregate_id": str(uuid4()),
        "payload": "{}",
    }
    await consumer._handle_message(redis, "stream", "1-0", fields)

    # Should NOT ack — message stays pending
    redis.xack.assert_not_called()
