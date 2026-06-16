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


def _row(**over):
    base = dict(
        id=JOB, user_id=USER, project_id=PROJ, outline_node_id=None,
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
    await repo.update_status(USER, JOB, "completed", conn=FakeConn(_row(status="completed")))
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
        USER, JOB, "failed", result={"error": "boom"},
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
    out = await repo.update_status(USER, JOB, "completed", conn=FakeConn(None))
    assert out is None
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_emits_pending_on_new_job(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    # P4 — create resolves the model NAME (HTTP); stub it (best-effort).
    monkeypatch.setattr(
        generation_jobs, "resolve_model_name", AsyncMock(return_value="claude-haiku"),
    )
    repo = GenerationJobsRepo(pool=None)
    _job, created = await repo.create(
        USER, PROJ, operation="generate",
        input={"model_source": "user_model", "model_ref": "abc", "reasoning": "rule_based"},
        conn=FakeConn(_row(status="pending")),
    )
    assert created is True
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "composition" and kw["status"] == "pending"
    # P4 — create carries the resolved model + a whitelisted params dict
    assert kw["model"] == "claude-haiku"
    assert kw["params"]["operation"] == "generate"
    assert kw["params"]["reasoning"] == "rule_based"
