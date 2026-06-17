"""Internal job-control endpoint — Unified Job Control Plane P3.

Verifies the job_id-keyed wrapper: M4 owner re-check (owner-scoped get → 404),
the action→(status,pause_reason,project-mirror) mapping reusing K16.4, the
concurrent-change 409, and the unknown-action 400. The shared transition
validator (`_validate_or_409` / validate_transition) is exercised by the K16.4
public tests; here it's a no-op so we test the wrapper logic. Calls the handler
directly with mocked repos (no app lifespan)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

import app.routers.internal_job_control as ijc
from app.routers.internal_job_control import (
    JobControlPayload, control_extraction_job, reconcile_jobs,
)

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
JOB = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PROJ = UUID("99999999-9999-9999-9999-999999999999")


def _job(status="running"):
    return SimpleNamespace(job_id=JOB, project_id=PROJ, status=status)


def _repos(job, updated_status="cancelled"):
    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=job)
    jobs.update_status = AsyncMock(
        return_value=(SimpleNamespace(job_id=JOB, status=updated_status) if job else None)
    )
    projects = AsyncMock()
    projects.set_extraction_state = AsyncMock()
    return jobs, projects


@pytest.fixture(autouse=True)
def _noop_validate(monkeypatch):
    monkeypatch.setattr("app.routers.internal_job_control._validate_or_409", lambda *a, **k: None)


def _patch_wiki(monkeypatch, rows=None):
    """Patch the reconcile endpoint's inline ``WikiGenJobsRepo(get_knowledge_pool())``
    so the wiki-gen UNION yields ``rows`` (default: none) without a live pool."""
    repo = MagicMock()
    repo.list_since = AsyncMock(return_value=list(rows or []))
    monkeypatch.setattr(ijc, "WikiGenJobsRepo", MagicMock(return_value=repo))
    monkeypatch.setattr(ijc, "get_knowledge_pool", MagicMock(return_value=MagicMock()))
    return repo


@pytest.fixture(autouse=True)
def _empty_wiki(monkeypatch):
    """Default: the wiki-gen reconcile source is empty (the extraction-only tests
    don't care about it). A wiki-specific test re-patches with rows."""
    _patch_wiki(monkeypatch)


async def test_cancel_owned_job_mirrors_disabled():
    jobs, projects = _repos(_job(), "cancelled")
    resp = await control_extraction_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert resp.status == "cancelled"
    jobs.get.assert_awaited_once_with(USER, JOB)          # M4 owner-scoped re-check
    jobs.update_status.assert_awaited_once_with(USER, JOB, "cancelled")
    _u, kw = projects.set_extraction_state.await_args.args, projects.set_extraction_state.await_args.kwargs
    assert kw["extraction_status"] == "disabled" and kw["extraction_enabled"] is False


async def test_pause_uses_pause_reason_and_mirrors_paused():
    jobs, projects = _repos(_job(), "paused")
    resp = await control_extraction_job(JOB, "pause", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert resp.status == "paused"
    assert projects.set_extraction_state.await_args.kwargs["extraction_status"] == "paused"


async def test_resume_mirrors_building():
    jobs, projects = _repos(_job("paused"), "running")
    await control_extraction_job(JOB, "resume", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert projects.set_extraction_state.await_args.kwargs["extraction_status"] == "building"


async def test_not_owned_is_404():
    jobs, projects = _repos(None)
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(JOB, "cancel", JobControlPayload(owner_user_id=OTHER), jobs, projects)
    assert exc.value.status_code == 404
    jobs.update_status.assert_not_awaited()  # never mutate a job we don't own


async def test_unknown_action_400():
    jobs, projects = _repos(_job())
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(JOB, "explode", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert exc.value.status_code == 400
    jobs.get.assert_not_awaited()


# ── D-JOBS-SECONDARY-KIND-CONTROL — wiki_gen cancel|resume dispatch ──────────────

def _wiki_repo(monkeypatch, *, job, cancel=True, resume=True):
    """Patch the wiki dispatch's inline WikiGenJobsRepo(get_knowledge_pool())."""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=job)
    repo.cancel = AsyncMock(return_value=cancel)
    repo.resume = AsyncMock(return_value=resume)
    monkeypatch.setattr(ijc, "WikiGenJobsRepo", MagicMock(return_value=repo))
    monkeypatch.setattr(ijc, "get_knowledge_pool", MagicMock(return_value=MagicMock()))
    return repo


def _wiki_job(status="pending", user=USER):
    return SimpleNamespace(job_id=JOB, user_id=user, status=status)


async def test_wiki_gen_cancel_owned_pending(monkeypatch):
    repo = _wiki_repo(monkeypatch, job=_wiki_job("pending"), cancel=True)
    resp = await control_extraction_job(
        JOB, "cancel", JobControlPayload(owner_user_id=USER, kind="wiki_gen"), AsyncMock(), AsyncMock())
    assert resp.status == "cancelled"
    repo.cancel.assert_awaited_once_with(JOB)


async def test_wiki_gen_resume_owned_paused(monkeypatch):
    repo = _wiki_repo(monkeypatch, job=_wiki_job("paused"), resume=True)
    resp = await control_extraction_job(
        JOB, "resume", JobControlPayload(owner_user_id=USER, kind="wiki_gen"), AsyncMock(), AsyncMock())
    assert resp.status == "pending"
    repo.resume.assert_awaited_once_with(JOB)


async def test_wiki_gen_not_owned_404(monkeypatch):
    repo = _wiki_repo(monkeypatch, job=_wiki_job("pending", user=OTHER))
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(
            JOB, "cancel", JobControlPayload(owner_user_id=USER, kind="wiki_gen"), AsyncMock(), AsyncMock())
    assert exc.value.status_code == 404
    repo.cancel.assert_not_awaited()  # ownership checked before any mutation


async def test_wiki_gen_cancel_running_409(monkeypatch):
    # a running wiki job isn't cancellable → repo.cancel guards to 0 rows → False → 409
    repo = _wiki_repo(monkeypatch, job=_wiki_job("running"), cancel=False)
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(
            JOB, "cancel", JobControlPayload(owner_user_id=USER, kind="wiki_gen"), AsyncMock(), AsyncMock())
    assert exc.value.status_code == 409


async def test_wiki_gen_bad_action_400(monkeypatch):
    repo = _wiki_repo(monkeypatch, job=_wiki_job("running"))
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(
            JOB, "pause", JobControlPayload(owner_user_id=USER, kind="wiki_gen"), AsyncMock(), AsyncMock())
    assert exc.value.status_code == 400
    repo.get.assert_not_awaited()  # bad action rejected before any lookup


async def test_concurrent_change_409():
    jobs, projects = _repos(_job())
    jobs.update_status = AsyncMock(return_value=None)  # CAS lost
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert exc.value.status_code == 409
    projects.set_extraction_state.assert_not_awaited()


async def test_reconcile_jobs_maps_complete_to_completed():
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    row = SimpleNamespace(
        job_id=JOB, user_id=USER, status="complete", items_processed=3, items_total=5,
        error_message=None, updated_at=updated, cost_spent_usd=2.74,
    )
    repo = AsyncMock()
    repo.list_since = AsyncMock(return_value=[row])
    out = await reconcile_jobs(since=updated, limit=1000, jobs_repo=repo)
    p = out["jobs"][0]
    assert p["service"] == "knowledge" and p["kind"] == "extraction"
    assert p["status"] == "completed"  # 'complete' → canonical 'completed'
    assert p["progress"] == {"done": 3, "total": 5}
    assert p["cost_usd"] == 2.74  # P4 — reconcile carries cumulative cost (backstop)
    assert p["occurred_at"] == updated.isoformat()


async def test_reconcile_skips_noncanonical_summarizing():
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    good = SimpleNamespace(job_id=JOB, user_id=USER, status="running", items_processed=0,
                           items_total=0, error_message=None, updated_at=updated,
                           cost_spent_usd=0)
    # 'summarizing' has no canonical JobStatus → must be skipped, not shipped unparseable.
    summ = SimpleNamespace(job_id=JOB, user_id=USER, status="summarizing", items_processed=0,
                           items_total=0, error_message=None, updated_at=updated,
                           cost_spent_usd=0)
    repo = AsyncMock()
    repo.list_since = AsyncMock(return_value=[good, summ])
    out = await reconcile_jobs(since=updated, limit=1000, jobs_repo=repo)
    assert len(out["jobs"]) == 1 and out["jobs"][0]["status"] == "running"


async def test_reconcile_unions_wiki_gen_and_merges_oldest_first(monkeypatch):
    # D-JOBS-WIKI-GEN-UNWIRED: the knowledge reconcile UNIONs extraction + wiki_gen,
    # both federating to service='knowledge', kept apart by `kind`. The two families
    # are merged oldest-first by occurred_at.
    from datetime import datetime, timezone
    t_ext = datetime(2026, 6, 16, tzinfo=timezone.utc)   # newer
    t_wiki = datetime(2026, 6, 15, tzinfo=timezone.utc)  # older
    ext_row = SimpleNamespace(job_id=JOB, user_id=USER, status="running", items_processed=1,
                              items_total=4, error_message=None, updated_at=t_ext, cost_spent_usd=0)
    wiki_row = {
        "job_id": UUID("11111111-1111-1111-1111-111111111111"), "user_id": USER,
        "status": "completed",       # list_since already mapped complete→completed
        "native_status": "complete", "cost_spent_usd": 1.5, "error_message": None,
        "updated_at": t_wiki,
    }
    _patch_wiki(monkeypatch, rows=[wiki_row])
    ext_repo = AsyncMock()
    ext_repo.list_since = AsyncMock(return_value=[ext_row])
    out = await reconcile_jobs(since=t_wiki, limit=1000, jobs_repo=ext_repo)
    jobs = out["jobs"]
    assert [j["kind"] for j in jobs] == ["wiki_gen", "extraction"]  # oldest-first merge
    w = jobs[0]
    assert w["service"] == "knowledge" and w["status"] == "completed"
    assert w["cost_usd"] == 1.5 and w["progress"] is None and w["error"] is None


async def test_reconcile_merge_caps_at_limit_keeping_oldest(monkeypatch):
    # The merged list is capped at `limit` oldest-first — the newest row is DROPPED
    # (re-fetched next sweep since `since` is inclusive, so no loss). Proves the soft cap.
    from datetime import datetime, timezone
    t1 = datetime(2026, 6, 15, tzinfo=timezone.utc)  # oldest (extraction)
    t2 = datetime(2026, 6, 16, tzinfo=timezone.utc)  # newest (wiki) — must be dropped at limit=1
    ext_row = SimpleNamespace(job_id=JOB, user_id=USER, status="running", items_processed=0,
                              items_total=0, error_message=None, updated_at=t1, cost_spent_usd=0)
    wiki_row = {
        "job_id": UUID("33333333-3333-3333-3333-333333333333"), "user_id": USER,
        "status": "completed", "native_status": "complete", "cost_spent_usd": 0.0,
        "error_message": None, "updated_at": t2,
    }
    _patch_wiki(monkeypatch, rows=[wiki_row])
    ext_repo = AsyncMock()
    ext_repo.list_since = AsyncMock(return_value=[ext_row])
    out = await reconcile_jobs(since=t1, limit=1, jobs_repo=ext_repo)
    assert len(out["jobs"]) == 1
    assert out["jobs"][0]["kind"] == "extraction"  # oldest kept; newer wiki row dropped
    assert out["jobs"][0]["occurred_at"] == t1.isoformat()


async def test_reconcile_wiki_gen_failed_carries_error(monkeypatch):
    from datetime import datetime, timezone
    t = datetime(2026, 6, 15, tzinfo=timezone.utc)
    wiki_row = {
        "job_id": UUID("22222222-2222-2222-2222-222222222222"), "user_id": USER,
        "status": "failed", "native_status": "failed", "cost_spent_usd": 0.0,
        "error_message": "budget exceeded", "updated_at": t,
    }
    _patch_wiki(monkeypatch, rows=[wiki_row])
    ext_repo = AsyncMock()
    ext_repo.list_since = AsyncMock(return_value=[])
    out = await reconcile_jobs(since=t, limit=1000, jobs_repo=ext_repo)
    p = out["jobs"][0]
    assert p["kind"] == "wiki_gen" and p["status"] == "failed"
    assert p["error"] == {"code": "wiki_gen_failed", "message": "budget exceeded"}
