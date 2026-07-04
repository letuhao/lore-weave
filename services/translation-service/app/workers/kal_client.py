"""KAL client for Translation Pipeline (X5 — temporal-knowledge fanout).

The KAL (Knowledge Access Layer, `services/knowledge-gateway`) is the SINGLE
versioned read/write boundary for entity/lore knowledge — contract frozen at
`contracts/api/knowledge-gateway/kal.v1.yaml`. INV-KAL: a consumer reads the
entity-knowledge the KAL covers (facts / canonical) THROUGH this gateway, never
the owning services' `/internal/*` knowledge endpoints directly.

This module wraps the two bounded entity-knowledge READS translation uses:

  - ``get_facts``     → GET /v1/kal/books/{book}/entities/{entity}/facts
  - ``get_canonical`` → GET /v1/kal/books/{book}/entities/{entity}/canonical

## As-of-N (story time, spec §6B)
Both reads take an OPTIONAL ``as_of`` chapter ordinal. When translating chapter
N, the entity knowledge injected as context should reflect the story state AS OF
chapter N — NOT the latest head, which would leak future spoilers into earlier
chapters. ``as_of`` omitted = current head (today's behavior, unchanged). The KAL
gates ``as_of`` per substrate and returns a ``temporal_capability`` (the glossary
projection honors ordinal valid-time; the KG is ``temporal_unsupported`` pre-F3).

## Immutable-once cache (spec §12.1 / D8)
The as-of-N knowledge for a (content, as_of) pair is IMMUTABLE: once the chapter's
bounded-unit content hash and the as-of ordinal are fixed, the facts/canonical
valid at that ordinal cannot change. So a re-translation of unchanged content
reuses the cached knowledge instead of re-hitting the KAL. The cache key is
``(book_id, entity_id, content_hash, as_of, kind)`` — content-addressed exactly
like the raw-output extraction cache (``extraction_cache.RawCacheKey``). It is a
small in-process LRU (best-effort; a miss just re-fetches).

## Safety gates (mirrors ``knowledge_client``)
  - **Null (feature off):** ``knowledge_gateway_url`` unset → empty result, NO
    HTTP call. Default behavior is therefore byte-identical to pre-X5.
  - **Degrade-to-empty:** any non-200 / transport / malformed body → empty result.
    Knowledge enrichment must NEVER fail a translation.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field

from loreweave_internal_client import build_internal_client

from ..config import settings

log = logging.getLogger(__name__)

_KAL_FETCH_TIMEOUT = 5.0  # seconds — mirrors knowledge_client


@dataclass
class Fact:
    """One bounded entity fact (kal.v1.yaml Fact schema, faithfully parsed)."""
    attr_or_predicate: str
    value: str
    fact_kind: str = ""
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None  # None = +∞ (open)
    cardinality: str = "single"


@dataclass
class FactsResult:
    """The bounded ``get_facts`` result + the KAL's per-substrate temporal capability.

    ``temporal_capability`` echoes whether ``as_of`` was actually honored for the
    glossary substrate (``ordinal_valid_time``) or only the current projection was
    available (``current_only``) — a degrade-safe signal (§12.5.1 / A5), not an error.
    """
    items: list[Fact] = field(default_factory=list)
    temporal_capability: dict = field(default_factory=dict)
    found: bool = False

    @classmethod
    def empty(cls) -> "FactsResult":
        return cls(found=False)


@dataclass
class CanonicalSnapshot:
    """The bounded ``get_canonical`` prose snapshot (kal.v1.yaml CanonicalSnapshot).

    ``canonical_status`` may be ``unbuildable`` (degrade-safe, §12.1 B4) — the
    caller then falls back to ``get_facts``. ``found`` is False when the feature is
    off / the read failed / no snapshot exists.
    """
    content: str = ""
    as_of_ordinal: int | None = None
    canonical_status: str = ""
    found: bool = False

    @classmethod
    def empty(cls) -> "CanonicalSnapshot":
        return cls(found=False)


# ── immutable-once cache (§12.1 / D8) ─────────────────────────────────────────
# Content-addressed: a (book, entity, content_hash, as_of, kind) tuple is immutable
# once content + as_of are fixed, so a re-translation of unchanged content reuses it.
# A bounded in-process LRU — best-effort, like extraction_cache. NOT cross-tenant
# unsafe: the key is per book/entity and the value is the same bounded knowledge any
# reader of that (content, as_of) would get; no user-private projection rides here.
_CACHE_MAX = 2048
_cache: "OrderedDict[tuple, object]" = OrderedDict()


def _cache_get(key: tuple):
    """LRU get; promotes on hit. Returns the sentinel-free value or None on miss."""
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_put(key: tuple, value: object) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def clear_cache() -> None:
    """Drop the immutable-once cache (test isolation / explicit invalidation)."""
    _cache.clear()


def _headers(user_id: str | None) -> dict:
    """The per-request X-User-Id tenancy header (KAL auth §). W5: X-Internal-Token
    is now baked into the client by build_internal_client; httpx merges this in."""
    return {"X-User-Id": user_id} if user_id else {}


def _parse_fact(raw: dict) -> Fact | None:
    if not isinstance(raw, dict):
        return None
    attr = raw.get("attr_or_predicate")
    if not attr:
        return None

    def _ord(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return Fact(
        attr_or_predicate=str(attr),
        value=str(raw.get("value", "")),
        fact_kind=str(raw.get("fact_kind", "")),
        valid_from_ordinal=_ord(raw.get("valid_from_ordinal")),
        valid_to_ordinal=_ord(raw.get("valid_to_ordinal")),
        cardinality=str(raw.get("cardinality", "single")),
    )


async def get_facts(
    book_id: str,
    entity_id: str,
    *,
    as_of: int | None = None,
    user_id: str | None = None,
    attrs: list[str] | None = None,
) -> FactsResult:
    """Fetch an entity's latest-valid (or valid-at-``as_of``) facts via the KAL.

    Calls: GET {kal}/v1/kal/books/{book_id}/entities/{entity_id}/facts
           ?as_of=N&attrs=a,b   (both optional)

    ``as_of`` omitted = current head (today's behavior). Immutable-once cached on
    ``(book, entity, content_hash, as_of, attrs)`` only when ``content_hash`` is
    supplied via ``get_facts_cached``; this raw fetch always hits the KAL.

    Returns a populated ``FactsResult`` on success, or an empty one when the feature
    is off (no URL) or on any failure. Never raises (best-effort enrichment)."""
    if not settings.knowledge_gateway_url:
        return FactsResult.empty()

    params: dict[str, str] = {}
    if as_of is not None:
        params["as_of"] = str(as_of)
    if attrs:
        params["attrs"] = ",".join(attrs)

    try:
        async with build_internal_client(settings.knowledge_gateway_url, internal_token=settings.internal_service_token, timeout_s=_KAL_FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.knowledge_gateway_url}"
                f"/v1/kal/books/{book_id}/entities/{entity_id}/facts",
                params=params,
                headers=_headers(user_id),
            )
            if resp.status_code != 200:
                log.warning(
                    "kal get_facts returned %d for entity=%s — no facts context",
                    resp.status_code, entity_id,
                )
                return FactsResult.empty()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — best-effort; cancel still propagates
        log.warning(
            "kal get_facts failed for entity=%s: %s — no facts context",
            entity_id, exc,
        )
        return FactsResult.empty()

    raw_items = payload.get("items", []) if isinstance(payload, dict) else []
    items = [f for f in (_parse_fact(r) for r in raw_items) if f is not None]
    cap = payload.get("temporal_capability", {}) if isinstance(payload, dict) else {}
    return FactsResult(
        items=items,
        temporal_capability=cap if isinstance(cap, dict) else {},
        found=True,
    )


async def get_canonical(
    book_id: str,
    entity_id: str,
    *,
    as_of: int | None = None,
    user_id: str | None = None,
) -> CanonicalSnapshot:
    """Fetch an entity's bounded canonical snapshot via the KAL (current or as-of N).

    Calls: GET {kal}/v1/kal/books/{book_id}/entities/{entity_id}/canonical?as_of=N

    ``as_of`` omitted = current head. May carry ``canonical_status='unbuildable'``
    (degrade-safe, §12.1 B4) — the caller falls back to ``get_facts``. Returns a
    populated ``CanonicalSnapshot`` on success, or an empty one when the feature is
    off / no snapshot / any failure. Never raises."""
    if not settings.knowledge_gateway_url:
        return CanonicalSnapshot.empty()

    params: dict[str, str] = {}
    if as_of is not None:
        params["as_of"] = str(as_of)

    try:
        async with build_internal_client(settings.knowledge_gateway_url, internal_token=settings.internal_service_token, timeout_s=_KAL_FETCH_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.knowledge_gateway_url}"
                f"/v1/kal/books/{book_id}/entities/{entity_id}/canonical",
                params=params,
                headers=_headers(user_id),
            )
            if resp.status_code != 200:
                log.warning(
                    "kal get_canonical returned %d for entity=%s — no canonical context",
                    resp.status_code, entity_id,
                )
                return CanonicalSnapshot.empty()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — best-effort
        log.warning(
            "kal get_canonical failed for entity=%s: %s — no canonical context",
            entity_id, exc,
        )
        return CanonicalSnapshot.empty()

    if not isinstance(payload, dict):
        return CanonicalSnapshot.empty()

    raw_ord = payload.get("as_of_ordinal")
    try:
        as_of_ord = int(raw_ord) if raw_ord is not None else None
    except (TypeError, ValueError):
        as_of_ord = None
    return CanonicalSnapshot(
        content=str(payload.get("content", "") or ""),
        as_of_ordinal=as_of_ord,
        canonical_status=str(payload.get("canonical_status", "")),
        found=True,
    )


# ── immutable-once cached variants (§12.1 / D8) ───────────────────────────────


async def get_canonical_cached(
    book_id: str,
    entity_id: str,
    *,
    content_hash: str,
    as_of: int | None = None,
    user_id: str | None = None,
) -> CanonicalSnapshot:
    """``get_canonical`` with the immutable-once cache (spec §12.1 / D8).

    Keyed on ``(book, entity, content_hash, as_of)``: once the chapter's content hash
    and the as-of ordinal are fixed, the canonical valid at that ordinal is immutable,
    so a re-translation of unchanged content reuses the cached snapshot. A cache miss
    fetches via the KAL and stores it; a feature-off / failure result is NOT cached
    (so enabling the feature / a transient recovery is picked up on the next read)."""
    key = ("canonical", book_id, entity_id, content_hash, as_of)
    hit = _cache_get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    snap = await get_canonical(book_id, entity_id, as_of=as_of, user_id=user_id)
    # Capability guard for the as_of path: the snapshot carries no temporal_capability, but a
    # DEGRADE (status != 'current' — the canon-content fallback) is the CURRENT authored canon,
    # NOT the as-of-N fold. Caching that under an as_of key would pin current-state content (a
    # spoiler) at a past ordinal. So for an as_of read, cache only a real fold ('current'); a
    # head read (as_of is None) caches regardless (current-state is correct there).
    cacheable = as_of is None or snap.canonical_status == "current"
    if snap.found and cacheable:
        _cache_put(key, snap)
    return snap


async def get_facts_cached(
    book_id: str,
    entity_id: str,
    *,
    content_hash: str,
    as_of: int | None = None,
    user_id: str | None = None,
    attrs: list[str] | None = None,
) -> FactsResult:
    """``get_facts`` with the immutable-once cache (spec §12.1 / D8).

    Keyed on ``(book, entity, content_hash, as_of, attrs)`` — see
    ``get_canonical_cached`` for the immutability rationale. Only a ``found`` result
    is cached."""
    attr_key = ",".join(sorted(attrs)) if attrs else ""
    key = ("facts", book_id, entity_id, content_hash, as_of, attr_key)
    hit = _cache_get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    res = await get_facts(book_id, entity_id, as_of=as_of, user_id=user_id, attrs=attrs)
    # Capability guard: a result keyed by as_of=N is only IMMUTABLE if the substrate actually
    # HONORED the as_of. If the glossary substrate fell back to the current projection (capability
    # != ordinal_valid_time), the value is the HEAD facts, NOT the as-of-N facts — caching it under
    # the as_of key would serve a spoiler/stale snapshot once the substrate becomes temporal. Cache
    # only an honored as_of (or a head read, as_of is None).
    honored = as_of is None or res.temporal_capability.get("glossary") == "ordinal_valid_time"
    if res.found and honored:
        _cache_put(key, res)
    return res
