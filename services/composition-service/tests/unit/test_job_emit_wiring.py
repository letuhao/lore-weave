"""Unified Job Control Plane P1 — emit_job_event wiring on GenerationJobsRepo.

The shared emit lib + JobEvent payload shape are SDK-tested centrally; these prove the
WIRING fires at composition's job-status chokepoints (create + update_status) on the
SAME conn the write uses (so the event commits atomically with the status change — H1),
maps the right fields, and does NOT fire when no row matched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.repositories import generation_jobs
from app.db.repositories.generation_jobs import GenerationJobsRepo

USER = uuid4()
JOB = uuid4()
PROJ = uuid4()
BOOK = uuid4()


def _row(**over):
    base = dict(
        id=JOB, created_by=USER, project_id=PROJ, book_id=BOOK, outline_node_id=None,
        operation="generate", mode="auto", status="pending", llm_job_id=None,
        input={}, result=None, critic=None, target_chapter_id=None,
        base_revision_id=None, target_revision_id=None, cost_usd=Decimal("0"),
        idempotency_key=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return base


class FakeConn:
    """Minimal asyncpg-conn stand-in: fetchrow returns a scripted row; fetchval None."""

    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row

    async def fetchval(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_update_status_emits_job_event(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    repo = GenerationJobsRepo(pool=None)
    await repo.update_status(JOB, "completed", conn=FakeConn(_row(status="completed")))
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "composition"
    assert kw["status"] == "completed"
    assert kw["job_id"] == str(JOB)
    assert kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_update_status_failed_passes_error(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    repo = GenerationJobsRepo(pool=None)
    await repo.update_status(
        JOB, "failed", result={"error": "boom"},
        conn=FakeConn(_row(status="failed", result={"error": "boom"})),
    )
    kw = spy.await_args.kwargs
    assert kw["status"] == "failed"
    assert kw["error"] == {"code": "error", "message": "boom"}


@pytest.mark.asyncio
async def test_update_status_missing_row_no_emit(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    repo = GenerationJobsRepo(pool=None)
    out = await repo.update_status(JOB, "completed", conn=FakeConn(None))
    assert out is None
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_emits_pending_on_new_job(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    # P4 — resolve_model_name MUST NOT be called when a caller passes its own conn
    # (we're inside its tx/lock — H1). This test injects a conn, so model=None and the
    # resolver is never awaited; params still ride (cheap, no I/O).
    resolve_spy = AsyncMock(return_value="claude-haiku")
    monkeypatch.setattr(generation_jobs, "resolve_model_name", resolve_spy)
    repo = GenerationJobsRepo(pool=None)
    # A real worker job: the server stamps the canonical worker_op into input.
    _job, created = await repo.create(
        PROJ, created_by=USER, operation="draft_scene",
        input={"model_source": "user_model", "model_ref": "abc", "reasoning": "rule_based",
               "worker_op": "generate"},
        conn=FakeConn(_row(status="pending")),
    )
    assert created is True
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "composition" and kw["status"] == "pending"
    # in-tx (conn-passed) path: resolver skipped → model None, but params present
    resolve_spy.assert_not_awaited()
    assert kw["model"] is None
    assert kw["params"]["operation"] == "draft_scene"
    assert kw["params"]["reasoning"] == "rule_based"
    assert kw["params"]["model_ref"] == "abc"
    # D-JOBS-P4-RETRY-COMPOSITION — worker_op stamped → worker-drivable → retryable.
    assert kw["params"]["retryable"] is True


@pytest.mark.asyncio
async def test_create_emits_retryable_false_for_inline_op(monkeypatch):
    # An inline/streamed cowrite job: a free-form prose `operation` with NO worker_op in
    # input is NOT worker-drivable → retryable=False (its prompt was never persisted, so the
    # unified plane must not offer a server-side retry; the FE re-generate is that surface).
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    monkeypatch.setattr(generation_jobs, "resolve_model_name", AsyncMock(return_value=None))
    repo = GenerationJobsRepo(pool=None)
    await repo.create(
        PROJ, created_by=USER, operation="draft_scene",
        input={"model_source": "user_model", "model_ref": "abc"},  # no worker_op
        conn=FakeConn(_row(status="running", operation="draft_scene")),
    )
    assert spy.await_args.kwargs["params"]["retryable"] is False


@pytest.mark.asyncio
async def test_create_emits_retryable_strict_on_worker_op_not_operation(monkeypatch):
    # /review-impl MED-1: stitch/decompose key on the SERVER-set worker_op, NOT the
    # operation column — an INLINE stitch (operation='stitch_chapter' but NO worker_op,
    # only partial input) must be retryable=False, while the worker stitch (worker_op set)
    # is retryable=True. An operation-based predicate would falsely flag the inline one.
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    monkeypatch.setattr(generation_jobs, "resolve_model_name", AsyncMock(return_value=None))
    repo = GenerationJobsRepo(pool=None)
    # inline stitch — operation matches a worker-op NAME but no worker_op stamped.
    await repo.create(
        PROJ, created_by=USER, operation="stitch_chapter",
        input={"model_source": "user_model", "operation": "stitch_chapter"},
        conn=FakeConn(_row(status="running", operation="stitch_chapter")),
    )
    assert spy.await_args.kwargs["params"]["retryable"] is False
    # worker stitch — worker_op stamped → retryable.
    spy.reset_mock()
    await repo.create(
        PROJ, created_by=USER, operation="stitch_chapter",
        input={"model_source": "user_model", "worker_op": "stitch_chapter", "chapter_id": "c1"},
        conn=FakeConn(_row(status="pending", operation="stitch_chapter")),
    )
    assert spy.await_args.kwargs["params"]["retryable"] is True


@pytest.mark.asyncio
async def test_create_emits_caller_resolved_model_name_in_tx(monkeypatch):
    # D-JOBS-P4-COMPOSITION-GUARDED-MODEL — the guarded caller resolves the name OUT-OF-TX
    # and passes `model_name`; the in-tx create must emit THAT name (not None) without
    # awaiting the resolver itself (no HTTP under the in-flight lock — H1).
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    resolve_spy = AsyncMock(return_value="should-not-be-called")
    monkeypatch.setattr(generation_jobs, "resolve_model_name", resolve_spy)
    repo = GenerationJobsRepo(pool=None)
    await repo.create(
        PROJ, created_by=USER, operation="generate",
        input={"model_source": "user_model", "model_ref": "abc"},
        conn=FakeConn(_row(status="pending")), model_name="claude-haiku",
    )
    resolve_spy.assert_not_awaited()  # caller pre-resolved → no in-lock HTTP
    assert spy.await_args.kwargs["model"] == "claude-haiku"
