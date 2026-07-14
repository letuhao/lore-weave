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

from app.db.repositories import (
    ChapterJobInFlightError, ReferenceViolationError, generation_jobs,
)
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.routers import internal_job_control as ijc
from app.routers.internal_job_control import (
    JobControlPayload, control_generation_job, reconcile_jobs,
)

USER = uuid4()
OTHER = uuid4()
JOB = uuid4()
NEW = uuid4()
NODE = uuid4()
CHAP = uuid4()
PROJ = uuid4()
BOOK = uuid4()


def _row(**over):
    base = dict(
        id=JOB, created_by=USER, project_id=PROJ, book_id=BOOK, outline_node_id=None,
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
    out = await repo.cancel(JOB, conn=FakeConn(_row(status="cancelled")))
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
    out = await repo.cancel(JOB, conn=FakeConn(None))
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
    repo = _repo(SimpleNamespace(id=JOB, status="running", created_by=USER))
    resp = await control_generation_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), repo)
    assert resp.status == "cancelled" and resp.job_id == JOB
    # 25 re-key: get()/cancel() are BARE-ID; the M4 owner re-check is an explicit
    # `job.created_by == payload.owner_user_id` assert in the handler, not a scoped read.
    repo.get.assert_awaited_once_with(JOB)
    repo.cancel.assert_awaited_once_with(JOB)


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
    repo = _repo(SimpleNamespace(id=JOB, status="completed", created_by=USER), cancelled=False)
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


# ── router: retry (D-JOBS-P4-RETRY-COMPOSITION) ─────────────────────────────────
def _failed_job(**over):
    base = dict(
        id=JOB, created_by=USER, project_id=PROJ, outline_node_id=NODE,
        operation="draft_scene", mode="auto", status="failed",
        # worker-drivable: input carries the canonical worker_op + the resolved context.
        input={"worker_op": "generate", "packed_prompt": "…", "model_source": "user_model",
               "model_ref": str(uuid4())},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _retry_repo(job, *, create_ret=None, guarded_ret=None, guarded_exc=None):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=job)
    repo.create = AsyncMock(return_value=create_ret or (SimpleNamespace(id=NEW, status="pending"), True))
    if guarded_exc is not None:
        repo.create_chapter_job_guarded = AsyncMock(side_effect=guarded_exc)
    else:
        repo.create_chapter_job_guarded = AsyncMock(
            return_value=guarded_ret or (SimpleNamespace(id=NEW, status="pending"), True))
    return repo


@pytest.fixture
def _retry_env(monkeypatch):
    """Worker enabled + stub enqueue/model-name so the retry core is unit-isolated."""
    monkeypatch.setattr(ijc, "settings", SimpleNamespace(
        composition_worker_enabled=True, redis_url="redis://x", chapter_inflight_stale_secs=1800))
    enq = AsyncMock(return_value=True)
    monkeypatch.setattr(ijc, "enqueue_job", enq)
    monkeypatch.setattr(ijc, "resolve_model_name", AsyncMock(return_value="some-model"))
    return enq


@pytest.mark.asyncio
async def test_retry_worker_drivable_resubmits_new_job(_retry_env):
    repo = _retry_repo(_failed_job())
    resp = await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert resp.job_id == NEW and resp.status == "pending"
    # re-submitted as a NEW job from the failed row; idempotency_key NOT copied (else ON
    # CONFLICT would replay→return the same failed row).
    repo.create.assert_awaited_once()
    kw = repo.create.await_args.kwargs
    assert kw["idempotency_key"] is None and kw["status"] == "pending"
    assert kw["operation"] == "draft_scene" and kw["outline_node_id"] == NODE
    assert kw["input"]["worker_op"] == "generate"
    _retry_env.assert_awaited_once()  # enqueued


@pytest.mark.asyncio
async def test_retry_not_owned_404(_retry_env):
    repo = _retry_repo(None)
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=OTHER), repo)
    assert exc.value.status_code == 404
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_not_failed_409(_retry_env):
    repo = _retry_repo(_failed_job(status="completed"))
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "JOBS_STATUS_NOT_FAILED"
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_inline_streamed_not_retryable_409(_retry_env):
    # inline cowrite job: no worker_op in input → not worker-drivable → 409, not re-submitted.
    repo = _retry_repo(_failed_job(input={"model_source": "user_model"}))
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "JOBS_NOT_RETRYABLE"
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_worker_disabled_409(monkeypatch):
    monkeypatch.setattr(ijc, "settings", SimpleNamespace(
        composition_worker_enabled=False, redis_url="redis://x", chapter_inflight_stale_secs=1800))
    monkeypatch.setattr(ijc, "enqueue_job", AsyncMock())
    repo = _retry_repo(_failed_job())
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "JOBS_WORKER_DISABLED"
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_node_deleted_409(_retry_env):
    # the failed job's outline node was deleted since → create re-validates ownership and
    # raises ReferenceViolationError → 409 (not a 500).
    repo = _retry_repo(_failed_job())
    repo.create = AsyncMock(side_effect=ReferenceViolationError("node gone"))
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "JOBS_NOT_RETRYABLE"


@pytest.mark.asyncio
async def test_retry_chapter_uses_guarded_create(_retry_env):
    # chapter_generate writes the book draft → must go through the in-flight guard, not plain create.
    job = _failed_job(operation="draft_chapter",
                      input={"worker_op": "chapter_generate", "chapter_id": str(CHAP),
                             "packed_prompt": "…", "model_source": "user_model"})
    repo = _retry_repo(job)
    resp = await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert resp.job_id == NEW
    repo.create_chapter_job_guarded.assert_awaited_once()
    repo.create.assert_not_awaited()  # NOT the plain path
    kw = repo.create_chapter_job_guarded.await_args.kwargs
    assert kw["idempotency_key"] is None and kw["status"] == "pending"


@pytest.mark.asyncio
async def test_retry_stitch_uses_guarded_create(_retry_env):
    # /review-impl MED-2: stitch_chapter also writes the chapter draft → must go through
    # the in-flight guard on retry too, not plain create.
    job = _failed_job(operation="stitch_chapter",
                      input={"worker_op": "stitch_chapter", "chapter_id": str(CHAP),
                             "chapter_intent": "…", "max_out": 2048, "model_source": "user_model"})
    repo = _retry_repo(job)
    resp = await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert resp.job_id == NEW
    repo.create_chapter_job_guarded.assert_awaited_once()
    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_chapter_in_flight_409(_retry_env):
    job = _failed_job(operation="draft_chapter",
                      input={"worker_op": "chapter_generate", "chapter_id": str(CHAP),
                             "model_source": "user_model"})
    repo = _retry_repo(job, guarded_exc=ChapterJobInFlightError("active-123"))
    with pytest.raises(HTTPException) as exc:
        await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "CHAPTER_JOB_IN_FLIGHT"
    assert exc.value.detail["active_job_id"] == "active-123"


# ── reconcile source: GET /internal/composition/jobs?since= ─────────────────────
@pytest.mark.asyncio
async def test_reconcile_jobs_maps_to_canonical_payload():
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    job = SimpleNamespace(id=JOB, created_by=USER, operation="generate", status="running", updated_at=updated)
    repo = AsyncMock()
    repo.list_since = AsyncMock(return_value=[job])
    out = await reconcile_jobs(since=updated, jobs=repo)
    assert len(out["jobs"]) == 1
    p = out["jobs"][0]
    assert p["service"] == "composition" and p["kind"] == "generate" and p["status"] == "running"
    assert p["job_id"] == str(JOB) and p["owner_user_id"] == str(USER)
    assert p["occurred_at"] == updated.isoformat()


# ── BE-7c — retrying an UNBOUND (Work-less) job ──────────────────────────────


@pytest.mark.asyncio
async def test_retry_of_an_unbound_job_uses_create_unbound(_retry_env):
    """BE-7c. `mine_motifs` IS in SUPPORTED_OPERATIONS and its input carries `worker_op`,
    so `is_worker_drivable` marks it retryable=True and the jobs-service Retry button is
    LIVE for it. But a mine job is Work-LESS (project_id IS NULL), and the plain `create()`
    derives book_id from composition_work — so retry would raise ReferenceViolationError and
    409 with a LIE ("the job's outline node no longer exists"). The retry must route to the
    same Work-less writer the confirm path uses."""
    job = _failed_job(operation="mine_motifs", project_id=None, book_id=None,
                      outline_node_id=None,
                      input={"worker_op": "mine_motifs", "scope": "corpus"})
    repo = _retry_repo(job)
    repo.create_unbound = AsyncMock(return_value=SimpleNamespace(id=NEW, status="pending"))

    resp = await control_generation_job(JOB, "retry", JobControlPayload(owner_user_id=USER), repo)

    assert resp.job_id == NEW and resp.status == "pending"
    repo.create_unbound.assert_awaited_once()
    repo.create.assert_not_awaited()  # the Work-bound writer would have raised
    kw = repo.create_unbound.await_args.kwargs
    assert kw["operation"] == "mine_motifs" and kw["created_by"] == USER
    assert kw["input"]["worker_op"] == "mine_motifs"
    # No "None" string on the worker stream for a job that has no project.
    assert _retry_env.await_args.kwargs["project_id"] == ""
