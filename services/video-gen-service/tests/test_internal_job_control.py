"""Internal job-control endpoint — Unified Job Control Plane P3.

`control_video_gen_job` is the `job_id`-keyed wrapper the central jobs-service
forwards to: cancel-only (400 otherwise), M4 owner re-check on the real row
(owner-scoped `get` → 404), CAS cancel via the existing `fail(status='cancelled')`
(→ 409 if no longer active), and a stateless-path 404 when the pool is down
(decouple off → no rows to control). Calls the handler directly with the module's
`get_pool`/`VideoGenJobsRepo` symbols monkeypatched (no app lifespan / DB)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import internal_job_control as ijc
from app.routers.internal_job_control import JobControlPayload, control_video_gen_job

USER = uuid4()
OTHER = uuid4()
JOB = uuid4()


def _wire(monkeypatch, *, job, won=True, pool_down=False):
    """Point the handler's get_pool/VideoGenJobsRepo at a fake repo."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=job)
    repo.fail = AsyncMock(return_value=won)

    def _get_pool():
        if pool_down:
            raise RuntimeError("video-gen pool not initialised")
        return object()

    monkeypatch.setattr(ijc, "get_pool", _get_pool)
    monkeypatch.setattr(ijc, "VideoGenJobsRepo", lambda _pool: repo)
    return repo


@pytest.mark.asyncio
async def test_cancel_owned_job_200(monkeypatch):
    repo = _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="running"))
    resp = await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert resp.status == "cancelled" and resp.job_id == JOB
    repo.get.assert_awaited_once_with(USER, JOB)      # M4 owner re-check
    repo.fail.assert_awaited_once()
    assert repo.fail.await_args.kwargs["status"] == "cancelled"


@pytest.mark.asyncio
async def test_not_owned_is_404(monkeypatch):
    repo = _wire(monkeypatch, job=None)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=OTHER))
    assert exc.value.status_code == 404
    repo.fail.assert_not_awaited()  # never mutate a job we don't own


@pytest.mark.asyncio
async def test_already_terminal_is_409(monkeypatch):
    # owner-scoped get finds it, but the CAS fail matched nothing (terminal/raced)
    _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="completed"), won=False)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_unknown_action_400(monkeypatch):
    repo = _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="running"))
    for action in ("pause", "resume", "explode"):
        with pytest.raises(HTTPException) as exc:
            await control_video_gen_job(JOB, action, JobControlPayload(owner_user_id=USER))
        assert exc.value.status_code == 400
    repo.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_stateless_pool_down_is_404(monkeypatch):
    """Decouple off → no pool, no rows: a control attempt is a clean 404, not a 500."""
    _wire(monkeypatch, job=None, pool_down=True)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert exc.value.status_code == 404
