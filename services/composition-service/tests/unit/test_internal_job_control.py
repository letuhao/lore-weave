"""Internal job-control endpoint + race-safe cancel — Unified Job Control Plane P3.

Two surfaces:
- `GenerationJobsRepo.cancel` — the CAS that guards `status = ANY(active)` so a
  control-plane cancel can never clobber a job that completed in the TOCTOU window;
  emits the terminal event on the winning CAS only (mirrors video-gen's `fail`).
- `control_generation_job` — the `job_id`-keyed wrapper: cancel-only (400 otherwise),
  M4 owner re-check (owner-scoped get → 404), and the 409 when the row is no longer
  cancellable. Calls the handler directly with mocked repos (no app lifespan)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.repositories import generation_jobs
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.routers.internal_job_control import (
    JobControlPayload, control_generation_job, reconcile_jobs,
)

USER = uuid4()
OTHER = uuid4()
JOB = uuid4()
PROJ = uuid4()


def _row(**over):
    base = dict(
        id=JOB, user_id=USER, project_id=PROJ, outline_node_id=None,
        operation="generate", mode="auto", status="cancelled", llm_job_id=None,
        input={}, result=None, critic=None, target_chapter_id=None,
        base_revision_id=None, target_revision_id=None, cost_usd=Decimal("0"),
        idempotency_key=None, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return base


class FakeConn:
    """Minimal asyncpg-conn stand-in: fetchrow returns a scripted row (or None)."""

    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row


# ── repo.cancel — the CAS guard ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cancel_cas_won_emits_cancelled(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    repo = GenerationJobsRepo(pool=None)
    out = await repo.cancel(USER, JOB, conn=FakeConn(_row(status="cancelled")))
    assert out is not None and out.status == "cancelled"
    spy.assert_awaited_once()
    kw = spy.await_args.kwargs
    assert kw["service"] == "composition" and kw["status"] == "cancelled"
    assert kw["job_id"] == str(JOB) and kw["owner_user_id"] == str(USER)


@pytest.mark.asyncio
async def test_cancel_cas_lost_no_emit(monkeypatch):
    """The CAS matched no row (already terminal / cross-user) → None, no emit:
    the guard never clobbers a completed job."""
    spy = AsyncMock()
    monkeypatch.setattr(generation_jobs, "emit_job_event", spy)
    repo = GenerationJobsRepo(pool=None)
    out = await repo.cancel(USER, JOB, conn=FakeConn(None))
    assert out is None
    spy.assert_not_awaited()


# ── router: POST /internal/composition/jobs/{job_id}/{action} ───────────────────
def _repo(job, cancelled=True):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=job)
    repo.cancel = AsyncMock(
        return_value=(SimpleNamespace(id=JOB, status="cancelled") if cancelled and job else None)
    )
    return repo


@pytest.mark.asyncio
async def test_cancel_owned_job_200():
    repo = _repo(SimpleNamespace(id=JOB, status="running"))
    resp = await control_generation_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), repo)
    assert resp.status == "cancelled" and resp.job_id == JOB
    repo.get.assert_awaited_once_with(USER, JOB)       # M4 owner-scoped re-check
    repo.cancel.assert_awaited_once_with(USER, JOB)


@pytest.mark.asyncio
async def test_not_owned_is_404():
    repo = _repo(None)
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "cancel", JobControlPayload(owner_user_id=OTHER), repo)
    assert exc.value.status_code == 404
    repo.cancel.assert_not_awaited()  # never mutate a job we don't own


@pytest.mark.asyncio
async def test_already_terminal_is_409():
    # owner-scoped get finds it, but the CAS cancel matched nothing (terminal/raced)
    repo = _repo(SimpleNamespace(id=JOB, status="completed"), cancelled=False)
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unknown_action_400():
    repo = _repo(SimpleNamespace(id=JOB, status="running"))
    for action in ("pause", "resume", "explode"):
        with pytest.raises(HTTPException) as exc:
            await control_generation_job(JOB, action, JobControlPayload(owner_user_id=USER), repo)
        assert exc.value.status_code == 400
    repo.get.assert_not_awaited()


# ── reconcile source: GET /internal/composition/jobs?since= ─────────────────────
@pytest.mark.asyncio
async def test_reconcile_jobs_maps_to_canonical_payload():
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    job = SimpleNamespace(id=JOB, user_id=USER, operation="generate", status="running", updated_at=updated)
    repo = AsyncMock()
    repo.list_since = AsyncMock(return_value=[job])
    out = await reconcile_jobs(since=updated, jobs=repo)
    assert len(out["jobs"]) == 1
    p = out["jobs"][0]
    assert p["service"] == "composition" and p["kind"] == "generate" and p["status"] == "running"
    assert p["job_id"] == str(JOB) and p["owner_user_id"] == str(USER)
    assert p["occurred_at"] == updated.isoformat()
