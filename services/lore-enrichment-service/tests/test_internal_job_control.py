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


class _ComposePool:
    """Pool for the compose-task branch (project_id None → not an enrichment_job).
    acquire() yields a conn whose fetchval returns None (no enrichment_job), fetchrow
    returns the scripted compose-cancel UPDATE result, and execute/transaction are no-ops
    (emit_job_event runs for real against conn.execute). pool.fetchval returns the
    scripted disambiguation status."""

    def __init__(self, *, update_row, status):
        self._update_row = update_row
        self._status = status

    async def fetchval(self, *a, **k):       # disambiguation SELECT status (direct on pool)
        return self._status

    def acquire(self):
        outer = self

        class _Conn:
            async def fetchval(self, *a, **k):      # enrichment_job project_id lookup
                return None
            async def fetchrow(self, *a, **k):      # compose cancel UPDATE … RETURNING
                return outer._update_row
            async def execute(self, *a, **k):       # emit_job_event outbox INSERT
                return None
            def transaction(self):
                conn = self
                class _Tx:
                    async def __aenter__(self): return conn
                    async def __aexit__(self, *e): return False
                return _Tx()

        conn = _Conn()

        class _Acq:
            async def __aenter__(self): return conn
            async def __aexit__(self, *exc): return False

        return _Acq()


@pytest.mark.asyncio
async def test_cancel_compose_task_pending(monkeypatch):
    # Not an enrichment_job (project None) → compose-task branch; the UPDATE matched a
    # pending row → 200 cancelled (D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL).
    pool = _ComposePool(update_row={"kind": "profile_suggest", "user_id": USER}, status=None)
    resp = await control_enrichment_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), pool)
    assert resp.status == "cancelled" and resp.job_id == JOB


@pytest.mark.asyncio
async def test_compose_task_404_when_unknown(monkeypatch):
    # Neither an enrichment_job nor a compose task (UPDATE None + disambiguation None) → 404.
    pool = _ComposePool(update_row=None, status=None)
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), pool)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_compose_task_409_when_terminal(monkeypatch):
    # Exists + owned but already terminal (UPDATE matched nothing, status='completed') → 409.
    pool = _ComposePool(update_row=None, status="completed")
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "cancel", JobControlPayload(owner_user_id=USER), pool)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "COMPOSE_TASK_TERMINAL"


@pytest.mark.asyncio
async def test_compose_task_pause_is_400(monkeypatch):
    # pause/resume are meaningless for a one-shot compose task → 400 (it exists, wrong action).
    pool = _ComposePool(update_row=None, status="pending")
    with pytest.raises(HTTPException) as exc:
        await control_enrichment_job(JOB, "pause", JobControlPayload(owner_user_id=USER), pool)
    assert exc.value.status_code == 400


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
