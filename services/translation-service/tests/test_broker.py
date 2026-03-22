"""
Unit tests for broker.py — Plan §3 message format and routing key contracts.

Tests inject mock exchange objects to verify that publish() and publish_event()
produce correctly shaped AMQP messages without connecting to a real broker.
"""
import json
import pytest
import aio_pika
from unittest.mock import AsyncMock


# ── publish() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_routes_to_correct_exchange():
    """publish() must call _jobs_exchange.publish, not the events exchange."""
    import app.broker as broker
    mock_jobs = AsyncMock()
    mock_events = AsyncMock()
    original_jobs, original_events = broker._jobs_exchange, broker._events_exchange
    broker._jobs_exchange = mock_jobs
    broker._events_exchange = mock_events
    try:
        await broker.publish("translation.job", {"job_id": "abc"})
        mock_jobs.publish.assert_called_once()
        mock_events.publish.assert_not_called()
    finally:
        broker._jobs_exchange = original_jobs
        broker._events_exchange = original_events


@pytest.mark.asyncio
async def test_publish_uses_persistent_delivery_mode():
    """Messages must be durable (delivery_mode=PERSISTENT) — Plan §3.3."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._jobs_exchange
    broker._jobs_exchange = mock_exchange
    try:
        await broker.publish("translation.job", {"job_id": "abc", "user_id": "xyz"})
        msg: aio_pika.Message = mock_exchange.publish.call_args.args[0]
        assert msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    finally:
        broker._jobs_exchange = original


@pytest.mark.asyncio
async def test_publish_passes_routing_key():
    """publish() must forward the caller's routing_key unchanged."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._jobs_exchange
    broker._jobs_exchange = mock_exchange
    try:
        await broker.publish("translation.chapter", {"chapter_id": "c1"})
        routing_key = mock_exchange.publish.call_args.kwargs["routing_key"]
        assert routing_key == "translation.chapter"
    finally:
        broker._jobs_exchange = original


@pytest.mark.asyncio
async def test_publish_body_is_valid_json():
    """Message body must be deserializable JSON."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._jobs_exchange
    broker._jobs_exchange = mock_exchange
    try:
        payload = {"job_id": "j1", "chapter_ids": ["c1", "c2"], "total": 2}
        await broker.publish("translation.job", payload)
        msg: aio_pika.Message = mock_exchange.publish.call_args.args[0]
        body = json.loads(msg.body)
        assert body == payload
    finally:
        broker._jobs_exchange = original


@pytest.mark.asyncio
async def test_publish_raises_assertion_if_not_connected():
    """publish() must raise AssertionError when broker is not connected."""
    import app.broker as broker
    original = broker._jobs_exchange
    broker._jobs_exchange = None
    try:
        with pytest.raises(AssertionError, match="Broker not connected"):
            await broker.publish("translation.job", {"x": 1})
    finally:
        broker._jobs_exchange = original


# ── publish_event() ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_event_injects_user_id_into_body():
    """publish_event() must merge user_id into the event envelope — Plan §3.5."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._events_exchange
    broker._events_exchange = mock_exchange
    try:
        await broker.publish_event("user-abc", {"event": "job.created", "job_id": "j1", "payload": {}})
        msg: aio_pika.Message = mock_exchange.publish.call_args.args[0]
        body = json.loads(msg.body)
        assert body["user_id"] == "user-abc"
        assert body["event"] == "job.created"
    finally:
        broker._events_exchange = original


@pytest.mark.asyncio
async def test_publish_event_routing_key_is_user_dot_userid():
    """Routing key must be user.<userId> so topic exchange routes per user — Plan §3.5."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._events_exchange
    broker._events_exchange = mock_exchange
    try:
        user_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        await broker.publish_event(user_id, {"event": "job.status_changed", "payload": {}})
        routing_key = mock_exchange.publish.call_args.kwargs["routing_key"]
        assert routing_key == f"user.{user_id}"
    finally:
        broker._events_exchange = original


@pytest.mark.asyncio
async def test_publish_event_does_not_use_persistent_delivery():
    """Events are fire-and-forget — no delivery_mode requirement; just verify no crash."""
    import app.broker as broker
    mock_exchange = AsyncMock()
    original = broker._events_exchange
    broker._events_exchange = mock_exchange
    try:
        await broker.publish_event("u1", {"event": "test", "payload": {}})
        mock_exchange.publish.assert_called_once()
    finally:
        broker._events_exchange = original


@pytest.mark.asyncio
async def test_publish_event_raises_assertion_if_not_connected():
    """publish_event() must raise AssertionError when broker is not connected."""
    import app.broker as broker
    original = broker._events_exchange
    broker._events_exchange = None
    try:
        with pytest.raises(AssertionError, match="Broker not connected"):
            await broker.publish_event("u1", {"event": "test"})
    finally:
        broker._events_exchange = original
