"""E0 collaboration grant client (Python) — resolves a (user, book) permission
against book-service, the single grant authority. Mirrors the Go ``grantclient``
SDK and the knowledge-service copy (E0-3).

book-service owns ``books`` + ``book_collaborators`` and exposes
``GET /internal/books/{book_id}/access?user_id=`` which always returns
200 ``{"grant_level": "none|view|edit|manage|owner", "lifecycle_state": ...}`` —
``none`` covers both a missing book and no-grant, so the endpoint is never an
existence oracle (E0 DESIGN R4).

Caching: a short-TTL cache stores ONLY positive grants (level > none) — a freshly
granted user is never stale-denied (``none`` is never cached, so the next call
re-fetches and sees the new grant), and a revoke takes effect within the TTL. v1
TTL is 45s (matches the Go SDK ``DefaultCacheTTL`` → uniform revoke SLA).

Fail-closed: any non-200 / transport error → ``GrantLevel.NONE`` (deny). Errors are
never cached. Never raises on a book-service outage; the gate layer (grant_deps)
maps a denied grant to 404/403.

NOTE (E0-4a): this is a 3rd copy of the SDK (Go + knowledge + here). Tracked for
extraction into a shared ``sdks/python/loreweave_grants`` after E0-4c, when all
three Python adopters can migrate at once — see D-E0-4-PY-GRANT-SDK-EXTRACT.
"""

import logging
import time
from enum import IntEnum
from uuid import UUID

import httpx

from .config import settings

__all__ = [
    "GrantLevel",
    "parse_grant_level",
    "GrantClient",
    "init_grant_client",
    "get_grant_client",
    "close_grant_client",
]

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_S = 45.0  # mirrors Go grantclient.DefaultCacheTTL
_TIMEOUT_S = 10.0


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


_client: "GrantClient | None" = None


class GrantClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = _TIMEOUT_S,
                 cache_ttl_s: float = DEFAULT_CACHE_TTL_S) -> None:
        self._base_url = base_url.rstrip("/")
        self._ttl = cache_ttl_s
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
        key = f"{user_id}:{book_id}"
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

    async def _fetch(self, book_id: UUID, user_id: UUID) -> tuple[GrantLevel, str]:
        url = f"{self._base_url}/internal/books/{book_id}/access"
        try:
            resp = await self._http.get(url, params={"user_id": str(user_id)})
            if resp.status_code != 200:
                logger.warning(
                    "grant authority %s returned %d (fail-closed deny)", url, resp.status_code,
                )
                return GrantLevel.NONE, ""
            data = resp.json()
            return parse_grant_level(data.get("grant_level")), data.get("lifecycle_state", "") or ""
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("grant authority unavailable (fail-closed deny): %s", exc)
            return GrantLevel.NONE, ""


def init_grant_client() -> "GrantClient":
    global _client
    if _client is not None:
        return _client
    _client = GrantClient(
        base_url=settings.book_service_internal_url,
        internal_token=settings.internal_service_token,
    )
    return _client


async def close_grant_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_grant_client() -> "GrantClient":
    if _client is None:
        return init_grant_client()
    return _client
