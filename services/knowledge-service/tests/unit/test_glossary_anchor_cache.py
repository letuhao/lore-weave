"""P2 — tests for GlossaryAnchorCache (singleflight LRU)."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from app.jobs.glossary_anchor_cache import GlossaryAnchorCache


@pytest.fixture
def cache() -> GlossaryAnchorCache:
    return GlossaryAnchorCache(max_size=3)


@pytest.fixture
def book_a() -> UUID:
    return uuid4()


async def test_cache_hit_returns_cached_anchor(cache, book_a):
    call_count = 0

    async def fetcher(bid: UUID, ci: int) -> list[dict]:
        nonlocal call_count
        call_count += 1
        return [{"name": "Alice", "ch": ci}]

    anchor1 = await cache.get(book_a, 5, fetcher)
    anchor2 = await cache.get(book_a, 5, fetcher)
    assert anchor1 == anchor2
    assert call_count == 1, "fetcher should be called once across two reads"


async def test_different_chapters_fetch_separately(cache, book_a):
    call_count = 0

    async def fetcher(bid, ci):
        nonlocal call_count
        call_count += 1
        return [{"ch": ci}]

    a5 = await cache.get(book_a, 5, fetcher)
    a6 = await cache.get(book_a, 6, fetcher)
    assert a5[0]["ch"] == 5
    assert a6[0]["ch"] == 6
    assert call_count == 2


async def test_singleflight_coalesces_concurrent_misses(cache, book_a):
    """Two concurrent get() calls for the same key -> fetcher called ONCE."""
    call_count = 0

    async def slow_fetcher(bid, ci):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return [{"ch": ci}]

    a1_task = asyncio.create_task(cache.get(book_a, 5, slow_fetcher))
    a2_task = asyncio.create_task(cache.get(book_a, 5, slow_fetcher))
    a1, a2 = await asyncio.gather(a1_task, a2_task)
    assert a1 == a2
    assert call_count == 1, "singleflight should coalesce concurrent same-key calls"


async def test_fetcher_exception_propagates_to_all_waiters_and_doesnt_cache(cache, book_a):
    call_count = 0

    async def failing_fetcher(bid, ci):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("glossary down")

    with pytest.raises(RuntimeError):
        await cache.get(book_a, 5, failing_fetcher)
    # Retry: fetcher is called AGAIN (failure was not cached).
    with pytest.raises(RuntimeError):
        await cache.get(book_a, 5, failing_fetcher)
    assert call_count == 2


async def test_lru_evicts_when_over_size(cache, book_a):
    async def fetcher(bid, ci):
        return [{"ch": ci}]

    # max_size=3 (fixture). Add 4 entries.
    await cache.get(book_a, 1, fetcher)
    await cache.get(book_a, 2, fetcher)
    await cache.get(book_a, 3, fetcher)
    await cache.get(book_a, 4, fetcher)
    # The oldest (chapter 1) should have been evicted.
    assert len(cache) == 3
    # Re-fetch chapter 1: fetcher is called again (cache miss).
    count_before = 0

    async def counting_fetcher(bid, ci):
        nonlocal count_before
        count_before += 1
        return [{"ch": ci, "refetched": True}]

    again = await cache.get(book_a, 1, counting_fetcher)
    assert count_before == 1
    assert again[0].get("refetched") is True


async def test_different_books_isolated(cache, book_a):
    book_b = uuid4()
    call_log = []

    async def fetcher(bid, ci):
        call_log.append((bid, ci))
        return [{"ch": ci, "book": str(bid)}]

    await cache.get(book_a, 5, fetcher)
    await cache.get(book_b, 5, fetcher)
    assert len(call_log) == 2, "different books should not share cache entries"
