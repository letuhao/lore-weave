"""Unified Job Control Plane P1 — emit_job_event wiring on translation_jobs chokepoints.

The shared emit lib + JobEvent payload shape are SDK-tested centrally; these prove the
WIRING fires at translation's job-status chokepoints (running fan-out, terminal finalize,
cancel) on the SAME conn the write uses (so the event commits atomically with the status
change — H1), maps the right fields (service="translation", status, job_id, owner), and
does NOT fire when no row matched.

The create/INSERT(pending) + no-work-completed chokepoints live in app.routers.jobs and
are exercised end-to-end through the create_job flow in test_jobs.py; here we cover the
worker/coordinator/cancel transitions that those tests don't drive.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.routers import jobs as jobs_router
from app.workers import coordinator as coordinator_mod
from app.workers import chapter_worker as worker_mod

USER = uuid4()
JOB = uuid4()


class _TxCM:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """Minimal asyncpg-conn stand-in. ``fetchrow`` returns a scripted row;
    ``transaction()`` is a no-op async CM. The pool flavour returns ITSELF from
    ``acquire()`` so a `async with pool.acquire() as conn` hands back this object."""

    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row

    async def execute(self, *a, **k):
        return None

    def transaction(self):
        return _TxCM()

    def acquire(self):
        conn = self

        class _AcquireCM:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _AcquireCM()


# ── coordinator: running transition ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_coordinator_emits_running(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(coordinator_mod, "emit_job_event", spy)
    pool = FakeConn({"owner_user_id": USER})
    publish = AsyncMock()
    publish_event = AsyncMock()
    msg = {"job_id": str(JOB), "user_id": str(USER), "chapter_ids": []}

    await coordinator_mod.handle_job_message(msg, pool, publish, publish_event)

    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "translation"
    assert kw["status"] == "running"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_coordinator_no_emit_when_no_row(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(coordinator_mod, "emit_job_event", spy)
    pool = FakeConn(None)  # UPDATE matched nothing (e.g. job already gone)
    msg = {"job_id": str(JOB), "user_id": str(USER), "chapter_ids": []}

    await coordinator_mod.handle_job_message(msg, pool, AsyncMock(), AsyncMock())

    spy.assert_not_awaited()


# ── chapter_worker: terminal finalize ────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_job_completion_emits_completed(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(worker_mod, "emit_job_event", spy)
    monkeypatch.setattr(worker_mod, "_send_translation_notification", AsyncMock())
    # P4 — cost is DERIVED out-of-tx via the estimate oracle; mock the resolver so the
    # test doesn't make a real HTTP call and the asserted cost is deterministic.
    cost_spy = AsyncMock(return_value=0.42)
    monkeypatch.setattr(worker_mod, "resolve_job_cost_usd", cost_spy)
    pool = FakeConn({
        "status": "completed", "completed_chapters": 3, "failed_chapters": 0,
        "total_chapters": 3, "owner_user_id": USER, "ti": 12000, "toks_out": 9000,
        "model_source": "user_model", "model_ref": uuid4(),
    })
    publish_event = AsyncMock()
    msg = {"job_id": str(JOB)}

    await worker_mod._check_job_completion(pool, JOB, str(USER), msg, publish_event)

    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "translation"
    assert kw["status"] == "completed"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)
    # P4 — terminal carries best-effort summed tokens (FakeConn returns the same row
    # for the SUM query, so ti/toks_out stand in for the aggregate) + the derived cost.
    assert kw["tokens_in"] == 12000 and kw["tokens_out"] == 9000
    assert kw["cost_usd"] == 0.42
    # cost was priced from the SUMMED actual tokens (D-JOBS-P4-TRANSLATION-COST)
    assert cost_spy.await_args.kwargs["input_tokens"] == 12000
    assert cost_spy.await_args.kwargs["output_tokens"] == 9000


@pytest.mark.asyncio
async def test_check_job_completion_maps_partial_to_completed(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(worker_mod, "emit_job_event", spy)
    monkeypatch.setattr(worker_mod, "_send_translation_notification", AsyncMock())
    monkeypatch.setattr(worker_mod, "resolve_job_cost_usd", AsyncMock(return_value=None))
    pool = FakeConn({
        "status": "partial", "completed_chapters": 2, "failed_chapters": 1,
        "total_chapters": 3, "owner_user_id": USER, "ti": 0, "toks_out": 0,
        "model_source": "user_model", "model_ref": uuid4(),
    })
    msg = {"job_id": str(JOB)}

    await worker_mod._check_job_completion(pool, JOB, str(USER), msg, AsyncMock())

    kw = spy.await_args.kwargs
    # 'partial' is not a canonical JobStatus → emitted as 'completed' (job finished).
    assert kw["status"] == "completed"


@pytest.mark.asyncio
async def test_check_job_completion_no_emit_when_not_done(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(worker_mod, "emit_job_event", spy)
    pool = FakeConn(None)  # guarded UPDATE matched nothing → job not done yet
    msg = {"job_id": str(JOB)}

    await worker_mod._check_job_completion(pool, JOB, str(USER), msg, AsyncMock())

    spy.assert_not_awaited()


# ── cancel transition ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_do_cancel_emits_cancelled(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(jobs_router, "emit_job_event", spy)
    db = FakeConn({"owner_user_id": USER})

    await jobs_router._do_cancel(db, JOB)

    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "translation"
    assert kw["status"] == "cancelled"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_do_cancel_no_emit_when_no_row(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(jobs_router, "emit_job_event", spy)
    db = FakeConn(None)  # nothing matched (already gone)

    await jobs_router._do_cancel(db, JOB)

    spy.assert_not_awaited()
