"""P5 — lore-enrichment fair-scheduling wiring tests (per-owner concurrent-job cap).

WFQ correctness (atomic Lua cap/lease-TTL) is proven by the SDK's real-Redis suite
(`sdks/python/tests/test_jobs_scheduler.py`). These prove the lore-enrichment WIRING:
the flag gate, the (allowed, token) contract, fail-open on a redis blip, and that a
release is a no-op when off — so a dropped wrap or a mis-shaped return can't silently
no-op (memory: nil-tolerant-decorator-needs-wiring-test).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.jobs import fair_sched

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_flag(monkeypatch):
    # Default OFF for each test; tests that need it ON set it explicitly.
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", False)
    monkeypatch.setattr(fair_sched.settings, "p5_owner_cap", 5)


async def test_acquire_noop_when_disabled():
    allowed, token = await fair_sched.try_acquire_job(uuid4())
    assert allowed is True and token is None  # no cap, no lease


async def test_release_noop_when_disabled():
    with patch.object(fair_sched, "get_scheduler") as gs:
        await fair_sched.release_job(uuid4(), "tok")
        gs.assert_not_called()


async def test_acquire_returns_token_under_cap(monkeypatch):
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", True)
    sched = AsyncMock()
    sched.acquire = AsyncMock(return_value="owner:3")
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_job(uuid4())
    assert allowed is True and token == "owner:3"
    sched.acquire.assert_awaited_once()


async def test_acquire_rejects_when_at_cap(monkeypatch):
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", True)
    sched = AsyncMock()
    sched.acquire = AsyncMock(return_value=None)  # at cap
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_job(uuid4())
    assert allowed is False and token is None  # caller → 429


async def test_acquire_fails_open_on_redis_error(monkeypatch):
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", True)
    sched = AsyncMock()
    sched.acquire = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_job(uuid4())
    assert allowed is True and token is None  # fail-OPEN: never wedge a legit job


async def test_release_calls_scheduler_when_enabled(monkeypatch):
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", True)
    sched = AsyncMock()
    sched.release = AsyncMock(return_value=True)
    uid = uuid4()
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        await fair_sched.release_job(uid, "owner:3")
    sched.release.assert_awaited_once_with(fair_sched.LANE_JOB, str(uid), "owner:3")


async def test_release_noop_when_token_absent(monkeypatch):
    monkeypatch.setattr(fair_sched.settings, "p5_sched_enabled", True)
    with patch.object(fair_sched, "get_scheduler") as gs:
        await fair_sched.release_job(uuid4(), None)  # acquired while P5 was off
        gs.assert_not_called()
