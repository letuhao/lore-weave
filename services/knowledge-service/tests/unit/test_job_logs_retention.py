"""C3 (D-K19b.8-01) — unit tests for job_logs retention sweep.

Covers the sweep + loop contract matrix:
  - advisory-lock skip / acquire / release on raise
  - DELETE count parse (normal / empty tag / malformed / zero)
  - cancellation at startup-delay + sweep + sleep boundaries
  - non-Cancelled exceptions don't kill the loop
  - defaults exposed
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.job_logs_retention import (
    DEFAULT_INTERVAL_S,
    DEFAULT_RETAIN_DAYS,
    DEFAULT_STARTUP_DELAY_S,
    RetentionResult,
    _parse_delete_count,
    run_job_logs_retention_loop,
    sweep_job_logs_once,
)


# ── fakes ───────────────────────────────────────────────────────────


class FakeConn:
    """Minimal async-pool-connection stand-in. Records executed SQL +
    returns canned results for the advisory-lock, DELETE, unlock path.
    """

    def __init__(
        self,
        *,
        try_lock: bool = True,
        delete_tag: str = "DELETE 0",
        delete_raises: Exception | None = None,
    ):
        self._try_lock = try_lock
        self._delete_tag = delete_tag
        self._delete_raises = delete_raises
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
        if "DELETE FROM job_logs" in sql:
            if self._delete_raises is not None:
                raise self._delete_raises
            return self._delete_tag
        raise AssertionError(f"unexpected execute: {sql}")


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


# ── _parse_delete_count ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("DELETE 5", 5),
        ("DELETE 0", 0),
        ("DELETE 12345", 12345),
        ("", 0),
        ("DELETE", 0),
        ("DELETE abc", 0),
        (None, 0),
    ],
)
def test_parse_delete_count_handles_all_shapes(tag, expected):
    """Hardening against a malformed command tag — asyncpg always
    returns ``DELETE N`` on DELETE, but the parser should fail soft
    rather than crash the scheduler loop."""
    assert _parse_delete_count(tag) == expected


# ── sweep_job_logs_once ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_skips_when_lock_already_held():
    conn = FakeConn(try_lock=False)
    pool = FakePool(conn)
    result = await sweep_job_logs_once(pool)  # type: ignore[arg-type]
    assert result.lock_skipped is True
    assert result.deleted == 0
    # DELETE must NOT have been executed.
    assert not any("DELETE FROM job_logs" in s for s in conn.executed)
    # Unlock must NOT be called when lock wasn't acquired.
    assert not any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_deletes_old_rows_and_returns_count():
    conn = FakeConn(try_lock=True, delete_tag="DELETE 42")
    pool = FakePool(conn)
    result = await sweep_job_logs_once(pool)  # type: ignore[arg-type]
    assert result.lock_skipped is False
    assert result.deleted == 42
    assert any("DELETE FROM job_logs" in s for s in conn.executed)
    # Unlock must fire after successful DELETE.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_zero_row_delete_is_not_error():
    """Empty table / all-fresh scenario. Not an error — retention
    ran, just had nothing to do.

    /review-impl L3: explicitly assert the advisory unlock fires
    even on the zero-row path. A regression moving the unlock
    inside an ``if deleted > 0`` branch would pass all other tests
    but strand the lock forever when the table is quiet.
    """
    conn = FakeConn(try_lock=True, delete_tag="DELETE 0")
    pool = FakePool(conn)
    result = await sweep_job_logs_once(pool)  # type: ignore[arg-type]
    assert result.deleted == 0
    assert result.lock_skipped is False
    # Lock MUST be released even when zero rows matched.
    assert any("pg_advisory_unlock" in s for s in conn.executed), (
        "advisory unlock must fire on zero-row sweep"
    )


@pytest.mark.asyncio
async def test_sweep_releases_lock_on_delete_exception():
    """If DELETE raises (shouldn't happen in practice — plain DELETE
    has no CHECK constraints — but defensive). Lock MUST be released
    so the next scheduled run can acquire. Tests the ``try/finally``
    contract."""
    conn = FakeConn(
        try_lock=True,
        delete_raises=RuntimeError("simulated DELETE failure"),
    )
    pool = FakePool(conn)
    with pytest.raises(RuntimeError, match="simulated DELETE failure"):
        await sweep_job_logs_once(pool)  # type: ignore[arg-type]
    # Lock must have been released even though DELETE blew up.
    assert any("pg_advisory_unlock" in s for s in conn.executed)


@pytest.mark.asyncio
async def test_sweep_forwards_retain_days_via_make_interval():
    """Parameter flows through to the DELETE. Use a FakeConn that
    captures the args to verify the integer reaches the SQL."""
    captured_args: list = []

    class CapturingConn(FakeConn):
        async def execute(self, sql: str, *args) -> str:
            self.executed.append(sql.strip()[:40])
            if "DELETE FROM job_logs" in sql:
                captured_args.extend(args)
                return "DELETE 7"
            if "pg_advisory_unlock" in sql:
                return "SELECT 1"
            raise AssertionError(f"unexpected execute: {sql}")

    conn = CapturingConn(try_lock=True)
    pool = FakePool(conn)
    result = await sweep_job_logs_once(pool, retain_days=45)  # type: ignore[arg-type]
    assert result.deleted == 7
    assert captured_args == [45]


# ── run_job_logs_retention_loop ─────────────────────────────────────


@pytest.mark.asyncio
async def test_loop_cancellation_during_startup_delay():
    """Cancelling the task during the startup sleep must re-raise
    CancelledError (not swallow it) so FastAPI lifespan teardown
    proceeds cleanly."""
    pool = MagicMock()

    task = asyncio.create_task(
        run_job_logs_retention_loop(
            pool, interval_s=100, startup_delay_s=1_000,
        )
    )
    # Let the coroutine reach the startup_delay sleep.
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_loop_cancellation_during_interval_sleep(monkeypatch):
    """After a successful sweep, the loop sleeps. Cancel during that
    sleep and assert CancelledError re-raises."""
    sweep_calls = 0

    async def fake_sweep(pool, *, retain_days):
        nonlocal sweep_calls
        sweep_calls += 1
        return RetentionResult(deleted=0, lock_skipped=False)

    monkeypatch.setattr(
        "app.jobs.job_logs_retention.sweep_job_logs_once", fake_sweep,
    )

    pool = MagicMock()
    task = asyncio.create_task(
        run_job_logs_retention_loop(
            pool, interval_s=10_000, startup_delay_s=0,
        )
    )
    # Yield repeatedly until the first sweep has happened.
    for _ in range(5):
        await asyncio.sleep(0)
        if sweep_calls >= 1:
            break
    assert sweep_calls == 1, "sweep should fire on first loop iteration"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_loop_continues_after_non_cancelled_sweep_exception(monkeypatch):
    """A RuntimeError during sweep should NOT kill the loop — one bad
    sweep shouldn't silence retention for the rest of the process
    lifetime. Cancelled exceptions DO propagate (see preceding tests)."""
    sweep_calls = 0

    async def fake_sweep(pool, *, retain_days):
        nonlocal sweep_calls
        sweep_calls += 1
        if sweep_calls == 1:
            raise RuntimeError("transient DB error")
        return RetentionResult(deleted=3, lock_skipped=False)

    monkeypatch.setattr(
        "app.jobs.job_logs_retention.sweep_job_logs_once", fake_sweep,
    )

    pool = MagicMock()
    # Very short interval so we get a 2nd sweep quickly.
    task = asyncio.create_task(
        run_job_logs_retention_loop(
            pool, interval_s=0, startup_delay_s=0,
        )
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if sweep_calls >= 2:
            break
    assert sweep_calls >= 2, "loop should have recovered and swept again"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_defaults_exposed():
    """Lock the constants — a drift here would silently change
    retention behaviour across deploys."""
    assert DEFAULT_INTERVAL_S == 24 * 60 * 60
    assert DEFAULT_STARTUP_DELAY_S == 1200
    assert DEFAULT_RETAIN_DAYS == 90
