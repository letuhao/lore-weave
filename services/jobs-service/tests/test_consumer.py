"""`JobProjectionConsumer` parse + handle + DLQ + notify (no Redis/DB)."""

import json
from unittest.mock import AsyncMock

import pytest

from app.projection.consumer import JobProjectionConsumer
from loreweave_jobs import JobEvent, JobStatus

U = "11111111-1111-1111-1111-111111111111"
J = "22222222-2222-2222-2222-222222222222"


def _event_fields(**over):
    ev = JobEvent(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, occurred_at="2026-06-15T10:00:00+00:00",
    )
    payload = ev.to_payload()
    payload.update(over)
    return {"event_type": "job.running", "payload": json.dumps(payload), "source": "knowledge"}


@pytest.fixture
def consumer(spy_pool):
    return JobProjectionConsumer("redis://x", spy_pool)


@pytest.mark.asyncio
async def test_handle_parses_and_upserts(consumer, spy_pool, monkeypatch):
    spy = AsyncMock(return_value=True)
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", spy)
    await consumer.handle("loreweave:events:jobs", "1-0", _event_fields())
    spy.assert_awaited_once()
    _conn, ev = spy.await_args.args
    assert isinstance(ev, JobEvent) and ev.service == "knowledge" and ev.job_id == J


@pytest.mark.asyncio
async def test_missing_payload_is_noop(consumer, monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", spy)
    await consumer.handle("s", "1-0", {"event_type": "job.running"})
    spy.assert_not_awaited()  # acked no-op, never raises


@pytest.mark.asyncio
async def test_invalid_json_is_noop(consumer, monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", spy)
    await consumer.handle("s", "1-0", {"payload": "{not json"})
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_payload_is_noop(consumer, monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", spy)
    # missing required keys (service/job_id/…) → from_payload raises → no-op
    await consumer.handle("s", "1-0", {"payload": json.dumps({"status": "running"})})
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_error_propagates_for_retry(consumer, monkeypatch):
    """A transient store failure must RAISE so the base applies retry→DLQ."""
    boom = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", boom)
    with pytest.raises(RuntimeError):
        await consumer.handle("loreweave:events:jobs", "1-0", _event_fields())


@pytest.mark.asyncio
async def test_notify_hook_fired_when_upsert_applied(spy_pool, monkeypatch):
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", AsyncMock(return_value=True))
    notify = AsyncMock()
    c = JobProjectionConsumer("redis://x", spy_pool, notify=notify)
    await c.handle("loreweave:events:jobs", "1-0", _event_fields())
    notify.assert_awaited_once()
    assert isinstance(notify.await_args.args[0], JobEvent)


@pytest.mark.asyncio
async def test_no_notify_when_upsert_is_monotonic_noop(spy_pool, monkeypatch):
    """A stale/duplicate event the upsert SKIPPED must not push an SSE frame."""
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", AsyncMock(return_value=False))
    notify = AsyncMock()
    c = JobProjectionConsumer("redis://x", spy_pool, notify=notify)
    await c.handle("loreweave:events:jobs", "1-0", _event_fields())
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_failure_does_not_break_projection(spy_pool, monkeypatch):
    monkeypatch.setattr("app.projection.consumer.upsert_job_event", AsyncMock(return_value=True))
    notify = AsyncMock(side_effect=RuntimeError("redis pub down"))
    c = JobProjectionConsumer("redis://x", spy_pool, notify=notify)
    await c.handle("loreweave:events:jobs", "1-0", _event_fields())  # must not raise


@pytest.mark.asyncio
async def test_on_dlq_writes_dead_letter(consumer, spy_pool):
    await consumer.on_dlq("loreweave:events:jobs", "9-0", _event_fields(), RuntimeError("x3"))
    spy_pool.execute.assert_awaited_once()
    args = spy_pool.execute.await_args.args
    assert "dead_letter_events" in args[0]
    assert args[1] == "loreweave:events:jobs" and args[2] == "9-0"
    assert args[4] == "x3"
