"""Unified Job Control Plane P1 — `loreweave_jobs.emit.emit_job_event`.

Proves the outbox write shape (aggregate_type=`jobs` so the relay routes it to
loreweave:events:jobs), in-tx raise propagation (H1 — the status change must not commit
without its event), and the best-effort variant swallowing."""

from __future__ import annotations

import json

import pytest

from loreweave_jobs import (
    JobEvent,
    JobStatus,
    emit_job_event,
    emit_job_event_safe,
    skipped_emit_total,
)
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
async def test_emit_passes_through_p4_usage_fields():
    conn = FakeConn()
    await emit_job_event(
        conn,
        service="knowledge",
        job_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="22222222-2222-2222-2222-222222222222",
        kind="extraction",
        status=JobStatus.RUNNING,
        model="qwen2.5-7b-instruct",
        cost_usd=1.5,
        tokens_in=1000,
        tokens_out=200,
        params={"concurrency": 4, "scope": "ch 1-40"},
    )
    _, args = conn.calls[0]
    ev = JobEvent.from_payload(json.loads(args[3]))
    assert ev.model == "qwen2.5-7b-instruct"
    assert ev.cost_usd == 1.5
    assert ev.tokens_in == 1000 and ev.tokens_out == 200
    assert ev.params == {"concurrency": 4, "scope": "ch 1-40"}


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
async def test_emit_maps_known_native_alias_to_canonical():
    # A producer-native alias (e.g. "queued") maps to the canonical status instead of
    # raising in-tx (D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK).
    conn = FakeConn()
    await emit_job_event(
        conn, service="campaign", job_id="88888888-8888-8888-8888-888888888888",
        owner_user_id="u", kind="campaign", status="queued",
    )
    _, args = conn.calls[0]
    assert args[2] == "job.pending"
    ev = JobEvent.from_payload(json.loads(args[3]))
    assert ev.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_emit_coerces_uppercase_canonical():
    # Case-insensitive canonical: an uppercase "RUNNING" maps, not skips/raises.
    conn = FakeConn()
    await emit_job_event(
        conn, service="s", job_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        owner_user_id="u", kind="k", status="RUNNING",
    )
    _, args = conn.calls[0]
    assert args[2] == "job.running"


@pytest.mark.asyncio
async def test_emit_skips_unmappable_status_instead_of_raising():
    # The bug: an unknown native status reached JobStatus(...) and raised INSIDE the
    # producer's status-change tx, rolling back a legitimate transition. It must now be
    # skipped (no emit, no raise) so the tx commits; the reconcile sweep backstops.
    conn = FakeConn()
    before = skipped_emit_total()
    await emit_job_event(
        conn, service="campaign", job_id="99999999-9999-9999-9999-999999999999",
        owner_user_id="u", kind="campaign", status="some_native_substate",
    )
    assert conn.calls == []  # no outbox row written, and crucially no exception raised
    assert skipped_emit_total() == before + 1  # the skip is counted (observability)


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
