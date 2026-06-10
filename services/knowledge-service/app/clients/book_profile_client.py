"""wiki-llm M1 (option A) — HTTP client for the lore-enrichment BookProfile.

The per-book de-bias profile (worldview / voice / era / language / anachronism
markers) is AUTHORED in lore-enrichment (it's an AI-domain artifact — LLM-suggested,
era-aware) and read here over the internal token to SHAPE the wiki-generation
prompt. This client follows the same graceful-degradation contract as
``BookClient``: every failure path returns a SAFE NEUTRAL default and logs a
warning — the caller (the wiki generator) never sees an exception and never
hard-fails generation because the profile service blipped. A neutral profile
shapes the prompt like a generic worldbuilder (never the hardcoded 封神 universe).

Caching (PO decision B, 2026-06-09): a TTL cache keyed by ``book_id``. A wiki-gen
job iterating N entities of one book makes ONE HTTP call (the rest are cache
hits), yet a profile EDITED mid-session is picked up on the next read after the
TTL expires. A FAILED read is deliberately NOT cached, so a transient
LE-unavailable (or a freshly recovered LE) is retried on the very next call
rather than pinned to neutral for the whole TTL window.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "BookProfile",
    "NEUTRAL_PROFILE",
    "BookProfileClient",
    "init_book_profile_client",
    "get_book_profile_client",
    "close_book_profile_client",
]

logger = logging.getLogger(__name__)


class BookProfile(BaseModel):
    """The de-bias profile fields the wiki prompt shapes on (frozen).

    Mirrors the subset of lore-enrichment's ``BookProfile`` that wiki generation
    consumes. ``anachronism_markers`` is a tuple of ``(term, reason)`` pairs;
    empty = the anachronism check is OFF. An UNSET book resolves to
    :data:`NEUTRAL_PROFILE` (language ``auto``, no era/worldview/markers).
    """

    model_config = ConfigDict(frozen=True)

    worldview: str = ""
    language: str = "auto"
    era_policy: str | None = None
    voice: str | None = None
    anachronism_markers: tuple[tuple[str, str], ...] = ()
    profile_source: str = "manual"

    @property
    def anachronism_enabled(self) -> bool:
        return len(self.anachronism_markers) > 0


#: The fallback for any book whose profile can't be read (unset, or LE down).
#: A generic worldbuilder — never the hardcoded 封神 / 商周 default.
NEUTRAL_PROFILE = BookProfile()


def _parse_markers(raw: Any) -> tuple[tuple[str, str], ...]:
    """Parse the ``[{term, reason}, ...]`` JSON into ``(term, reason)`` pairs.

    Tolerant of the LE view shape (a list of objects) and degrades to empty on
    anything malformed — a bad marker list must never break generation."""
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("term"):
            out.append((str(item["term"]), str(item.get("reason", ""))))
        elif isinstance(item, (list, tuple)) and len(item) >= 1 and item[0]:
            out.append((str(item[0]), str(item[1]) if len(item) > 1 else ""))
    return tuple(out)


def _profile_from_payload(data: Any) -> BookProfile:
    """Build a :class:`BookProfile` from the LE internal GET body. Tolerant: any
    missing/odd field falls back to its neutral default (never raises)."""
    if not isinstance(data, dict):
        return NEUTRAL_PROFILE
    return BookProfile(
        worldview=str(data.get("worldview") or ""),
        language=str(data.get("language") or "auto"),
        era_policy=data.get("era_policy") if data.get("era_policy") else None,
        voice=data.get("voice") if data.get("voice") else None,
        anachronism_markers=_parse_markers(data.get("anachronism_markers")),
        profile_source=str(data.get("profile_source") or "manual"),
    )


_client: "BookProfileClient | None" = None


class BookProfileClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float,
        cache_ttl_s: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )
        self._cache_ttl_s = cache_ttl_s
        # book_id -> (expiry_monotonic, profile). Only SUCCESSFUL reads are
        # cached; a failure returns neutral without populating the cache.
        self._cache: dict[UUID, tuple[float, BookProfile]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_profile(self, book_id: UUID) -> BookProfile:
        """Resolve a book's de-bias profile (cached for the TTL), or
        :data:`NEUTRAL_PROFILE` on any failure.

        Cache hit (unexpired) → no HTTP call. Miss/expired → fetch; cache the
        result on success. A non-200 / transport error / bad body → neutral,
        NOT cached, so the next call retries (an edited or recovered profile is
        picked up promptly — PO decision B). Concurrent first reads of the same
        book may briefly double-fetch (no lock); harmless and self-correcting.
        """
        now = time.monotonic()
        cached = self._cache.get(book_id)
        if cached is not None and cached[0] > now:
            return cached[1]

        url = f"{self._base_url}/internal/lore-enrichment/books/{book_id}/profile"
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url, headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning(
                    "lore-enrichment %s returned %d, trace_id=%s",
                    url, resp.status_code, tid,
                )
                return NEUTRAL_PROFILE
            profile = _profile_from_payload(resp.json())
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "lore-enrichment unavailable fetching book profile: %s trace_id=%s",
                exc, tid,
            )
            return NEUTRAL_PROFILE
        self._cache[book_id] = (now + self._cache_ttl_s, profile)
        return profile


def init_book_profile_client() -> "BookProfileClient":
    global _client
    if _client is not None:
        return _client
    _client = BookProfileClient(
        base_url=settings.lore_enrichment_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.lore_enrichment_client_timeout_s,
        cache_ttl_s=settings.book_profile_cache_ttl_s,
    )
    return _client


async def close_book_profile_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_book_profile_client() -> "BookProfileClient":
    if _client is None:
        return init_book_profile_client()
    return _client
