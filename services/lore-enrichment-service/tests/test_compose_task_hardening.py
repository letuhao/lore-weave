"""Compose-task hardening (clear-defers-codeside slice 2).

Three defers, all fakes (no live stack):

  * D-M2-COMPOSE-TASK-RACE — `run_compose_task` claims the row with SELECT … FOR
    UPDATE before computing, so two workers can't double-compute + last-write-wins.
    The claim SKIPS a row another worker is actively on (a 'running' row touched
    within the idle window) but RE-DRIVES a stale 'running' row (crash recovery), and
    the legitimate idempotent 'completed' skip still holds.
  * D-M2-COMPOSE-TASK-POISON — a malformed request_json (missing key → KeyError) is a
    business fail (mark failed + ACK), NOT an infra error that poison-loops un-ACKed.
  * D-M2-COMPOSE-TASK-SWEEPER — a periodic sweep finds ('pending','running') rows idle
    past the timeout and re-drives the idempotent `run_compose_task`.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.compose import compose_task as ct


# ── a transaction-capable fake asyncpg pool/conn ──────────────────────────────


class _FakeConn:
    """Records executes/fetchrows; serves a scripted fetchrow result queue. Supports
    the `async with conn.transaction()` context the claim uses."""

    def __init__(self, *, fetchrow_results=None, fetchval_results=None):
        self._fetchrow_results = list(fetchrow_results or [])
        self._fetchval_results = list(fetchval_results or [])
        self.executes: list[tuple] = []
        self.fetchrows: list[tuple] = []
        self.fetchvals: list[tuple] = []
        self.fetches: list[tuple] = []
        self.fetch_result: list = []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Tx()

    async def fetchrow(self, sql, *params):
        self.fetchrows.append((sql, params))
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def fetch(self, sql, *params):
        self.fetches.append((sql, params))
        return self.fetch_result

    async def execute(self, sql, *params):
        self.executes.append((sql, params))

    async def fetchval(self, sql, *params):
        self.fetchvals.append((sql, params))
        if self._fetchval_results:
            return self._fetchval_results.pop(0)
        return None


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _A:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _A()


def _full_request():
    """A well-formed profile_suggest request_json (all keys the worker indexes)."""
    return {"user_id": str(uuid4()), "book_id": str(uuid4()),
            "project_id": str(uuid4()), "suggest_model_ref": str(uuid4()),
            "sample_chapter_ids": []}


def _claim_row(task_id, *, kind="profile_suggest", status="pending", request=None):
    """A row shaped like the claim's FOR-UPDATE SELECT returns."""
    return {
        "task_id": task_id,
        "kind": kind,
        "status": status,
        "request_json": request if request is not None else _full_request(),
    }


# ── D-M2-COMPOSE-TASK-RACE: claim semantics ───────────────────────────────────


def test_claim_skips_completed(monkeypatch):
    tid = uuid4()
    # The real FOR-UPDATE SELECT has `status <> 'completed'` → no lockable row; the
    # lock-free disambiguating fetchval then reads 'completed'.
    conn = _FakeConn(fetchrow_results=[None], fetchval_results=["completed"])
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "already_completed"
    # never transitioned to running, never computed.
    assert conn.executes == []


def test_claim_skips_active_running(monkeypatch):
    """A 'running' row another worker is actively on (touched within the idle window)
    is skipped — the claim's WHERE excludes it, so the FOR-UPDATE SELECT finds no row,
    and the disambiguating read sees status='running'."""
    tid = uuid4()
    conn = _FakeConn(fetchrow_results=[None], fetchval_results=["running"])
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "skipped_active"
    # no compute, no overwrite.
    assert conn.executes == []


def test_claim_redrives_stale_running(monkeypatch):
    """A stale 'running' row (a crashed worker) IS re-claimed and recomputed."""
    tid = uuid4()
    conn = _FakeConn(fetchrow_results=[_claim_row(tid, status="running")])

    computed: dict = {}

    async def _compute(pool, **kw):
        computed["ran"] = True
        return {"worldview": "recovered"}

    monkeypatch.setattr(ct, "compute_profile_suggest", _compute)
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "completed"
    assert computed.get("ran") is True
    # the claim bumped status→running (the FOR-UPDATE transition), then completed.
    assert any("status" in sql.lower() for sql, _ in conn.executes)


def test_claim_runs_pending_to_completed(monkeypatch):
    tid = uuid4()
    conn = _FakeConn(fetchrow_results=[_claim_row(tid, status="pending")])

    async def _compute(pool, **kw):
        return {"worldview": "w"}

    monkeypatch.setattr(ct, "compute_profile_suggest", _compute)
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "completed"


def test_claim_not_found(monkeypatch):
    conn = _FakeConn(fetchrow_results=[None])
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(uuid4())))
    assert out in ("not_found", "skipped_active")


# ── D-M2-COMPOSE-TASK-POISON: malformed request_json ──────────────────────────


def test_poison_keyerror_marks_failed_not_infra(monkeypatch):
    """A request_json missing a key → KeyError inside compute. It must be caught as a
    business fail (mark failed + return normally so the consumer ACKs), NOT re-raised
    as an infra error that poison-loops the message."""
    tid = uuid4()
    # request_json is missing 'suggest_model_ref' → compute_profile_suggest KeyErrors.
    bad_req = {"user_id": str(uuid4()), "book_id": str(uuid4()),
               "project_id": str(uuid4())}  # no suggest_model_ref
    conn = _FakeConn(fetchrow_results=[_claim_row(tid, status="pending", request=bad_req)])

    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "failed"  # terminal, ACK-able — NOT a raised infra error
    # the row was marked failed with an error.
    assert any("failed" in str(params) for _sql, params in conn.executes)


def test_poison_does_not_raise(monkeypatch):
    """The whole point: run_compose_task RETURNS on a malformed input (so the consumer
    ACKs) rather than propagating — assert no exception escapes."""
    tid = uuid4()
    bad_req = {"user_id": str(uuid4())}  # missing nearly everything
    conn = _FakeConn(fetchrow_results=[_claim_row(tid, status="pending", request=bad_req)])
    # must not raise
    out = asyncio.run(ct.run_compose_task(_FakePool(conn), task_id=str(tid)))
    assert out == "failed"


# ── D-M2-COMPOSE-TASK-SWEEPER ─────────────────────────────────────────────────


def test_sweep_redrives_stuck_rows(monkeypatch):
    """The sweep scans for stuck rows and re-drives the idempotent run_compose_task."""
    t1, t2 = uuid4(), uuid4()
    conn = _FakeConn()
    conn.fetch_result = [{"task_id": t1}, {"task_id": t2}]
    pool = _FakePool(conn)

    redriven: list[str] = []

    async def _run(p, *, task_id):
        redriven.append(task_id)
        return "completed"

    monkeypatch.setattr(ct, "run_compose_task", _run)
    n = asyncio.run(ct.sweep_stuck_compose_tasks(pool, timeout_s=900, batch=20))
    assert n == 2
    assert set(redriven) == {str(t1), str(t2)}
    # the scan filtered on the stuck predicate (status + idle).
    scan_sql = conn.fetches[0][0]
    assert "pending" in scan_sql and "running" in scan_sql
    assert "updated_at" in scan_sql


def test_sweep_empty_is_noop(monkeypatch):
    conn = _FakeConn()
    conn.fetch_result = []
    called: list = []

    async def _run(p, *, task_id):
        called.append(task_id)
        return "completed"

    monkeypatch.setattr(ct, "run_compose_task", _run)
    n = asyncio.run(ct.sweep_stuck_compose_tasks(_FakePool(conn), timeout_s=900, batch=20))
    assert n == 0
    assert called == []


def test_sweep_one_failure_does_not_abort_others(monkeypatch):
    """A re-drive that raises for one row is swallowed; the others still run."""
    t1, t2 = uuid4(), uuid4()
    conn = _FakeConn()
    conn.fetch_result = [{"task_id": t1}, {"task_id": t2}]

    seen: list[str] = []

    async def _run(p, *, task_id):
        seen.append(task_id)
        if task_id == str(t1):
            raise RuntimeError("transient db blip")
        return "completed"

    monkeypatch.setattr(ct, "run_compose_task", _run)
    n = asyncio.run(ct.sweep_stuck_compose_tasks(_FakePool(conn), timeout_s=900, batch=20))
    # t1 raised (not counted), t2 succeeded — the loop survived t1's failure.
    assert str(t2) in seen
    assert n == 1


async def test_sweeper_loop_runs_iterations(monkeypatch):
    """run_compose_task_sweeper ticks N times then stops (iterations harness)."""
    ticks: list = []

    async def _sweep(pool, *, timeout_s, batch):
        ticks.append((timeout_s, batch))
        return 0

    monkeypatch.setattr(ct, "sweep_stuck_compose_tasks", _sweep)
    await ct.run_compose_task_sweeper(
        object(), interval_s=0.001, timeout_s=900, batch=20, iterations=3,
    )
    assert len(ticks) == 3


async def test_sweeper_loop_disabled_when_interval_nonpositive(monkeypatch):
    called: list = []

    async def _sweep(pool, *, timeout_s, batch):
        called.append(1)
        return 0

    monkeypatch.setattr(ct, "sweep_stuck_compose_tasks", _sweep)
    await ct.run_compose_task_sweeper(object(), interval_s=0, timeout_s=900, batch=20)
    assert called == []  # interval<=0 ⇒ disabled, never sweeps
