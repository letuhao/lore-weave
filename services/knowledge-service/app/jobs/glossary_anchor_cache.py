"""P2 — in-process LRU cache for glossary known-entities anchors.

Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D4.

Design notes (post /review-impl round 1):
  - M3 fix: NO bucketing. Keyed strictly by (book_id, chapter_index).
    Avoids precision loss and 5-chapter-boundary spikes.
  - M5 fix: per-process, never cleared. Glossary anchor is read-only
    within an extraction run; cross-job staleness bounded by the slowly
    changing nature of glossary.
  - Concurrent extraction jobs on the same book share this cache (safe;
    fetch is read-only).
  - Max 1000 entries (~50KB/anchor × 1000 = 50MB process memory).
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any, Awaitable, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

# Type for the fetcher: (book_id, chapter_index) -> awaitable list of dicts.
AnchorFetcher = Callable[[UUID, int], Awaitable[list[dict[str, Any]]]]


class GlossaryAnchorCache:
    """Async LRU keyed by (book_id, chapter_index). Bounded; oldest evicted.

    Concurrent calls for the same key are coalesced via an in-flight
    futures map (singleflight) so we don't fire N glossary calls for
    N concurrent leaf tasks within the same chapter.
    """

    def __init__(self, max_size: int = 1000):
        self._max = max_size
        self._cache: OrderedDict[tuple[UUID, int], list[dict[str, Any]]] = OrderedDict()
        self._inflight: dict[tuple[UUID, int], asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        book_id: UUID,
        chapter_index: int,
        fetcher: AnchorFetcher,
    ) -> list[dict[str, Any]]:
        """Return the cached anchor for (book_id, chapter_index), or fetch
        via the provided fetcher (called at most once per key thanks to
        the singleflight inflight map).

        The fetcher MAY raise; in that case the inflight future propagates
        the exception to all coalesced waiters AND the cache is NOT
        populated (next call will retry).
        """
        key = (book_id, chapter_index)

        async with self._lock:
            if key in self._cache:
                # Touch LRU order.
                self._cache.move_to_end(key)
                return self._cache[key]
            if key in self._inflight:
                fut = self._inflight[key]
            else:
                fut = asyncio.get_running_loop().create_future()
                self._inflight[key] = fut
                # Detach the actual fetch so the lock can release.
                asyncio.create_task(self._do_fetch(key, fetcher, fut))

        # Awaiting outside the lock so coalesced callers don't block claims.
        return await fut

    async def _do_fetch(
        self,
        key: tuple[UUID, int],
        fetcher: AnchorFetcher,
        fut: asyncio.Future,
    ) -> None:
        try:
            anchor = await fetcher(*key)
        except Exception as exc:  # noqa: BLE001 — propagate hard fail
            async with self._lock:
                self._inflight.pop(key, None)
            if not fut.done():
                fut.set_exception(exc)
            return
        async with self._lock:
            self._cache[key] = anchor
            self._inflight.pop(key, None)
            # Bounded LRU eviction.
            while len(self._cache) > self._max:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("glossary_anchor_cache evicted %s", evicted_key)
        if not fut.done():
            fut.set_result(anchor)

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """Test-only. Production code never calls clear (M5 spec)."""
        self._cache.clear()
        self._inflight.clear()


__all__ = ["AnchorFetcher", "GlossaryAnchorCache"]
