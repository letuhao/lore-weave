"""Per-process TTL caches for L0 and L1 summaries (K6.2).

In-process `cachetools.TTLCache` keyed per layer:

  - L0: user_id → Summary | None
  - L1: (user_id, project_id) → Summary | None

`None` IS cached (negative caching) — missing bios / missing project
summaries are the common case and we don't want to hammer Postgres
for every turn from a user who hasn't set a bio. A sentinel value
distinguishes "cached as absent" from "not in cache".

Cache staleness is capped at 60 seconds (K6.3 adds write-through
invalidation for the same-process case). Cross-process invalidation
is Track 2 — multi-process scale-out of knowledge-service accepts up
to 60s of staleness in exchange for simpler ops.

The cache is NOT a write-through cache. Writes go to the repo first
and then invalidate the matching key (K6.3). Reads try the cache
first and fall through to the repo on miss.

Module-level state is intentional — see the explanation in
app/clients/glossary_client.py for the same per-worker singleton
rationale.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cachetools import TTLCache

from app.db.models import Summary
from app.metrics import cache_hit_total, cache_miss_total

__all__ = [
    "MISSING",
    "get_l0",
    "put_l0",
    "invalidate_l0",
    "get_l1",
    "put_l1",
    "invalidate_l1",
    "clear_all",
    "L0_LAYER",
    "L1_LAYER",
]

L0_LAYER = "l0"
L1_LAYER = "l1"

_TTL_SECONDS = 60
_MAX_SIZE = 10_000

# Distinct-from-None sentinel meaning "we queried the DB and got no
# row — don't re-query for TTL seconds".
MISSING: Any = object()

_l0_cache: TTLCache = TTLCache(maxsize=_MAX_SIZE, ttl=_TTL_SECONDS)
_l1_cache: TTLCache = TTLCache(maxsize=_MAX_SIZE, ttl=_TTL_SECONDS)


def get_l0(user_id: UUID) -> Summary | None | Any:
    """Return the cached L0 summary, the MISSING sentinel for a known
    absent row, or None for a cache miss.

    Callers must distinguish `None` (cache miss, fall through to DB)
    from `MISSING` (cache hit, row is known to not exist).
    """
    try:
        value = _l0_cache[user_id]
    except KeyError:
        cache_miss_total.labels(layer=L0_LAYER).inc()
        return None
    cache_hit_total.labels(layer=L0_LAYER).inc()
    return value


def put_l0(user_id: UUID, summary: Summary | None) -> None:
    _l0_cache[user_id] = summary if summary is not None else MISSING


def invalidate_l0(user_id: UUID) -> None:
    _l0_cache.pop(user_id, None)


def get_l1(user_id: UUID, project_id: UUID) -> Summary | None | Any:
    key = (user_id, project_id)
    try:
        value = _l1_cache[key]
    except KeyError:
        cache_miss_total.labels(layer=L1_LAYER).inc()
        return None
    cache_hit_total.labels(layer=L1_LAYER).inc()
    return value


def put_l1(user_id: UUID, project_id: UUID, summary: Summary | None) -> None:
    _l1_cache[(user_id, project_id)] = summary if summary is not None else MISSING


def invalidate_l1(user_id: UUID, project_id: UUID) -> None:
    _l1_cache.pop((user_id, project_id), None)


def clear_all() -> None:
    """Test helper — drops all cached entries across both layers."""
    _l0_cache.clear()
    _l1_cache.clear()
