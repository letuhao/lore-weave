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
from app.routers.internal_job_control import (
    JobControlPayload, control_video_gen_job, reconcile_jobs,
)

USER = uuid4()
OTHER = uuid4()
JOB = uuid4()
PROV = uuid4()  # the provider-registry job_id stored on the row


def _wire(monkeypatch, *, job, won=True, pool_down=False, abort_raises=None):
    """Point the handler's get_pool/VideoGenJobsRepo at a fake repo, and stub the
    provider-registry Client used for D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT. Returns
    (repo, client) so tests can assert the abort call."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=job)
    repo.fail = AsyncMock(return_value=won)

    def _get_pool():
        if pool_down:
            raise RuntimeError("video-gen pool not initialised")
        return object()

    monkeypatch.setattr(ijc, "get_pool", _get_pool)
    monkeypatch.setattr(ijc, "VideoGenJobsRepo", lambda _pool: repo)

    client = AsyncMock()
    client.cancel_job = AsyncMock(side_effect=abort_raises)
    client.aclose = AsyncMock()
    monkeypatch.setattr(ijc, "Client", lambda **kw: client)
    return repo, client


# ── D-JOBS-P4-RETRY-VIDEOGEN — re-submit a failed job from its stored request_json ──
NEW = uuid4()
_REQ = {"prompt": "a cat", "model_source": "user_model", "model_ref": str(uuid4()),
        "duration_seconds": 5, "aspect_ratio": "16:9", "style": None}


def _patch_submit(monkeypatch, *, job_id=NEW, status="pending"):
    """Stub the lazy-imported `_submit_decoupled` on its SOURCE module (the retry path does
    `from .generate import _submit_decoupled` at call time → reads the patched attr)."""
    from types import SimpleNamespace as _SN
    sub = AsyncMock(return_value=_SN(job_id=str(job_id), status=status))
    monkeypatch.setattr("app.routers.generate._submit_decoupled", sub)
    return sub


@pytest.mark.asyncio
async def test_cancel_owned_job_200(monkeypatch):
    repo, client = _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="running", provider_job_id=PROV))
    resp = await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert resp.status == "cancelled" and resp.job_id == JOB
    repo.get.assert_awaited_once_with(USER, JOB)      # M4 owner re-check
    repo.fail.assert_awaited_once()
    assert repo.fail.await_args.kwargs["status"] == "cancelled"
    # D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT: after the local CAS wins, abort the provider job.
    client.cancel_job.assert_awaited_once()
    assert client.cancel_job.await_args.args[0] == PROV
    assert client.cancel_job.await_args.kwargs["user_id"] == str(USER)


@pytest.mark.asyncio
async def test_cancel_no_provider_job_id_skips_abort(monkeypatch):
    # A row with no provider_job_id (submit not yet acked) → local cancel only, no abort call.
    repo, client = _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="pending", provider_job_id=None))
    resp = await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert resp.status == "cancelled"
    client.cancel_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_provider_abort_failure_still_cancels(monkeypatch):
    # The local row is canonical: a best-effort provider-abort failure must NOT fail the cancel.
    from loreweave_llm import LLMJobNotFound
    repo, client = _wire(
        monkeypatch, job=SimpleNamespace(id=JOB, status="running", provider_job_id=PROV),
        abort_raises=LLMJobNotFound("gone", status_code=404))
    resp = await control_video_gen_job(JOB, "cancel", JobControlPayload(owner_user_id=USER))
    assert resp.status == "cancelled"  # swallowed
    client.cancel_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_not_owned_is_404(monkeypatch):
    repo, _ = _wire(monkeypatch, job=None)
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
    repo, _ = _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="running", provider_job_id=PROV))
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


@pytest.mark.asyncio
async def test_retry_failed_resubmits_fresh_job(monkeypatch):
    _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="failed", request_json=_REQ, provider_job_id=PROV))
    sub = _patch_submit(monkeypatch)
    resp = await control_video_gen_job(JOB, "retry", JobControlPayload(owner_user_id=USER))
    assert resp.job_id == NEW and resp.status == "pending"
    sub.assert_awaited_once()
    # reconstructed GenerateRequest carries the failed row's prompt + model_ref
    body = sub.await_args.args[0]
    assert body.prompt == "a cat" and body.model_ref == _REQ["model_ref"]


@pytest.mark.asyncio
async def test_retry_not_owned_404(monkeypatch):
    _wire(monkeypatch, job=None)
    sub = _patch_submit(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "retry", JobControlPayload(owner_user_id=OTHER))
    assert exc.value.status_code == 404
    sub.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_non_failed_409(monkeypatch):
    _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="running", request_json=_REQ, provider_job_id=PROV))
    sub = _patch_submit(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "retry", JobControlPayload(owner_user_id=USER))
    assert exc.value.status_code == 409
    sub.assert_not_awaited()  # never re-submits a non-failed job


@pytest.mark.asyncio
async def test_retry_missing_params_409(monkeypatch):
    # a pre-emit row with an empty request_json can't be reconstructed → graceful 409, not 500
    _wire(monkeypatch, job=SimpleNamespace(id=JOB, status="failed", request_json={}, provider_job_id=PROV))
    sub = _patch_submit(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "retry", JobControlPayload(owner_user_id=USER))
    assert exc.value.status_code == 409
    sub.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_stateless_pool_down_404(monkeypatch):
    _wire(monkeypatch, job=None, pool_down=True)
    sub = _patch_submit(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await control_video_gen_job(JOB, "retry", JobControlPayload(owner_user_id=USER))
    assert exc.value.status_code == 404
    sub.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_jobs_maps_rows(monkeypatch):
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    job = SimpleNamespace(id=JOB, user_id=USER, status="running", updated_at=updated)
    repo = AsyncMock()
    repo.list_since = AsyncMock(return_value=[job])
    monkeypatch.setattr(ijc, "get_pool", lambda: object())
    monkeypatch.setattr(ijc, "VideoGenJobsRepo", lambda _pool: repo)
    out = await reconcile_jobs(since=updated)
    p = out["jobs"][0]
    assert p["service"] == "video_gen" and p["kind"] == "video_gen" and p["status"] == "running"
    assert p["job_id"] == str(JOB) and p["occurred_at"] == updated.isoformat()


@pytest.mark.asyncio
async def test_reconcile_stateless_pool_down_empty(monkeypatch):
    def _down():
        raise RuntimeError("video-gen pool not initialised")
    monkeypatch.setattr(ijc, "get_pool", _down)
    from datetime import datetime, timezone
    out = await reconcile_jobs(since=datetime(2026, 6, 15, tzinfo=timezone.utc))
    assert out == {"jobs": []}
