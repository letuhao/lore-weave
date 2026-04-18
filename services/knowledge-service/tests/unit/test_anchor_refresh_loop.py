"""K13.1 — unit tests for the nightly anchor-refresh background loop."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.anchor_refresh_loop import run_anchor_refresh_loop
from app.jobs.compute_anchor_score import RefreshResult


def _session_factory():
    @asynccontextmanager
    async def factory():
        yield MagicMock()

    return factory


@pytest.mark.asyncio
async def test_loop_calls_refresh_then_sleeps_interval(monkeypatch):
    """First tick runs refresh, then sleeps for interval_s."""
    call_args: list = []
    sleeps: list[float] = []

    async def fake_refresh(pool, session_factory):
        call_args.append((pool, session_factory))
        return RefreshResult(5, 42, 0, lock_skipped=False)

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)
        # After the second sleep (the between-runs one), cancel the loop.
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.jobs.anchor_refresh_loop.refresh_anchor_scores", fake_refresh,
    )
    monkeypatch.setattr("app.jobs.anchor_refresh_loop.asyncio.sleep", fake_sleep)

    pool = MagicMock()
    factory = _session_factory()

    with pytest.raises(asyncio.CancelledError):
        await run_anchor_refresh_loop(
            pool, factory, interval_s=60, startup_delay_s=1,
        )

    # One call to refresh, two sleeps (startup delay + inter-run).
    assert len(call_args) == 1
    assert call_args[0] == (pool, factory)
    assert sleeps == [1, 60]


@pytest.mark.asyncio
async def test_loop_continues_after_refresh_error(monkeypatch):
    """Unexpected exception from refresh must not kill the loop."""
    runs: list[str] = []
    sleeps: list[float] = []

    async def fake_refresh(pool, session_factory):
        runs.append("ran")
        if len(runs) == 1:
            raise RuntimeError("boom")
        return RefreshResult(1, 1, 0)

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)
        # startup_delay_s=0 means no initial sleep. So:
        #   run 1 (raises) → sleep #1 → run 2 (ok) → sleep #2 (cancel)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.jobs.anchor_refresh_loop.refresh_anchor_scores", fake_refresh,
    )
    monkeypatch.setattr("app.jobs.anchor_refresh_loop.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_anchor_refresh_loop(
            MagicMock(), _session_factory(),
            interval_s=10, startup_delay_s=0,
        )

    # Two refresh attempts — the error didn't abort the loop.
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_loop_records_outcome_metrics(monkeypatch):
    """lock_skipped outcome increments the lock_skipped metric label."""
    from app.metrics import anchor_refresh_runs_total

    before_ok = anchor_refresh_runs_total.labels(outcome="ok")._value.get()
    before_skipped = anchor_refresh_runs_total.labels(outcome="lock_skipped")._value.get()

    results = iter([
        RefreshResult(3, 30, 0, lock_skipped=False),
        RefreshResult(0, 0, 0, lock_skipped=True),
    ])

    async def fake_refresh(pool, session_factory):
        return next(results)

    tick = 0

    async def fake_sleep(seconds: float):
        nonlocal tick
        tick += 1
        if tick >= 3:  # startup + 2 between-runs → bail after 2 runs
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.jobs.anchor_refresh_loop.refresh_anchor_scores", fake_refresh,
    )
    monkeypatch.setattr("app.jobs.anchor_refresh_loop.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_anchor_refresh_loop(
            MagicMock(), _session_factory(),
            interval_s=1, startup_delay_s=0,
        )

    after_ok = anchor_refresh_runs_total.labels(outcome="ok")._value.get()
    after_skipped = anchor_refresh_runs_total.labels(outcome="lock_skipped")._value.get()
    assert after_ok - before_ok == 1
    assert after_skipped - before_skipped == 1


@pytest.mark.asyncio
async def test_loop_cancellation_during_startup_delay(monkeypatch):
    """Cancellation during the warm-up sleep propagates cleanly."""

    async def fake_refresh(pool, session_factory):
        raise AssertionError("must not run if cancelled before first tick")

    async def fake_sleep(seconds: float):
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.jobs.anchor_refresh_loop.refresh_anchor_scores", fake_refresh,
    )
    monkeypatch.setattr("app.jobs.anchor_refresh_loop.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_anchor_refresh_loop(
            MagicMock(), _session_factory(),
            interval_s=60, startup_delay_s=60,
        )
