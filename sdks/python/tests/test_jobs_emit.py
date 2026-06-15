"""Unified Job Control Plane P1 — `loreweave_jobs.emit.emit_job_event`.

Proves the outbox write shape (aggregate_type=`jobs` so the relay routes it to
loreweave:events:jobs), in-tx raise propagation (H1 — the status change must not commit
without its event), and the best-effort variant swallowing."""

from __future__ import annotations

import json

import pytest

from loreweave_jobs import JobEvent, JobStatus, emit_job_event, emit_job_event_safe
from loreweave_jobs.contract import JOBS_AGGREGATE_TYPE


class FakeConn:
    def __init__(self, *, fail: bool = False):
        self.calls: list[tuple] = []
        self._fail = fail

    async def execute(self, sql, *args):
        if self._fail:
            raise RuntimeError("db down")
        self.calls.append((sql, args))


@pytest.mark.asyncio
async def test_emit_writes_outbox_row_shape():
    conn = FakeConn()
    await emit_job_event(
        conn,
        service="knowledge",
        job_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="22222222-2222-2222-2222-222222222222",
        kind="extraction",
        status=JobStatus.RUNNING,
        parent_job_id="33333333-3333-3333-3333-333333333333",
        detail_status="entity",
        progress={"done": 1, "total": 40},
        title="extract ch1-40",
    )
    assert len(conn.calls) == 1
    sql, args = conn.calls[0]
    assert "INSERT INTO outbox_events" in sql
    agg_type, agg_id, event_type, payload_json = args
    assert agg_type == JOBS_AGGREGATE_TYPE == "jobs"
    assert agg_id == "11111111-1111-1111-1111-111111111111"
    assert event_type == "job.running"
    # payload round-trips back to a JobEvent
    ev = JobEvent.from_payload(json.loads(payload_json))
    assert ev.service == "knowledge"
    assert ev.status == JobStatus.RUNNING
    assert ev.parent_job_id == "33333333-3333-3333-3333-333333333333"
    assert ev.progress == {"done": 1, "total": 40}
    assert ev.occurred_at is not None  # stamped when omitted


@pytest.mark.asyncio
async def test_emit_accepts_raw_status_string():
    conn = FakeConn()
    await emit_job_event(
        conn, service="s", job_id="44444444-4444-4444-4444-444444444444",
        owner_user_id="u", kind="k", status="completed",
    )
    _, args = conn.calls[0]
    assert args[2] == "job.completed"


@pytest.mark.asyncio
async def test_emit_in_tx_raises_so_tx_rolls_back():
    conn = FakeConn(fail=True)
    with pytest.raises(RuntimeError):
        await emit_job_event(
            conn, service="s", job_id="55555555-5555-5555-5555-555555555555",
            owner_user_id="u", kind="k", status=JobStatus.FAILED,
        )


@pytest.mark.asyncio
async def test_emit_safe_swallows_and_returns_false():
    conn = FakeConn(fail=True)
    ok = await emit_job_event_safe(
        conn, service="s", job_id="66666666-6666-6666-6666-666666666666",
        owner_user_id="u", kind="k", status=JobStatus.FAILED,
    )
    assert ok is False  # best-effort — never raises


@pytest.mark.asyncio
async def test_emit_safe_returns_true_on_success():
    conn = FakeConn()
    ok = await emit_job_event_safe(
        conn, service="s", job_id="77777777-7777-7777-7777-777777777777",
        owner_user_id="u", kind="k", status=JobStatus.RUNNING,
    )
    assert ok is True
    assert len(conn.calls) == 1
