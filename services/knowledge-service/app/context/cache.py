"""Per-process TTL caches for L0 and L1 summaries (K6.2).

In-process `cachetools.TTLCache` keyed per layer:

  - L0: user_id → Summary | None
  - L1: (user_id, project_id) → Summary | None

`None` IS cached (negative caching) — missing bios / missing project
summaries are the common case and we don't want to hammer Postgres
for every turn from a user who hasn't set a bio. A sentinel value
distinguishes "cached as absent" from "not in cache".

Cache staleness is capped at 60 seconds. Within the same process,
K6.3 adds write-through invalidation (the repo's upsert/delete pops
the local key). Across processes, D-T2-04 registers a Redis-pub/sub
invalidator via `set_invalidator` and the write-path `invalidate_*`
helpers fire-and-forget publish so peer workers drop the same key.

The cache is NOT a write-through cache. Writes go to the repo first
and then invalidate the matching key. Reads try the cache first and
fall through to the repo on miss.

Module-level state is intentional — see the explanation in
app/clients/glossary_client.py for the same per-worker singleton
rationale.
"""

from __future__ import annotations

from typing import Any, Protocol
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
    "invalidate_all_for_user",
    "clear_all",
    "set_invalidator",
    "apply_remote_l0_invalidation",
    "apply_remote_l1_invalidation",
    "apply_remote_user_invalidation",
    "L0_LAYER",
    "L1_LAYER",
]


class _Invalidator(Protocol):
    """Duck-typed interface for the D-T2-04 CacheInvalidator.

    Kept local to avoid a circular import with `cache_invalidation`
    (which imports this module to apply remote invalidations).
    """

    def publish(
        self,
        op: str,
        user_id: UUID,
        project_id: UUID | None = None,
    ) -> None:
        ...

L0_LAYER = "l0"
L1_LAYER = "l1"

_TTL_SECONDS = 60
_MAX_SIZE = 10_000

# Distinct-from-None sentinel meaning "we queried the DB and got no
# row — don't re-query for TTL seconds".
MISSING: Any = object()

_l0_cache: TTLCache = TTLCache(maxsize=_MAX_SIZE, ttl=_TTL_SECONDS)
_l1_cache: TTLCache = TTLCache(maxsize=_MAX_SIZE, ttl=_TTL_SECONDS)

# D-T2-04 — installed by lifespan when Redis is configured; None means
# single-process / Track 1 deploy where we stay on local-only semantics.
_invalidator: _Invalidator | None = None


def set_invalidator(invalidator: _Invalidator | None) -> None:
    """Register (or clear) the cross-process invalidator.

    Called from the lifespan hook once the Redis-backed
    `CacheInvalidator` has finished its `.start()`. Passing `None`
    un-registers on shutdown or on the Track 1 path where the
    invalidator was never constructed.
    """
    global _invalidator
    _invalidator = invalidator


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
    """Pop the local key and broadcast to peer workers.

    Local pop is synchronous so THIS worker never reads stale after
    a write. The cross-process publish is fire-and-forget; peer
    workers drop their keys on receipt, with the TTL as the ultimate
    fallback if the pub/sub message never arrives (network blip,
    Redis down).
    """
    _l0_cache.pop(user_id, None)
    # Capture to a local to avoid the check-then-use race where a
    # concurrent `set_invalidator(None)` (lifespan shutdown) could
    # null the module-level slot between the None check and the call.
    # In practice writes should be drained before shutdown, but the
    # local-capture costs nothing and closes the hole.
    inv = _invalidator
    if inv is not None:
        inv.publish("l0", user_id)


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
    """Pop the local (user, project) key and broadcast."""
    _l1_cache.pop((user_id, project_id), None)
    inv = _invalidator  # local capture — see invalidate_l0
    if inv is not None:
        inv.publish("l1", user_id, project_id)


def invalidate_all_for_user(user_id: UUID) -> None:
    """Drop every cache entry for `user_id` across both layers.

    Used by K7d's user-data delete to guarantee a freshly-deleted
    user's stale rows can't surface from a per-process cache for the
    next 60 seconds. Walks the cache snapshots (NOT the live dicts —
    we mutate during iteration) and pops any matching key.

    O(N) over total cache size; called only on user erasure which is
    rare. D-T2-04 extends the broadcast to peer workers via pub/sub
    when the invalidator is installed.
    """
    _l0_cache.pop(user_id, None)
    for key in [k for k in list(_l1_cache.keys()) if k[0] == user_id]:
        _l1_cache.pop(key, None)
    inv = _invalidator  # local capture — see invalidate_l0
    if inv is not None:
        inv.publish("user", user_id)


def clear_all() -> None:
    """Test helper — drops all cached entries across both layers."""
    _l0_cache.clear()
    _l1_cache.clear()


# ── D-T2-04 remote-invalidation hooks (no re-publish) ───────────────
#
# The Redis-pub/sub subscriber calls these after receiving a message
# from a peer worker. They pop the local key WITHOUT firing a publish
# of their own — preventing an echo storm where worker B's local pop
# triggers another broadcast back to worker A.


def apply_remote_l0_invalidation(user_id: UUID) -> None:
    _l0_cache.pop(user_id, None)


def apply_remote_l1_invalidation(user_id: UUID, project_id: UUID) -> None:
    _l1_cache.pop((user_id, project_id), None)


def apply_remote_user_invalidation(user_id: UUID) -> None:
    _l0_cache.pop(user_id, None)
    for key in [k for k in list(_l1_cache.keys()) if k[0] == user_id]:
        _l1_cache.pop(key, None)
