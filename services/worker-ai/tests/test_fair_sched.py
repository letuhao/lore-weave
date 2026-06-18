"""P5 — worker-ai fair-scheduling wiring tests (the PULL substrate).

The WFQ correctness (atomic Lua cap/round-robin/lease-TTL) is proven by the SDK's
real-Redis suite (`sdks/python/tests/test_jobs_scheduler.py`). These tests prove the
worker-ai WIRING: the flag gate, the (allowed, token) contract, the round-robin
owner ordering, and that a release is a no-op when off — so a dropped wrap or a
mis-shaped return can't silently no-op (memory: nil-tolerant-decorator-needs-wiring-test).
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app import fair_sched

# NOTE: async tests run under `-o asyncio_mode=auto` (the project's pytest invocation);
# no blanket `pytestmark = asyncio` so the sync round_robin tests don't get a spurious mark.


@dataclass
class _J:
    user_id: object
    job_id: object = None


def test_round_robin_interleaves_owners():
    a, b = uuid4(), uuid4()
    jobs = [_J(a), _J(a), _J(a), _J(b)]  # created_at order: A,A,A,B
    out = fair_sched.round_robin_by_owner(jobs)
    owners = [j.user_id for j in out]
    # B's single job is NOT stuck behind all of A's — it surfaces in the first pass.
    assert owners == [a, b, a, a]


def test_round_robin_preserves_within_owner_order():
    a = uuid4()
    j1, j2, j3 = _J(a, "1"), _J(a, "2"), _J(a, "3")
    out = fair_sched.round_robin_by_owner([j1, j2, j3])
    assert [j.job_id for j in out] == ["1", "2", "3"]  # single owner ⇒ unchanged


def test_round_robin_empty():
    assert fair_sched.round_robin_by_owner([]) == []


async def test_acquire_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("P5_SCHED_ENABLED", raising=False)
    allowed, token = await fair_sched.try_acquire_chunk(uuid4())
    assert allowed is True and token is None  # proceeds un-capped, no lease


async def test_release_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("P5_SCHED_ENABLED", raising=False)
    # Must not raise / not touch a scheduler when off.
    with patch.object(fair_sched, "get_scheduler") as gs:
        await fair_sched.release_chunk(uuid4(), "tok")
        gs.assert_not_called()


async def test_acquire_returns_token_when_under_cap(monkeypatch):
    monkeypatch.setenv("P5_SCHED_ENABLED", "true")
    sched = AsyncMock()
    sched.acquire = AsyncMock(return_value="owner:7")
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_chunk(uuid4())
    assert allowed is True and token == "owner:7"
    sched.acquire.assert_awaited_once()


async def test_acquire_defers_when_at_cap(monkeypatch):
    monkeypatch.setenv("P5_SCHED_ENABLED", "true")
    sched = AsyncMock()
    sched.acquire = AsyncMock(return_value=None)  # at cap
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_chunk(uuid4())
    assert allowed is False and token is None


async def test_acquire_fails_open_on_redis_error(monkeypatch):
    monkeypatch.setenv("P5_SCHED_ENABLED", "true")
    sched = AsyncMock()
    sched.acquire = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        allowed, token = await fair_sched.try_acquire_chunk(uuid4())
    # fail-OPEN: a transient redis blip degrades to the un-capped path, never wedges.
    assert allowed is True and token is None


async def test_release_calls_scheduler_when_enabled(monkeypatch):
    monkeypatch.setenv("P5_SCHED_ENABLED", "true")
    sched = AsyncMock()
    sched.release = AsyncMock(return_value=True)
    uid = uuid4()
    with patch.object(fair_sched, "get_scheduler", return_value=sched):
        await fair_sched.release_chunk(uid, "owner:7")
    sched.release.assert_awaited_once_with(fair_sched.LANE_EXTRACTION, str(uid), "owner:7")


async def test_release_noop_when_token_absent(monkeypatch):
    monkeypatch.setenv("P5_SCHED_ENABLED", "true")
    with patch.object(fair_sched, "get_scheduler") as gs:
        await fair_sched.release_chunk(uuid4(), None)  # chunk submitted while P5 was off
        gs.assert_not_called()
