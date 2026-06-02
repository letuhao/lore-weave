"""K14.1 + K14.8 — Unit tests for event consumer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.consumer import BLOCK_MS, EventConsumer
from app.events.dispatcher import EventDispatcher


@pytest.fixture
def dispatcher():
    d = EventDispatcher()
    d.register("test.event", AsyncMock())
    return d


@pytest.fixture
def pool():
    return AsyncMock()


@pytest.mark.asyncio
async def test_run_continues_on_idle_timeout(monkeypatch):
    """D-REDIS8-CONSUMERS: redis-py 8 makes a blocking XREADGROUP(block=) raise
    TimeoutError on idle (5.x returned empty). TimeoutError is NOT a
    ConnectionError subclass, so without an explicit catch it fell to the generic
    handler (ERROR log + 2s sleep) on every idle tick. The loop must treat it as
    normal idle: continue, no ERROR, keep reading."""
    import redis.asyncio as aioredis

    consumer = EventConsumer("redis://x", AsyncMock(), MagicMock())
    fake_r = AsyncMock()
    monkeypatch.setattr(consumer, "_ensure_groups", AsyncMock())
    monkeypatch.setattr(consumer, "_process_pending", AsyncMock())
    monkeypatch.setattr(consumer, "_ensure_redis", AsyncMock(return_value=fake_r))

    calls = {"n": 0}

    async def _xread(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise aioredis.TimeoutError("Timeout reading from redis:6379")
        consumer._running = False  # stop after the 2nd (post-timeout) read
        return []

    fake_r.xreadgroup = AsyncMock(side_effect=_xread)

    err_logged = []
    monkeypatch.setattr(
        "app.events.consumer.logger.exception",
        lambda *a, **k: err_logged.append(a),
    )

    await consumer.run()

    assert calls["n"] == 2  # continued past the idle TimeoutError to a 2nd read
    assert err_logged == []  # TimeoutError did NOT hit the generic ERROR handler


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
async def test_ensure_redis_disables_socket_read_timeout(pool):
    """Regression: the blocking XREADGROUP loop must use a connection whose
    socket read timeout never pre-empts the server-side BLOCK.

    redis-py 8.0 changed AbstractConnection's default socket_timeout from
    None to 5s. With BLOCK_MS=5000 the per-read socket timeout races the
    BLOCK and wins every cycle, raising TimeoutError and wedging the
    consumer (zero events processed on all streams). _ensure_redis MUST
    pass socket_timeout=None so blocking reads are never pre-empted.

    Invariant asserted: socket_timeout is None (unbounded) OR strictly
    greater than BLOCK_MS/1000.
    """
    consumer = EventConsumer.__new__(EventConsumer)
    consumer._redis_url = "redis://redis:6379"
    consumer._redis = None

    with patch("app.events.consumer.aioredis.from_url") as from_url:
        from_url.return_value = AsyncMock()
        await consumer._ensure_redis()

    from_url.assert_called_once()
    socket_timeout = from_url.call_args.kwargs.get("socket_timeout", "MISSING")
    assert socket_timeout is None or socket_timeout > BLOCK_MS / 1000, (
        f"socket_timeout={socket_timeout!r} must be None or > {BLOCK_MS / 1000}s "
        "to avoid pre-empting the XREADGROUP BLOCK"
    )


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
