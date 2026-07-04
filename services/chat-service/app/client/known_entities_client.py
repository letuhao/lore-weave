"""T5 (Context Budget Law D2/A3) — known-entities client for the intent gate.

Fetches a book's known-entity token set (entity names + aliases) from
glossary-service's internal route and caches it in-process (A3: no new table).
The entity-presence gate (`app.services.entity_presence`) reads this set to decide
whether a turn references book lore → whether the expensive grounding pull is worth
running.

Graceful degradation is the contract (mirrors book_steering_client): EVERY failure
returns an EMPTY set and never raises into the turn. The gate treats an empty set as
"cannot tell → open the gate" (bias-to-include), so a glossary outage makes turns a
touch more expensive but never wrong.

Cache: book_id → (expiry_monotonic, frozenset). Only SUCCESSES are cached (a
transient failure self-heals on the next turn instead of being pinned as empty). TTL
from settings; invalidated implicitly by expiry (a glossary edit shows up within one
TTL — acceptable for a heuristic gate).
"""
from __future__ import annotations

import logging
import time

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "KnownEntitiesClient",
    "init_known_entities_client",
    "close_known_entities_client",
    "get_known_entities_client",
]


def _tokens_from_rows(rows: list) -> frozenset[str]:
    """Build the lowercased name+alias token set from the route's rows.
    Shape: [{entity_id, name, kind_code, aliases:[...], frequency}]."""
    toks: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = r.get("name")
        if isinstance(name, str) and name.strip():
            toks.add(name.strip().lower())
        aliases = r.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str) and a.strip():
                    toks.add(a.strip().lower())
    return frozenset(toks)


class KnownEntitiesClient:
    """Thin async wrapper + in-process TTL cache. One instance per process."""

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 2.0,
        cache_ttl_s: float = 300.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ttl = cache_ttl_s
        self._cache: dict[str, tuple[float, frozenset[str]]] = {}
        client_kwargs: dict = {
            "timeout": httpx.Timeout(timeout_s),
            "headers": {"X-Internal-Token": internal_token},
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**client_kwargs)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _cached(self, book_id: str) -> frozenset[str] | None:
        hit = self._cache.get(book_id)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        return None

    async def get_known_entity_tokens(self, book_id: str) -> frozenset[str]:
        """The book's name+alias token set (lowercased). ``frozenset()`` on ANY
        failure (the gate reads empty as bias-to-include). Cached per TTL."""
        if not book_id:
            return frozenset()
        cached = self._cached(book_id)
        if cached is not None:
            return cached
        url = f"{self._base_url}/internal/books/{book_id}/known-entities"
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        # audit MED-4: widen the vocabulary for GATE purposes. The route defaults
        # (min_frequency=2, limit=50) exist for extraction-prompt context, but for the
        # gate a false-negative (missing a real entity → wrongly gating out its turn) is
        # worse than a slightly larger token set. min_frequency=1 catches a just-
        # introduced character; limit=500 (the route's cap) covers a large book's cast.
        params = {"min_frequency": 1, "limit": 500}
        try:
            resp = await self._http.get(url, params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise
            logger.warning("known-entities unavailable for book %s: %s", book_id, type(exc).__name__)
            return frozenset()
        if resp.status_code != 200:
            logger.warning("known-entities %d for book %s", resp.status_code, book_id)
            return frozenset()
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("known-entities decode failure for book %s: %s", book_id, exc)
            return frozenset()
        rows = data if isinstance(data, list) else data.get("items") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            logger.warning("known-entities unexpected shape for book %s", book_id)
            return frozenset()
        tokens = _tokens_from_rows(rows)
        self._cache[book_id] = (time.monotonic() + self._ttl, tokens)
        return tokens


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: KnownEntitiesClient | None = None


def init_known_entities_client() -> KnownEntitiesClient:
    """Instantiate the shared client from settings. Idempotent."""
    global _client
    if _client is not None:
        return _client
    _client = KnownEntitiesClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.known_entities_timeout_s,
        cache_ttl_s=settings.known_entities_cache_ttl_s,
    )
    return _client


async def close_known_entities_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_known_entities_client() -> KnownEntitiesClient:
    """Lazy accessor — initialises on first use if lifespan didn't."""
    global _client
    if _client is None:
        return init_known_entities_client()
    return _client
