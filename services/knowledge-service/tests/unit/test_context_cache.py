"""Unit tests for the L0/L1 TTL cache (K6.2 + K6.3).

Covers:
  - basic get/put/invalidate round-trip
  - negative caching via MISSING sentinel
  - selector cache-through: first call hits repo, second call doesn't
  - SummariesRepo.upsert/delete invalidates the matching key
  - hit/miss metrics increment correctly
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.context import cache
from app.context.selectors.projects import load_project_summary
from app.context.selectors.summaries import load_global_summary
from app.db.models import Summary
from app.metrics import cache_hit_total, cache_miss_total


def _summary(scope: str, scope_id=None, content: str = "hi") -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=uuid4(),
        scope_type=scope,
        scope_id=scope_id,
        content=content,
        token_count=1,
        version=1,
        created_at=now,
        updated_at=now,
    )


# ── bare cache module ──────────────────────────────────────────────────────


def test_l0_put_then_get_returns_same_summary():
    uid = uuid4()
    s = _summary("global")
    cache.put_l0(uid, s)
    assert cache.get_l0(uid) is s


def test_l0_missing_key_returns_none():
    assert cache.get_l0(uuid4()) is None


def test_l0_negative_cache_returns_missing_sentinel():
    uid = uuid4()
    cache.put_l0(uid, None)
    assert cache.get_l0(uid) is cache.MISSING


def test_l0_invalidate_drops_entry():
    uid = uuid4()
    cache.put_l0(uid, _summary("global"))
    cache.invalidate_l0(uid)
    assert cache.get_l0(uid) is None


def test_l1_keyed_by_user_and_project():
    uid = uuid4()
    pid_a = uuid4()
    pid_b = uuid4()
    s_a = _summary("project", pid_a, content="A")
    s_b = _summary("project", pid_b, content="B")
    cache.put_l1(uid, pid_a, s_a)
    cache.put_l1(uid, pid_b, s_b)
    assert cache.get_l1(uid, pid_a) is s_a
    assert cache.get_l1(uid, pid_b) is s_b


def test_l1_invalidate_does_not_affect_other_project():
    uid = uuid4()
    pid_a = uuid4()
    pid_b = uuid4()
    cache.put_l1(uid, pid_a, _summary("project", pid_a))
    cache.put_l1(uid, pid_b, _summary("project", pid_b))
    cache.invalidate_l1(uid, pid_a)
    assert cache.get_l1(uid, pid_a) is None
    assert cache.get_l1(uid, pid_b) is not None


# ── selectors use cache ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_global_summary_caches_positive_result():
    uid = uuid4()
    s = _summary("global", content="cached-bio")
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=s)

    first = await load_global_summary(repo, uid)
    second = await load_global_summary(repo, uid)

    assert first is s
    assert second is s
    # Repo hit once; second call served from cache.
    assert repo.get.await_count == 1


@pytest.mark.asyncio
async def test_load_global_summary_caches_negative_result():
    uid = uuid4()
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)

    first = await load_global_summary(repo, uid)
    second = await load_global_summary(repo, uid)

    assert first is None
    assert second is None
    # Missing rows are cached via the MISSING sentinel — no re-query.
    assert repo.get.await_count == 1


@pytest.mark.asyncio
async def test_load_project_summary_caches_result():
    uid = uuid4()
    pid = uuid4()
    s = _summary("project", pid)
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=s)

    first = await load_project_summary(repo, uid, pid)
    second = await load_project_summary(repo, uid, pid)

    assert first is s
    assert second is s
    assert repo.get.await_count == 1


@pytest.mark.asyncio
async def test_l0_cache_hit_metric_increments():
    uid = uuid4()
    cache.put_l0(uid, _summary("global"))
    before = cache_hit_total.labels(layer="l0")._value.get()
    cache.get_l0(uid)
    after = cache_hit_total.labels(layer="l0")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_l0_cache_miss_metric_increments():
    before = cache_miss_total.labels(layer="l0")._value.get()
    cache.get_l0(uuid4())
    after = cache_miss_total.labels(layer="l0")._value.get()
    assert after == before + 1


# ── K6.3 invalidation on write ────────────────────────────────────────────


def test_invalidate_cache_helper_routes_global():
    from app.db.repositories.summaries import _invalidate_cache

    uid = uuid4()
    cache.put_l0(uid, _summary("global"))
    _invalidate_cache(uid, "global", None)
    assert cache.get_l0(uid) is None


def test_invalidate_cache_helper_routes_project():
    from app.db.repositories.summaries import _invalidate_cache

    uid = uuid4()
    pid = uuid4()
    cache.put_l1(uid, pid, _summary("project", pid))
    _invalidate_cache(uid, "project", pid)
    assert cache.get_l1(uid, pid) is None


def test_invalidate_cache_helper_unknown_scope_is_noop():
    from app.db.repositories.summaries import _invalidate_cache

    # Should not raise, even for scope types we don't cache.
    _invalidate_cache(uuid4(), "session", uuid4())  # type: ignore[arg-type]


# ── K6-I2: TTL expiration invariant ───────────────────────────────────────


def test_l0_cache_entries_expire_after_ttl(monkeypatch):
    """Swap in a tiny-TTL cache and verify the sentinel disappears
    after sleeping past the window. Guards the core cache invariant:
    a row eventually evicts so stale data doesn't live forever.
    """
    import time as _time
    from cachetools import TTLCache

    # Replace the L0 cache with a 50ms-TTL instance for this test only.
    tiny = TTLCache(maxsize=10, ttl=0.05)
    monkeypatch.setattr(cache, "_l0_cache", tiny)

    uid = uuid4()
    cache.put_l0(uid, _summary("global", content="will-expire"))

    # Immediately visible.
    assert cache.get_l0(uid) is not None

    # Sleep past the TTL — entry must be evicted on next read.
    _time.sleep(0.08)
    assert cache.get_l0(uid) is None


def test_l1_cache_entries_expire_after_ttl(monkeypatch):
    import time as _time
    from cachetools import TTLCache

    tiny = TTLCache(maxsize=10, ttl=0.05)
    monkeypatch.setattr(cache, "_l1_cache", tiny)

    uid = uuid4()
    pid = uuid4()
    cache.put_l1(uid, pid, _summary("project", pid))

    assert cache.get_l1(uid, pid) is not None
    _time.sleep(0.08)
    assert cache.get_l1(uid, pid) is None
