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
]

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_S = 45.0  # mirrors Go grantclient.DefaultCacheTTL
DEFAULT_TIMEOUT_S = 10.0


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
        # key "user_id:book_id" -> (GrantLevel, lifecycle, expiry_monotonic)
        self._cache: dict[str, tuple[GrantLevel, str, float]] = {}
        self._now = time.monotonic  # injectable for tests

    async def aclose(self) -> None:
        await self._http.aclose()

    async def resolve_access(self, book_id: UUID, user_id: UUID) -> tuple[GrantLevel, str]:
        """Return (grant level, book lifecycle_state) for (user, book). Positive
        grants cached for the TTL; ``none`` and transport errors never cached. A
        book-service failure → (NONE, "") — fail closed."""
        key = _cache_key(user_id, book_id)
        hit = self._cache.get(key)
        if hit is not None:
            lvl, lifecycle, exp = hit
            if self._now() < exp:
                return lvl, lifecycle
        lvl, lifecycle = await self._fetch(book_id, user_id)
        if lvl > GrantLevel.NONE:
            self._cache[key] = (lvl, lifecycle, self._now() + self._ttl)
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

    async def _fetch(self, book_id: UUID, user_id: UUID) -> tuple[GrantLevel, str]:
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
                return GrantLevel.NONE, ""
            data = resp.json()
            return parse_grant_level(data.get("grant_level")), data.get("lifecycle_state", "") or ""
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "grant authority unavailable (fail-closed deny): %s, trace_id=%s", exc, tid,
            )
            return GrantLevel.NONE, ""
