"""C14a — unit tests for the reconcile-evidence-count scheduler.

Covers the sweep + loop contract:
  - advisory-lock skip / acquire / release on raise
  - per-user iteration over DISTINCT user_id
  - per-user error isolation (one bad user doesn't poison the sweep)
  - per-label counter aggregation (entities / events / facts)
  - defaults exposed
  - cancellation at startup-delay + sleep boundaries
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.jobs.reconcile_evidence_count_scheduler import (
    DEFAULT_INTERVAL_S,
    DEFAULT_STARTUP_DELAY_S,
    ReconcileSweepResult,
    run_reconcile_loop,
    sweep_reconcile_once,
)


# ── fakes ───────────────────────────────────────────────────────────


class FakeConn:
    """Minimal pool-connection stand-in. Records SQL + returns canned
    rows for the advisory-lock, user-list, unlock path."""

    def __init__(
        self,
        *,
        try_lock: bool = True,
        users: list[str] | None = None,
    ):
        self._try_lock = try_lock
        self._users = users or []
        self.executed: list[str] = []

    async def fetchval(self, sql: str, *args):
        self.executed.append(sql.strip()[:40])
        if "pg_try_advisory_lock" in sql:
            return self._try_lock
        raise AssertionError(f"unexpected fetchval: {sql}")

    async def fetch(self, sql: str, *args) -> list[dict]:
        self.executed.append(sql.strip()[:40])
        if "FROM knowledge_projects" in sql:
            return [{"user_id": uid} for uid in self._users]
        raise AssertionError(f"unexpected fetch: {sql}")

    async def execute(self, sql: str, *args) -> str:
        self.executed.append(sql.strip()[:40])
        if "pg_advisory_unlock" in sql:
            return "SELECT 1"
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def _session_factory(session=None):
    @asynccontextmanager
    async def _factory():
        yield session or AsyncMock()
    return _factory


class FakeReconcileResult:
    """Match the shape the scheduler reads from reconcile_evidence_count."""
    def __init__(self, entities=0, events=0, facts=0):
        self.entities_fixed = entities
        self.events_fixed = events
        self.facts_fixed = facts


# ── sweep_reconcile_once ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_skips_when_lock_already_held():
    conn = FakeConn(try_lock=False)
    pool = FakePool(conn)
    result = await sweep_reconcile_once(pool, _session_factory())  # type: ignore[arg-type]
    assert result.lock_skipped is True
    assert result.users_considered == 0
    # The user-list query must NOT fire when the lock wasn't acquired.
    assert not any("FROM knowledge_projects" in s for s in conn.executed)
    # Unlock must NOT fire either — lock was never held.
    assert not any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_iterates_users_and_aggregates(monkeypatch):
    conn = FakeConn(try_lock=True, users=[
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ])
    pool = FakePool(conn)

    # Patch reconcile_evidence_count in the scheduler module namespace.
    from app.jobs import reconcile_evidence_count_scheduler as sched
    call_args = []

    async def fake_reconcile(session, *, user_id, project_id, limit_per_label):
        call_args.append((user_id, project_id, limit_per_label))
        # Return different counts per user so aggregation is verifiable.
        if user_id.endswith("001"):
            return FakeReconcileResult(entities=3, events=1, facts=0)
        return FakeReconcileResult(entities=0, events=2, facts=5)

    monkeypatch.setattr(sched, "reconcile_evidence_count", fake_reconcile)

    result = await sweep_reconcile_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.lock_skipped is False
    assert result.users_considered == 2
    assert result.entities_fixed == 3
    assert result.events_fixed == 3
    assert result.facts_fixed == 5
    assert result.errored == 0
    # reconcile called per-user with project_id=None + limit_per_label=None.
    assert len(call_args) == 2
    for uid, pid, lim in call_args:
        assert pid is None
        assert lim is None
    # Unlock fired despite completion.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_isolates_per_user_errors(monkeypatch):
    """One bad user must not poison the entire sweep — error counted,
    remaining users still processed, unlock still fires."""
    conn = FakeConn(try_lock=True, users=["u1", "u2", "u3"])
    pool = FakePool(conn)

    from app.jobs import reconcile_evidence_count_scheduler as sched

    async def fake_reconcile(session, *, user_id, project_id, limit_per_label):
        if user_id == "u2":
            raise RuntimeError("neo4j timeout for u2")
        return FakeReconcileResult(entities=1, events=0, facts=0)

    monkeypatch.setattr(sched, "reconcile_evidence_count", fake_reconcile)

    result = await sweep_reconcile_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.users_considered == 3
    assert result.errored == 1
    # u1 + u3 still processed — entities=2 total.
    assert result.entities_fixed == 2


@pytest.mark.asyncio
async def test_sweep_unlocks_on_sweep_level_exception(monkeypatch):
    """Even if fetch(user_list) raises, the finally block must unlock."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    async def broken_fetch(sql, *args):
        raise RuntimeError("db blew up")
    conn.fetch = broken_fetch  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        await sweep_reconcile_once(pool, _session_factory())  # type: ignore[arg-type]

    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_includes_archived_only_users(monkeypatch):
    """/review-impl LOW#4 regression — `_LIST_USERS_SQL` must NOT
    filter on `is_archived = false` (unlike K20.3 which does).
    Archived projects still have :Entity/:Event/:Fact nodes with
    potentially drifting evidence_count; reconciling them is cheap
    (no $) and protects against un-archive resurrecting bad state."""
    from app.jobs import reconcile_evidence_count_scheduler as sched

    # Grep the SQL literal to assert the filter is absent. Source-scan
    # regression lock — catches a future PR that re-adds the filter
    # for symmetry with K20.3 without realising reconciler doesn't
    # have the $$ cost K20.3 avoids.
    sql = sched._LIST_USERS_SQL
    assert "is_archived" not in sql, (
        f"_LIST_USERS_SQL must not filter on is_archived "
        f"(reconciler is cheap, should cover archived projects too):\n{sql}"
    )
    # Still a DISTINCT-user query.
    assert "DISTINCT user_id" in sql
    assert "FROM knowledge_projects" in sql


@pytest.mark.asyncio
async def test_sweep_empty_user_list_is_noop(monkeypatch):
    conn = FakeConn(try_lock=True, users=[])
    pool = FakePool(conn)

    from app.jobs import reconcile_evidence_count_scheduler as sched
    calls = []

    async def fake_reconcile(session, *, user_id, project_id, limit_per_label):
        calls.append(user_id)
        return FakeReconcileResult()

    monkeypatch.setattr(sched, "reconcile_evidence_count", fake_reconcile)

    result = await sweep_reconcile_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.users_considered == 0
    assert calls == []
    # Unlock still fires.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


# ── defaults ───────────────────────────────────────────────────────


def test_defaults_are_sensible():
    assert DEFAULT_INTERVAL_S == 24 * 60 * 60  # daily
    assert DEFAULT_STARTUP_DELAY_S == 25 * 60   # 25 min


# ── run_reconcile_loop — cancellation ──────────────────────────────


@pytest.mark.asyncio
async def test_loop_cancellation_at_startup_delay():
    """Cancelling during startup delay exits cleanly (no sweep ran)."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    task = asyncio.create_task(
        run_reconcile_loop(
            pool,  # type: ignore[arg-type]
            _session_factory(),
            startup_delay_s=3600,  # long
            interval_s=3600,
        ),
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Sweep never ran — no lock acquire.
    assert not any("pg_try_advisory_lock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_loop_continues_after_sweep_error(monkeypatch):
    """A failed sweep must not kill the loop — error logged + sleep +
    next cycle. Counter verification lives in metrics-wiring tests;
    here we only confirm the loop survives."""
    conn = FakeConn(try_lock=True, users=["u1"])
    pool = FakePool(conn)

    from app.jobs import reconcile_evidence_count_scheduler as sched
    sweep_calls = 0

    async def fake_sweep(p, sf):
        nonlocal sweep_calls
        sweep_calls += 1
        if sweep_calls == 1:
            raise RuntimeError("first sweep blew up")
        return ReconcileSweepResult(users_considered=0)

    monkeypatch.setattr(sched, "sweep_reconcile_once", fake_sweep)

    task = asyncio.create_task(
        run_reconcile_loop(
            pool,  # type: ignore[arg-type]
            _session_factory(),
            startup_delay_s=0,
            interval_s=0,
        ),
    )
    # Let it run 2 cycles then cancel.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sweep_calls >= 2  # first raised; loop survived to next
