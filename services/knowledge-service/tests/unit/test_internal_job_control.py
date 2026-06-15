"""Internal job-control endpoint — Unified Job Control Plane P3.

Verifies the job_id-keyed wrapper: M4 owner re-check (owner-scoped get → 404),
the action→(status,pause_reason,project-mirror) mapping reusing K16.4, the
concurrent-change 409, and the unknown-action 400. The shared transition
validator (`_validate_or_409` / validate_transition) is exercised by the K16.4
public tests; here it's a no-op so we test the wrapper logic. Calls the handler
directly with mocked repos (no app lifespan)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.routers.internal_job_control import JobControlPayload, control_extraction_job

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


async def test_concurrent_change_409():
    jobs, projects = _repos(_job())
    jobs.update_status = AsyncMock(return_value=None)  # CAS lost
    with pytest.raises(HTTPException) as exc:
        await control_extraction_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), jobs, projects)
    assert exc.value.status_code == 409
    projects.set_extraction_state.assert_not_awaited()
