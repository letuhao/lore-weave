"""Internal job-control endpoint — Unified Job Control Plane P3.

`control_enrichment_job` is the `job_id`-keyed wrapper the central jobs-service
forwards to. It is deliberately thin: validate the action (cancel/pause/resume),
re-verify ownership + recover `project_id` from the owner-scoped `enrichment_job`
row (M4 → 404), then DELEGATE to the existing C8 public handler (which owns the
state machine + atomic UPDATE+emit + resume enqueue). These prove the wrapper
logic — the delegated handler is mocked; the C8 transitions are covered by the
public-route + state-machine tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.api.internal_job_control as ijc
from app.api.internal_job_control import (
    JobControlPayload, control_enrichment_job, reconcile_jobs,
)

USER = uuid4()
JOB = uuid4()
PROJ = uuid4()


class _FakeConn:
    def __init__(self, val):
        self._val = val

    async def fetchval(self, *a, **k):
        return self._val


class _FakePool:
    """acquire() yields a conn whose fetchval returns the scripted project_id (or None)."""

    def __init__(self, val):
        self._conn = _FakeConn(val)

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acq()


@pytest.mark.asyncio
async def test_cancel_delegates_with_recovered_project_and_owner(monkeypatch):
    captured = {}

    async def fake_cancel(job_id, *, project_id, principal, pool):
        captured.update(job_id=job_id, project_id=project_id, principal=principal)
        return {"job_id": str(job_id), "status": "cancelled"}

    monkeypatch.setitem(ijc._HANDLERS, "cancel", fake_cancel)
    resp = await control_enrichment_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), _FakePool(PROJ))
    assert resp.status == "cancelled" and resp.job_id == JOB
    assert captured["project_id"] == PROJ          # recovered from the owner-scoped row
    assert captured["principal"].user_id == USER   # M4 — acts as the asserted owner


@pytest.mark.asyncio
async def test_resume_delegates(monkeypatch):
    async def fake_resume(job_id, *, project_id, principal, pool):
        return {"job_id": str(job_id), "status": "running", "resume": "enqueued"}

    monkeypatch.setitem(ijc._HANDLERS, "resume", fake_resume)
    resp = await control_enrichment_job(JOB, "resume", JobControlPayload(owner_user_id=USER), _FakePool(PROJ))
    assert resp.status == "running"


@pytest.mark.asyncio
async def test_not_owned_is_404_without_delegating(monkeypatch):
    called = {"n": 0}

    async def fake_cancel(*a, **k):
        called["n"] += 1
        return {}

    monkeypatch.setitem(ijc._HANDLERS, "cancel", fake_cancel)
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), _FakePool(None))
    assert exc.value.status_code == 404
    assert called["n"] == 0  # never mutate a job we don't own


@pytest.mark.asyncio
async def test_unknown_action_is_400_before_db():
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "explode", JobControlPayload(owner_user_id=USER), _FakePool(PROJ))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_illegal_transition_409_propagates(monkeypatch):
    async def fake_pause(job_id, *, project_id, principal, pool):
        raise HTTPException(status_code=409, detail="illegal transition")

    monkeypatch.setitem(ijc._HANDLERS, "pause", fake_pause)
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "pause", JobControlPayload(owner_user_id=USER), _FakePool(PROJ))
    assert exc.value.status_code == 409


class _FetchPool:
    """acquire-less pool whose fetch returns scripted rows (reconcile uses pool.fetch)."""

    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *a, **k):
        return self._rows


@pytest.mark.asyncio
async def test_reconcile_maps_rows_and_skips_estimating():
    from datetime import datetime, timezone
    updated = datetime(2026, 6, 15, tzinfo=timezone.utc)
    rows = [
        {"job_id": JOB, "user_id": USER, "status": "running", "error_message": None, "updated_at": updated},
        {"job_id": uuid4(), "user_id": USER, "status": "estimating", "error_message": None, "updated_at": updated},
    ]
    out = await reconcile_jobs(since=updated, pool=_FetchPool(rows))
    assert len(out["jobs"]) == 1  # the transient 'estimating' row is skipped
    p = out["jobs"][0]
    assert p["service"] == "lore_enrichment" and p["kind"] == "enrichment_job"
    assert p["status"] == "running" and p["job_id"] == str(JOB)
