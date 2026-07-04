"""X2 — read-only client for the Knowledge Access Layer (KAL / knowledge-gateway).

The KAL (`services/knowledge-gateway`, FROZEN contract
`contracts/api/knowledge-gateway/kal.v1.yaml`) is the single versioned read/write
boundary for entity/lore/KG knowledge (INV-KAL). Consumers must read entity
knowledge through it rather than calling glossary-service / knowledge-service
`/internal/*` routes directly.

This client mirrors the sibling read clients (`glossary.py`, `knowledge.py`):
async httpx, internal-token + forwarded `X-User-Id` auth, typed errors (never a
bare httpx error), UTF-8/CJK-safe JSON on the wire (no ASCII-escape), graceful
typed empties left to the caller.

v1 semantics == today's current projection (latest-valid facts), so a migration
onto these reads is behavior-preserving; `as_of` is additive/optional.

Covered reads (kal.v1.yaml §reads):
  * roster(book)                — bounded-per-page, COMPLETE-in-aggregate cast
    (id+name); the caller DRAINS `next_cursor`. `roster()` here drains for you.
  * get_facts(entity, as_of?)   — latest-valid (or valid-at-N) facts.
  * get_canonical(entity, as_of?) — bounded canonical snapshot (degrade-safe).
  * search(query, k)            — bounded entity search (top-K).
  * timeline(entity, ...)       — windowed change history (one page).
  * neighborhood(entity, hops)  — KG 1-hop (capped); KG `as_of` gated per-substrate.

WRITES + extraction-writeback paths are NOT here — those remain on the owning
services' write surfaces (the KAL does own writes, but this consumer is read-only:
enrichment write-back goes through glossary `extract-entities` SSOT, never here).
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from loreweave_internal_client import InternalClientError, build_internal_client

from app.logging_config import trace_id_var

__all__ = [
    "RosterEntry",
    "KalFact",
    "CanonicalSnapshot",
    "KalServiceError",
    "KalClient",
]


# P3 SDK-first: subclass the shared InternalClientError (`.retryable` derived from
# `.status_code`); name kept so `except KalServiceError` sites are unchanged.
class KalServiceError(InternalClientError):
    """Raised on any KAL read failure. `retryable` flags transient conditions
    (timeout, 502/503/429) so the caller can degrade or retry."""


@dataclass(frozen=True)
class RosterEntry:
    entity_id: str
    name: str = ""
    kind: str = ""


@dataclass(frozen=True)
class KalFact:
    fact_id: str
    entity_id: str
    fact_kind: str
    attr_or_predicate: str
    value: str
    valid_from_ordinal: int = 0
    valid_to_ordinal: int | None = None
    cardinality: str = "single"


@dataclass(frozen=True)
class CanonicalSnapshot:
    entity_id: str
    content: str = ""
    as_of_ordinal: int | None = None
    canonical_status: str = "current"


# Safety cap for the roster drain: the roster is bounded-per-page and
# complete-in-aggregate, but a runaway/looping cursor must never spin forever.
# 500 pages * 500 max page size = 250k entities — far beyond any real cast.
_MAX_ROSTER_PAGES = 500


class KalClient:
    """Typed async read client for the KAL.

    `internal_token` authenticates service-to-service calls (`X-Internal-Token`).
    `user_id` is forwarded as `X-User-Id` so the KAL can enforce book/project
    View-gating on behalf of the originating user (kal.v1.yaml §Auth).
    """

    def __init__(
        self,
        *,
        base_url: str,
        internal_token: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        # W3 trace-uniformity: the shared factory bakes X-Internal-Token + JSON and
        # injects X-Trace-Id per request (this client had NO trace before). The
        # per-request X-User-Id tenancy header stays the caller's job (see _headers).
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, connect_timeout_s=5.0,
            trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── headers ──────────────────────────────────────────────────────────────

    def _headers(self, user_id: UUID | str | None) -> dict[str, str]:
        # X-Internal-Token is baked into the client; only the per-request X-User-Id
        # tenancy header (kal.v1.yaml §Auth) is added here (merged by httpx).
        if user_id is not None:
            return {"X-User-Id": str(user_id)}
        return {}

    # ── roster — bounded-per-page, COMPLETE-in-aggregate cast (drained) ───────

    async def roster(
        self,
        *,
        book_id: UUID,
        user_id: UUID | str | None = None,
        limit: int = 200,
    ) -> list[RosterEntry]:
        """Drain the KAL roster to completion: page by `next_cursor` until it is
        null (or the safety cap), accumulating the full id+name cast.

        The roster is a snapshot as-of drain-start (kal.v1.yaml §roster); entities
        created mid-drain may be omitted (tolerated by the caller). Projection is
        id+name (+ optional kind); never full attributes."""
        out: list[RosterEntry] = []
        cursor: str | None = None
        for _ in range(_MAX_ROSTER_PAGES):
            params: dict[str, str] = {"limit": str(limit)}
            if cursor:
                params["cursor"] = cursor
            resp = await self._get(
                f"{self._base}/v1/kal/books/{book_id}/roster",
                headers=self._headers(user_id),
                params=params,
            )
            data = resp.json()
            for r in _items(data):
                out.append(
                    RosterEntry(
                        entity_id=str(r.get("entity_id") or r.get("id") or ""),
                        name=str(r.get("name") or ""),
                        kind=str(r.get("kind") or ""),
                    )
                )
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                break
        return out

    # ── get_facts — latest-valid (or valid-at-N) facts ───────────────────────

    async def get_facts(
        self,
        *,
        book_id: UUID,
        entity_id: UUID | str,
        user_id: UUID | str | None = None,
        as_of: int | None = None,
        attrs: str | None = None,
    ) -> list[KalFact]:
        params: dict[str, str] = {}
        if as_of is not None:
            params["as_of"] = str(as_of)
        if attrs:
            params["attrs"] = attrs
        resp = await self._get(
            f"{self._base}/v1/kal/books/{book_id}/entities/{entity_id}/facts",
            headers=self._headers(user_id),
            params=params or None,
        )
        return [_fact(r) for r in _items(resp.json())]

    # ── get_canonical — bounded canonical snapshot ───────────────────────────

    async def get_canonical(
        self,
        *,
        book_id: UUID,
        entity_id: UUID | str,
        user_id: UUID | str | None = None,
        as_of: int | None = None,
    ) -> CanonicalSnapshot:
        params: dict[str, str] = {}
        if as_of is not None:
            params["as_of"] = str(as_of)
        resp = await self._get(
            f"{self._base}/v1/kal/books/{book_id}/entities/{entity_id}/canonical",
            headers=self._headers(user_id),
            params=params or None,
        )
        data = resp.json() if isinstance(resp.json(), dict) else {}
        return CanonicalSnapshot(
            entity_id=str(data.get("entity_id") or entity_id),
            content=str(data.get("content") or ""),
            as_of_ordinal=data.get("as_of_ordinal"),
            canonical_status=str(data.get("canonical_status") or "current"),
        )

    # ── search — bounded entity search (top-K) ───────────────────────────────

    async def search(
        self,
        *,
        book_id: UUID,
        query: str,
        user_id: UUID | str | None = None,
        k: int = 20,
    ) -> list[RosterEntry]:
        resp = await self._get(
            f"{self._base}/v1/kal/books/{book_id}/search",
            headers=self._headers(user_id),
            params={"query": query, "k": str(k)},
        )
        return [
            RosterEntry(
                entity_id=str(r.get("entity_id") or r.get("id") or ""),
                name=str(r.get("name") or ""),
                kind=str(r.get("kind") or ""),
            )
            for r in _items(resp.json())
        ]

    # ── timeline — one bounded page of the change feed ───────────────────────

    async def timeline(
        self,
        *,
        book_id: UUID,
        entity_id: UUID | str,
        user_id: UUID | str | None = None,
        before_order: int | None = None,
        after_order: int | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if before_order is not None:
            params["before_order"] = str(before_order)
        if after_order is not None:
            params["after_order"] = str(after_order)
        if cursor:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = str(limit)
        resp = await self._get(
            f"{self._base}/v1/kal/books/{book_id}/entities/{entity_id}/timeline",
            headers=self._headers(user_id),
            params=params or None,
        )
        data = resp.json()
        return data if isinstance(data, dict) else {"items": []}

    # ── neighborhood — KG 1-hop (capped) ─────────────────────────────────────

    async def neighborhood(
        self,
        *,
        book_id: UUID,
        entity_id: UUID | str,
        user_id: UUID | str | None = None,
        hops: int | None = None,
        cap: int | None = None,
        as_of: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if hops is not None:
            params["hops"] = str(hops)
        if cap is not None:
            params["cap"] = str(cap)
        if as_of is not None:
            params["as_of"] = str(as_of)
        resp = await self._get(
            f"{self._base}/v1/kal/books/{book_id}/entities/{entity_id}/neighborhood",
            headers=self._headers(user_id),
            params=params or None,
        )
        data = resp.json()
        return data if isinstance(data, dict) else {"edges": []}

    # ── transport (typed errors only, CJK-safe) ──────────────────────────────

    async def _get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            resp = await self._http.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise KalServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise KalServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code == 200:
            return resp
        detail = resp.text[:200]
        raise KalServiceError(
            f"GET {url} failed ({resp.status_code}): {detail}",
            status_code=resp.status_code,
        )


def _items(payload: Any) -> list[dict[str, Any]]:
    """KAL list reads return `{items: [...], ...}` (kal.v1.yaml). Normalize to a
    list of dicts; tolerate a bare list defensively."""
    if isinstance(payload, dict):
        val = payload.get("items")
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _fact(r: dict[str, Any]) -> KalFact:
    return KalFact(
        fact_id=str(r.get("fact_id") or ""),
        entity_id=str(r.get("entity_id") or ""),
        fact_kind=str(r.get("fact_kind") or ""),
        attr_or_predicate=str(r.get("attr_or_predicate") or ""),
        value=str(r.get("value") or ""),
        valid_from_ordinal=int(r.get("valid_from_ordinal") or 0),
        valid_to_ordinal=r.get("valid_to_ordinal"),
        cardinality=str(r.get("cardinality") or "single"),
    )
