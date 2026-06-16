"""P5 WFQ FairScheduler — real-Redis integration tests.

The scheduler's correctness lives in its Lua scripts (atomic round-robin, per-owner
cap, lease-TTL crash backstop, release re-arm) — invariants a mock/fake Redis cannot
prove. So these are GATED on a real Redis: set ``P5_TEST_REDIS_URL`` (e.g.
``redis://localhost:6399``) to run them; skipped otherwise. Each test uses a unique
``lane`` so they never collide and clean up after themselves.
"""

from __future__ import annotations

import os
import uuid

import pytest

from loreweave_jobs import FairScheduler

pytestmark = pytest.mark.asyncio

_URL = os.environ.get("P5_TEST_REDIS_URL")
_skip = pytest.mark.skipif(not _URL, reason="set P5_TEST_REDIS_URL to run scheduler integration tests")


@pytest.fixture
async def sched():
    s = FairScheduler(_URL, owner_cap=5, global_budget=0, lease_ttl_ms=3_600_000)
    lane = f"test:{uuid.uuid4().hex[:12]}"
    yield s, lane
    # cleanup all keys for this lane
    r = await s._r()
    keys = await r.keys(f"p5:{lane}:*")
    if keys:
        await r.delete(*keys)
    await s.close()


@_skip
async def test_per_owner_cap_bounds_inflight(sched):
    s, lane = sched
    for i in range(10):
        await s.enqueue(lane, "ownerA", {"n": i})
    released = await s.dispatch(lane, cap=3, max_batch=100)
    assert len(released) == 3  # capped at 3 even though 10 are ready
    assert await s.inflight_count(lane, "ownerA") == 3
    assert await s.ready_len(lane, "ownerA") == 7
    # units came out FIFO
    assert [u["n"] for _, u in released] == [0, 1, 2]


@_skip
async def test_wfq_round_robin_across_owners(sched):
    s, lane = sched
    for i in range(5):
        await s.enqueue(lane, "A", {"who": "A", "n": i})
    for i in range(5):
        await s.enqueue(lane, "B", {"who": "B", "n": i})
    released = await s.dispatch(lane, cap=10, max_batch=4)
    whos = [u["who"] for _, u in released]
    # round-robin interleave, not 4×A then B
    assert whos == ["A", "B", "A", "B"]


@_skip
async def test_giant_job_does_not_starve_small_one(sched):
    s, lane = sched
    for i in range(100):
        await s.enqueue(lane, "giant", {"n": i})
    for i in range(3):
        await s.enqueue(lane, "small", {"n": i})
    # cap=2 per owner; drain in batches the way a dispatcher loop would, releasing as we go
    seen_small = 0
    for _ in range(10):
        batch = await s.dispatch(lane, cap=2, max_batch=4)
        for tok, _u in batch:
            # token is "{owner}:{seq}"; immediately "finish" the unit so the next pass
            # can dispatch more (what a real dispatcher loop + worker terminal does).
            owner = tok.rsplit(":", 1)[0]
            if owner == "small":
                seen_small += 1
            await s.release(lane, owner, tok)
        if seen_small >= 3:
            break
    # the small owner's 3 units all got served quickly, not stuck behind the giant's 100
    assert seen_small == 3


@_skip
async def test_release_rearms_a_capped_owner(sched):
    s, lane = sched
    for i in range(4):
        await s.enqueue(lane, "A", {"n": i})
    first = await s.dispatch(lane, cap=2, max_batch=10)
    assert len(first) == 2  # at cap
    assert await s.dispatch(lane, cap=2, max_batch=10) == []  # still at cap → nothing
    tok, _ = first[0]
    await s.release(lane, "A", tok)  # free one slot → ring re-armed
    again = await s.dispatch(lane, cap=2, max_batch=10)
    assert len(again) == 1  # exactly one more (back at cap)


@_skip
async def test_global_budget_caps_total(sched):
    s, lane = sched
    for o in ("A", "B", "C"):
        for i in range(5):
            await s.enqueue(lane, o, {"n": i})
    released = await s.dispatch(lane, cap=5, budget=4, max_batch=100)
    assert len(released) == 4  # global budget wins over per-owner cap
    assert await s.inflight_total(lane) == 4


@_skip
async def test_pull_acquire_release_cap(sched):
    s, lane = sched
    t1 = await s.acquire(lane, "A", cap=2)
    t2 = await s.acquire(lane, "A", cap=2)
    assert t1 and t2
    assert await s.acquire(lane, "A", cap=2) is None  # at cap
    assert await s.release(lane, "A", t1) is True
    assert await s.acquire(lane, "A", cap=2)  # slot freed


@_skip
async def test_release_is_idempotent(sched):
    s, lane = sched
    t = await s.acquire(lane, "A", cap=5)
    assert await s.release(lane, "A", t) is True
    assert await s.release(lane, "A", t) is False  # double-release is a no-op
    assert await s.inflight_total(lane) == 0


@_skip
async def test_expired_lease_reclaimed(sched):
    s, lane = sched
    # ttl=0 ⇒ the lease is already expired by the time we look (crash-leak simulation)
    t = await s.acquire(lane, "A", cap=5, lease_ttl_ms=0)
    assert t
    # a fresh acquire drops the expired one first → count stays bounded
    total = await s.reclaim_expired(lane)
    assert total == 0
    assert await s.inflight_count(lane, "A") == 0
