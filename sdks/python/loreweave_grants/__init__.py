"""loreweave_grants — the shared E0 collaboration grant client (Python).

The single async client every Python service uses to resolve a (user, book)
permission against book-service, the single grant authority. Mirrors the Go
``grantclient`` SDK. Extracted from 3 byte-identical service copies
(composition / knowledge / translation) — D-E0-4-PY-GRANT-SDK-EXTRACT.

book-service owns ``books`` + ``book_collaborators`` and exposes
``GET /internal/books/{book_id}/access?user_id=`` which always returns
200 ``{"grant_level": "none|view|edit|manage|owner", "lifecycle_state": ...}`` —
``none`` covers both a missing book and no-grant, so the endpoint is never an
existence oracle (E0 DESIGN R4).

Caching: a short-TTL cache stores ONLY positive grants (level > none) — a freshly
granted user is never stale-denied (``none`` is never cached, so the next call
re-fetches and sees the new grant), and a revoke takes effect within the TTL. v1
TTL is 45s (matches the Go SDK ``DefaultCacheTTL`` → uniform revoke SLA). For
instant revoke, ``invalidate`` drops a cached entry on demand (wired to the
book-service revoke pub/sub by the consuming service — D-GRANT-INSTANT-REVOKE).

Fail-closed: any non-200 / transport error → ``GrantLevel.NONE`` (deny). Errors are
never cached. Never raises on a book-service outage; the caller's gate layer maps a
denied grant to 404/403.

Per-service knobs are passed at construction (base_url, internal_token, timeout,
optional ``trace_id_provider`` for X-Trace-Id propagation) so the one client serves
every service without per-copy drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from enum import IntEnum
from uuid import UUID

import httpx

__all__ = [
    "GrantLevel",
    "parse_grant_level",
    "GrantClient",
    "DEFAULT_CACHE_TTL_S",
    "REVOKE_STREAM",
]

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_S = 45.0  # mirrors Go grantclient.DefaultCacheTTL
DEFAULT_TIMEOUT_S = 10.0
# book-service publishes grant cache-invalidations here via the outbox→relay
# (aggregate_type='grant_revoke' → loreweave:events:grant_revoke). D-GRANT-INSTANT-REVOKE.
REVOKE_STREAM = "loreweave:events:grant_revoke"


class GrantLevel(IntEnum):
    """Ordered permission a user holds on a book: none<view<edit<manage<owner."""

    NONE = 0
    VIEW = 1
    EDIT = 2
    MANAGE = 3
    OWNER = 4

    def at_least(self, need: "GrantLevel") -> bool:
        return self.value >= need.value


_WIRE = {
    "owner": GrantLevel.OWNER,
    "manage": GrantLevel.MANAGE,
    "edit": GrantLevel.EDIT,
    "view": GrantLevel.VIEW,
    "none": GrantLevel.NONE,
}


def parse_grant_level(s: str | None) -> GrantLevel:
    """Map book-service's wire string to a GrantLevel. Unknown/empty/cased →
    NONE (default-deny — never silently grant)."""
    return _WIRE.get(s or "", GrantLevel.NONE)


def _cache_key(user_id: UUID, book_id: UUID) -> str:
    return f"{user_id}:{book_id}"


class GrantClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
        *,
        trace_id_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ttl = cache_ttl_s
        self._trace_id_provider = trace_id_provider
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )
        # key "user_id:book_id" -> (GrantLevel, lifecycle, owner_user_id|None, expiry_monotonic)
        self._cache: dict[str, tuple[GrantLevel, str, UUID | None, float]] = {}
        self._now = time.monotonic  # injectable for tests
        self._revoke_task: asyncio.Task | None = None

    async def aclose(self) -> None:
        await self.stop_revoke_consumer()
        await self._http.aclose()

    async def resolve_access(self, book_id: UUID, user_id: UUID) -> tuple[GrantLevel, str]:
        """Return (grant level, book lifecycle_state) for (user, book). Positive
        grants cached for the TTL; ``none`` and transport errors never cached. A
        book-service failure → (NONE, "") — fail closed."""
        key = _cache_key(user_id, book_id)
        hit = self._cache.get(key)
        if hit is not None:
            lvl, lifecycle, _owner, exp = hit
            if self._now() < exp:
                return lvl, lifecycle
        lvl, lifecycle, owner = await self._fetch(book_id, user_id)
        if lvl > GrantLevel.NONE:
            self._cache[key] = (lvl, lifecycle, owner, self._now() + self._ttl)
        return lvl, lifecycle

    async def resolve_grant(self, book_id: UUID, user_id: UUID) -> GrantLevel:
        lvl, _ = await self.resolve_access(book_id, user_id)
        return lvl

    def invalidate(self, book_id: UUID, user_id: UUID) -> bool:
        """Drop a cached (user, book) grant so the next resolve re-fetches. Powers
        instant revoke (book-service publishes a revoke → the service's subscriber
        calls this). Returns True if an entry was actually removed. Safe to call for
        an uncached pair (no-op)."""
        return self._cache.pop(_cache_key(user_id, book_id), None) is not None

    def invalidate_all(self) -> None:
        """Drop the whole cache (defensive — e.g. a resync signal)."""
        self._cache.clear()

    # ── instant revoke (D-GRANT-INSTANT-REVOKE) ──────────────────────────────
    def start_revoke_consumer(self, redis_url: str, stream: str = REVOKE_STREAM) -> None:
        """Start a background task that tails the grant-revoke stream and drops the
        cached grant for each ``{user_id, book_id}`` it sees — so a book-service revoke
        takes effect at once instead of after the 45s TTL. Call once from the service
        lifespan (a running loop is required); idempotent (a 2nd call no-ops).

        NO consumer group: every client instance must observe every revoke (fan-out),
        so each tails from ``$`` independently. A missed event degrades to the TTL
        (fail-safe). redis is lazy-imported so the base package stays httpx-only."""
        if self._revoke_task is not None and not self._revoke_task.done():
            return
        self._revoke_task = asyncio.create_task(self._revoke_loop(redis_url, stream))

    async def stop_revoke_consumer(self) -> None:
        task = self._revoke_task
        self._revoke_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — best-effort shutdown
                logger.warning("grant-revoke consumer shutdown error", exc_info=True)

    async def _revoke_loop(self, redis_url: str, stream: str) -> None:
        import redis.asyncio as aioredis  # lazy — only services that start the consumer need redis
        from redis.exceptions import TimeoutError as RedisTimeoutError

        r = aioredis.from_url(redis_url, decode_responses=True)
        last_id = "$"  # tail only NEW events; pre-existing entries are stale for a cache
        logger.info("grant-revoke consumer started (stream=%s)", stream)
        try:
            while True:
                try:
                    resp = await r.xread({stream: last_id}, block=5000, count=100)
                except asyncio.CancelledError:
                    raise
                except RedisTimeoutError:
                    # Idle BLOCK timeout (redis-py 8 raises on a quiet stream rather
                    # than returning empty) — the normal "no new events this window"
                    # signal, NOT an error. Re-block silently (D-REDIS8-CONSUMERS);
                    # a real outage surfaces as ConnectionError below.
                    continue
                except Exception:  # noqa: BLE001 — genuine transient redis blip: back off + retry
                    logger.warning("grant-revoke consumer read failed; retrying", exc_info=True)
                    await asyncio.sleep(1.0)
                    continue
                for _stream, entries in resp or []:
                    for msg_id, fields in entries:
                        last_id = msg_id
                        self._apply_revoke(fields)
        except asyncio.CancelledError:
            pass
        finally:
            await r.aclose()
            logger.info("grant-revoke consumer stopped")

    def _apply_revoke(self, fields: dict) -> None:
        """Invalidate the cached grant named by one stream entry's payload. Tolerant:
        a malformed/foreign entry is logged + skipped (never crashes the loop)."""
        raw = fields.get("payload")
        if not raw:
            return
        try:
            body = json.loads(raw)
            book_id = UUID(str(body["book_id"]))
            user_id = UUID(str(body["user_id"]))
        except (ValueError, KeyError, TypeError):
            logger.warning("grant-revoke: malformed payload, ignoring")
            return
        if self.invalidate(book_id, user_id):
            logger.debug("grant-revoke: invalidated grant user=%s book=%s", user_id, book_id)

    async def _fetch(self, book_id: UUID, user_id: UUID) -> tuple[GrantLevel, str, UUID | None]:
        url = f"{self._base_url}/internal/books/{book_id}/access"
        tid = self._trace_id_provider() if self._trace_id_provider else None
        try:
            resp = await self._http.get(
                url,
                params={"user_id": str(user_id)},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "grant authority %s returned %d (fail-closed deny), trace_id=%s",
                    url, resp.status_code, tid,
                )
                return GrantLevel.NONE, "", None
            data = resp.json()
            # owner_user_id is returned by book-service ONLY to a grantee (grant != none),
            # so a consumer can resolve a cross-tenant read of the owner's per-(user,book)
            # rows. Absent/malformed → None (never raises into the caller).
            owner_raw = data.get("owner_user_id")
            try:
                owner = UUID(str(owner_raw)) if owner_raw else None
            except (ValueError, TypeError):
                owner = None
            return parse_grant_level(data.get("grant_level")), data.get("lifecycle_state", "") or "", owner
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "grant authority unavailable (fail-closed deny): %s, trace_id=%s", exc, tid,
            )
            return GrantLevel.NONE, "", None

    async def resolve_owner(self, book_id: UUID, user_id: UUID) -> UUID | None:
        """Return the book-OWNER's user_id when `user_id` holds a grant on the book,
        else None. Powers a grant-gated cross-tenant read of the owner's
        per-(user,book) rows (e.g. the book-tier model settings). Serves from the
        same cache as resolve_access; fail-closed (None) on any error."""
        key = _cache_key(user_id, book_id)
        hit = self._cache.get(key)
        if hit is not None:
            lvl, _lifecycle, owner, exp = hit
            if self._now() < exp:
                return owner if lvl > GrantLevel.NONE else None
        lvl, lifecycle, owner = await self._fetch(book_id, user_id)
        if lvl > GrantLevel.NONE:
            self._cache[key] = (lvl, lifecycle, owner, self._now() + self._ttl)
            return owner
        return None
