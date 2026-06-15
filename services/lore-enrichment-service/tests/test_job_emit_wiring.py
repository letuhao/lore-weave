"""Unified Job Control Plane P1 — emit_job_event wiring on lore-enrichment.

The shared emit lib + JobEvent payload shape are SDK-tested centrally; these prove the
WIRING fires at lore-enrichment's TWO job-status chokepoints — ``enrichment_job``
(PgProposalStore.create_job / mark_job_status + the api/jobs.py author transitions) and
``enrichment_compose_task`` (create_compose_task + run_compose_task's _mark + the worker
claim) — on the SAME conn the write uses (event commits atomically with the status
change — H1), maps the right service/owner/kind/status, SKIPS the non-canonical
``estimating`` state, and does NOT fire when no row matched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import jobs as jobs_api
from app.compose import compose_task as ct
from app.jobs import proposal_store as ps
from app.jobs.proposal_store import PgProposalStore

USER = uuid4()
JOB = uuid4()
PROJ = uuid4()
BOOK = uuid4()


class FakeConn:
    """Minimal asyncpg-conn stand-in: fetchval/fetchrow return scripted values; the
    ``transaction()`` async-ctx is a no-op; execute records nothing."""

    def __init__(self, *, fetchval=None, fetchrow=None):
        self._fetchval = fetchval
        self._fetchrow = fetchrow

    async def fetchval(self, *a, **k):
        return self._fetchval

    async def fetchrow(self, *a, **k):
        return self._fetchrow

    async def execute(self, *a, **k):
        return "UPDATE 1"

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()


class FakePool:
    """asyncpg.Pool stand-in: ``acquire()`` async-ctx yields the given conn."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acq()


# ── enrichment_job: PgProposalStore.create_job (INSERT → pending) ─────────────


@pytest.mark.asyncio
async def test_create_job_emits_pending(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ps, "emit_job_event", spy)
    repo = PgProposalStore(FakePool(FakeConn(fetchval=JOB)))
    out = await repo.create_job(
        user_id=str(USER), project_id=str(PROJ), book_id=str(BOOK),
        technique="retrieval", entity_kind="location",
        max_spend=None, estimated_cost=0.0,
    )
    assert out == str(JOB)
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "pending"
    assert kw["kind"] == "enrichment_job"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


# ── enrichment_job: PgProposalStore.mark_job_status (UPDATE → status) ─────────


@pytest.mark.asyncio
async def test_mark_job_status_emits_transition(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ps, "emit_job_event", spy)
    row = {"user_id": USER, "status": "completed", "error_message": None}
    repo = PgProposalStore(FakePool(FakeConn(fetchrow=row)))
    await repo.mark_job_status(job_id=str(JOB), status="completed")
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "completed"
    assert kw["kind"] == "enrichment_job"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)
    assert kw["error"] is None


@pytest.mark.asyncio
async def test_mark_job_status_failed_passes_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ps, "emit_job_event", spy)
    row = {"user_id": USER, "status": "failed", "error_message": "boom"}
    repo = PgProposalStore(FakePool(FakeConn(fetchrow=row)))
    await repo.mark_job_status(job_id=str(JOB), status="failed", error_message="boom")
    kw = spy.await_args.kwargs
    assert kw["status"] == "failed"
    assert kw["error"] == {"code": "error", "message": "boom"}


@pytest.mark.asyncio
async def test_mark_job_status_estimating_skips_emit(monkeypatch):
    """``estimating`` has no canonical JobStatus → skip the emit (else the SDK would
    raise inside the status-change tx and roll the legitimate UPDATE back)."""
    spy = AsyncMock()
    monkeypatch.setattr(ps, "emit_job_event", spy)
    row = {"user_id": USER, "status": "estimating", "error_message": None}
    repo = PgProposalStore(FakePool(FakeConn(fetchrow=row)))
    await repo.mark_job_status(job_id=str(JOB), status="estimating")
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_job_status_missing_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ps, "emit_job_event", spy)
    repo = PgProposalStore(FakePool(FakeConn(fetchrow=None)))
    await repo.mark_job_status(job_id=str(JOB), status="completed")
    spy.assert_not_awaited()


# ── enrichment_job: api/jobs.py author lifecycle transition ───────────────────


@pytest.mark.asyncio
async def test_transition_job_emits_canonical(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(jobs_api, "emit_job_event", spy)
    # The SELECT (status read) then the UPDATE both go through the same conn.
    conn = FakeConn(fetchrow={"status": "paused"})
    principal = jobs_api.Principal(user_id=USER)
    out = await jobs_api._transition_job(
        action="resume", job_id=JOB, project_id=PROJ,
        principal=principal, pool=FakePool(conn),
    )
    assert out["status"] == "running"
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "running"
    assert kw["kind"] == "enrichment_job"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_transition_job_start_skips_estimating(monkeypatch):
    """``start`` walks pending→estimating→running; only the final canonical 'running'
    is emitted (the transient 'estimating' is skipped) and only ONCE."""
    spy = AsyncMock()
    monkeypatch.setattr(jobs_api, "emit_job_event", spy)
    conn = FakeConn(fetchrow={"status": "pending"})
    principal = jobs_api.Principal(user_id=USER)
    out = await jobs_api._transition_job(
        action="start", job_id=JOB, project_id=PROJ,
        principal=principal, pool=FakePool(conn),
    )
    assert out["status"] == "running"
    spy.assert_awaited_once()
    assert spy.await_args.kwargs["status"] == "running"


# ── enrichment_compose_task: create_compose_task (INSERT → pending) ───────────


@pytest.mark.asyncio
async def test_create_compose_task_emits_pending(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ct, "emit_job_event", spy)
    task_id = uuid4()
    out = await ct.create_compose_task(
        FakePool(FakeConn(fetchval=task_id)),
        kind="profile_suggest", user_id=str(USER), project_id=str(PROJ),
        book_id=str(BOOK), request={"x": 1},
    )
    assert out == str(task_id)
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "pending"
    assert kw["kind"] == "profile_suggest"  # the compose task's own kind
    assert kw["job_id"] == str(task_id)
    assert kw["owner_user_id"] == str(USER)


# ── enrichment_compose_task: _mark (UPDATE → completed/failed) ────────────────


@pytest.mark.asyncio
async def test_compose_mark_emits_completed(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ct, "emit_job_event", spy)
    task_id = uuid4()
    row = {"user_id": USER, "kind": "intent_resolve",
           "status": "completed", "error_message": None}
    await ct._mark(
        FakePool(FakeConn(fetchrow=row)),
        task_id=str(task_id), status="completed", result={"ok": True},
    )
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "completed"
    assert kw["kind"] == "intent_resolve"
    assert kw["job_id"] == str(task_id)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_compose_mark_failed_passes_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ct, "emit_job_event", spy)
    task_id = uuid4()
    row = {"user_id": USER, "kind": "profile_suggest",
           "status": "failed", "error_message": "bad llm"}
    await ct._mark(
        FakePool(FakeConn(fetchrow=row)),
        task_id=str(task_id), status="failed", error="bad llm",
    )
    kw = spy.await_args.kwargs
    assert kw["status"] == "failed"
    assert kw["error"] == {"code": "error", "message": "bad llm"}


@pytest.mark.asyncio
async def test_compose_mark_missing_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ct, "emit_job_event", spy)
    await ct._mark(
        FakePool(FakeConn(fetchrow=None)),
        task_id=str(uuid4()), status="completed",
    )
    spy.assert_not_awaited()


# ── enrichment_compose_task: _claim_for_run (claim → running) ─────────────────


@pytest.mark.asyncio
async def test_compose_claim_emits_running(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(ct, "emit_job_event", spy)
    task_id = uuid4()
    # The FOR-UPDATE SELECT returns a claimable row; the claim UPDATE then runs.
    row = {"task_id": task_id, "kind": "profile_suggest",
           "status": "pending", "user_id": USER, "request_json": "{}"}
    verdict, claimed = await ct._claim_for_run(
        FakePool(FakeConn(fetchrow=row)), task_id=str(task_id), idle_window_s=60.0,
    )
    assert verdict == "run"
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "lore_enrichment"
    assert kw["status"] == "running"
    assert kw["kind"] == "profile_suggest"
    assert kw["job_id"] == str(task_id)
    assert kw["owner_user_id"] == str(USER)
