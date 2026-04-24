"""C14a — unit tests for the quarantine-cleanup scheduler.

Covers:
  - advisory-lock skip / acquire / release on raise
  - global sweep (user_id=None) delegates to run_quarantine_cleanup
  - sweep-level exception counted + errored flag set + unlock fires
  - defaults exposed
  - cancellation at startup-delay boundary
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.jobs.quarantine_cleanup_scheduler import (
    DEFAULT_INTERVAL_S,
    DEFAULT_LIMIT_PER_SWEEP,
    DEFAULT_MAX_DRAIN_ITERATIONS,
    DEFAULT_STARTUP_DELAY_S,
    QuarantineSweepResult,
    run_quarantine_loop,
    sweep_quarantine_once,
)


class FakeConn:
    def __init__(self, *, try_lock: bool = True):
        self._try_lock = try_lock
        self.executed: list[str] = []

    async def fetchval(self, sql: str, *args):
        self.executed.append(sql.strip()[:40])
        if "pg_try_advisory_lock" in sql:
            return self._try_lock
        raise AssertionError(f"unexpected fetchval: {sql}")

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


# ── sweep_quarantine_once ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_skips_when_lock_already_held(monkeypatch):
    conn = FakeConn(try_lock=False)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    called = []

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        called.append(user_id)
        return 0

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.lock_skipped is True
    assert result.invalidated == 0
    assert called == []  # cleanup must NOT be invoked
    assert not any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_runs_global_cleanup_and_returns_count(monkeypatch):
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    call_args = {}

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        call_args["user_id"] = user_id
        call_args["ttl_hours"] = ttl_hours
        call_args["limit"] = limit
        return 42

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.lock_skipped is False
    assert result.errored is False
    assert result.invalidated == 42
    # Global sweep — user_id must be None.
    assert call_args["user_id"] is None
    # Limit defaults propagate.
    assert call_args["limit"] == DEFAULT_LIMIT_PER_SWEEP
    # Unlock fires.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_custom_ttl_and_limit_propagate(monkeypatch):
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    call_args = {}

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        call_args.update({"ttl_hours": ttl_hours, "limit": limit})
        return 7

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(
        pool,  # type: ignore[arg-type]
        _session_factory(),
        ttl_hours=48,
        limit=500,
    )

    assert call_args["ttl_hours"] == 48
    assert call_args["limit"] == 500
    assert result.invalidated == 7


@pytest.mark.asyncio
async def test_sweep_exception_marks_errored_and_unlocks(monkeypatch):
    """Exception from run_quarantine_cleanup sets errored=True + unlocks
    without re-raising (loop must survive)."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched

    async def fake_cleanup(session, **kwargs):
        raise RuntimeError("neo4j connection refused")

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.errored is True
    assert result.invalidated == 0
    assert any("pg_advisory_unlock" in s for s in conn.executed)


# ── defaults ───────────────────────────────────────────────────────


def test_defaults_are_sensible():
    assert DEFAULT_INTERVAL_S == 12 * 60 * 60  # 12h
    assert DEFAULT_STARTUP_DELAY_S == 30 * 60  # 30 min
    assert DEFAULT_LIMIT_PER_SWEEP == 1000
    assert DEFAULT_MAX_DRAIN_ITERATIONS == 10


# ── /review-impl MED#1 — inner-loop drain ──────────────────────────


@pytest.mark.asyncio
async def test_sweep_drains_burst_across_multiple_iterations(monkeypatch):
    """When backlog > limit, sweep_quarantine_once must call
    run_quarantine_cleanup repeatedly until a call returns < limit
    (natural drain terminator). Prevents long backlogs requiring
    multiple 12h-spaced sweeps."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    # Simulate: 1st call returns full limit (1000), 2nd returns full
    # limit, 3rd returns 150 (< 1000) — backlog drained.
    drain_sequence = [1000, 1000, 150]
    call_count = 0

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        nonlocal call_count
        assert user_id is None  # global sweep
        ret = drain_sequence[call_count]
        call_count += 1
        return ret

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(pool, _session_factory())  # type: ignore[arg-type]

    assert result.iterations == 3
    assert result.invalidated == 2150  # 1000 + 1000 + 150
    assert result.errored is False
    # Helper called exactly 3 times (not 4 — natural terminator fires).
    assert call_count == 3


@pytest.mark.asyncio
async def test_sweep_drain_caps_at_max_iterations(monkeypatch):
    """Safety net: if helper keeps returning full limit (pathological
    BE regression or truly unbounded backlog), the drain loop must
    stop at DEFAULT_MAX_DRAIN_ITERATIONS rather than running forever."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    call_count = 0

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        nonlocal call_count
        call_count += 1
        return 1000  # ALWAYS returns full limit — would loop forever without cap

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(
        pool,  # type: ignore[arg-type]
        _session_factory(),
        max_drain_iterations=5,  # override for a faster test
    )

    assert result.iterations == 5
    assert result.invalidated == 5000  # 5 × 1000
    assert call_count == 5
    # Unlock still fires.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_limit_none_single_shot(monkeypatch):
    """When `limit=None` the helper drains everything in one call;
    inner loop must NOT repeat (no natural way to know if more exists)."""
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched
    call_count = 0

    async def fake_cleanup(session, *, user_id, ttl_hours, limit):
        nonlocal call_count
        assert limit is None
        call_count += 1
        return 9999  # would otherwise trigger another iteration

    monkeypatch.setattr(sched, "run_quarantine_cleanup", fake_cleanup)

    result = await sweep_quarantine_once(
        pool,  # type: ignore[arg-type]
        _session_factory(),
        limit=None,
    )

    assert result.iterations == 1
    assert call_count == 1
    assert result.invalidated == 9999


# ── run_quarantine_loop — cancellation ─────────────────────────────


@pytest.mark.asyncio
async def test_loop_cancellation_at_startup_delay(monkeypatch):
    conn = FakeConn(try_lock=True)
    pool = FakePool(conn)

    from app.jobs import quarantine_cleanup_scheduler as sched

    async def never_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("sweep must not run during cancelled startup")

    monkeypatch.setattr(sched, "sweep_quarantine_once", never_called)

    task = asyncio.create_task(
        run_quarantine_loop(
            pool,  # type: ignore[arg-type]
            _session_factory(),
            startup_delay_s=3600,
            interval_s=3600,
        ),
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
