"""Knowledge client for Translation Pipeline V3 (M4a).

Fetches an entity's 1-hop relation neighbourhood from knowledge-service so the
V3 pipeline can render context-correct pronouns/honorifics (who outranks/relates
to whom → 你/您, anh/em/ngài). The design's `memory_recall_entity` is MCP-only;
this uses the equivalent **internal-HTTP** route `POST /internal/knowledge/
wiki-neighborhood`, keyed by `glossary_entity_id` (which translation already has
from the glossary layer) — so no project-namespace bridge is needed.

Mirrors `glossary_client` conventions: a plain async fetch + dataclasses +
graceful degradation. Two safety gates:
  - **Null (feature off):** when `knowledge_service_internal_url` is unset, return
    an empty neighbourhood without any HTTP call.
  - **Degrade-to-empty:** any non-200 / transport error → empty neighbourhood;
    knowledge enrichment must never fail a translation.

Parsing is faithful — `confidence` and `pending_validation` are preserved so the
M4b brief-builder can apply the §11.2 trust ladder (lock vs. hint). This module
does NOT filter or inject; it only fetches + parses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from ..config import settings

log = logging.getLogger(__name__)

_KNOWLEDGE_FETCH_TIMEOUT = 5.0  # seconds
_DEFAULT_REL_CAP = 200


@dataclass
class Relation:
    """A single 1-hop relation edge for an entity."""
    predicate: str
    subject_name: str | None
    subject_kind: str | None
    object_name: str | None
    object_kind: str | None
    confidence: float
    pending_validation: bool
    source_type: str  # "glossary" | "enriched"


@dataclass
class WikiNeighborhood:
    """An entity's 1-hop relation neighbourhood from knowledge-service."""
    found: bool = False
    glossary_entity_id: str = ""
    name: str | None = None
    kind: str | None = None
    relations: list[Relation] = field(default_factory=list)
    truncated: bool = False
    # Entity-level trust signals (§11.2 ladder): TRUST 1 = entity anchored in
    # glossary (source_types ∋ 'glossary' / entity_source_type == 'glossary').
    # Kept so M4b can lock vs. hint at the entity level, not just per-relation.
    source_types: list[str] = field(default_factory=list)
    entity_source_type: str = ""

    @classmethod
    def empty(cls, glossary_entity_id: str = "") -> "WikiNeighborhood":
        return cls(found=False, glossary_entity_id=glossary_entity_id)


def _parse_relation(raw: dict) -> Relation:
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return Relation(
        predicate=str(raw.get("predicate", "")),
        subject_name=raw.get("subject_name"),
        subject_kind=raw.get("subject_kind"),
        object_name=raw.get("object_name"),
        object_kind=raw.get("object_kind"),
        confidence=confidence,
        pending_validation=bool(raw.get("pending_validation", False)),
        source_type=str(raw.get("source_type", "")),
    )


def _parse_neighborhood(payload: dict, glossary_entity_id: str) -> WikiNeighborhood:
    relations = [
        _parse_relation(r) for r in payload.get("relations", []) if isinstance(r, dict)
    ]
    raw_source_types = payload.get("source_types", [])
    source_types = [str(s) for s in raw_source_types] if isinstance(raw_source_types, list) else []
    return WikiNeighborhood(
        found=bool(payload.get("found", False)),
        glossary_entity_id=str(payload.get("glossary_entity_id", glossary_entity_id)),
        name=payload.get("name"),
        kind=payload.get("kind"),
        relations=relations,
        truncated=bool(payload.get("relations_truncated", False)),
        source_types=source_types,
        entity_source_type=str(payload.get("entity_source_type", "")),
    )


async def fetch_wiki_neighborhood(
    user_id: str,
    glossary_entity_id: str,
    rel_cap: int = _DEFAULT_REL_CAP,
) -> WikiNeighborhood:
    """Fetch an entity's 1-hop relation neighbourhood from knowledge-service.

    Calls: POST {knowledge}/internal/knowledge/wiki-neighborhood

    Returns a populated ``WikiNeighborhood`` on success, or an empty one when the
    feature is off (no URL configured) or on any failure. Never raises.
    """
    if not settings.knowledge_service_internal_url:
        # Null port — feature off / local dev. No HTTP call.
        return WikiNeighborhood.empty(glossary_entity_id)

    try:
        async with httpx.AsyncClient(timeout=_KNOWLEDGE_FETCH_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.knowledge_service_internal_url}"
                f"/internal/knowledge/wiki-neighborhood",
                json={
                    "user_id": user_id,
                    "glossary_entity_id": glossary_entity_id,
                    "rel_cap": rel_cap,
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "wiki-neighborhood returned %d for entity=%s — no knowledge context",
                    resp.status_code, glossary_entity_id,
                )
                return WikiNeighborhood.empty(glossary_entity_id)
            return _parse_neighborhood(resp.json(), glossary_entity_id)
    except Exception as exc:
        log.warning(
            "wiki-neighborhood fetch failed for entity=%s: %s — no knowledge context",
            glossary_entity_id, exc,
        )
        return WikiNeighborhood.empty(glossary_entity_id)


# ── M4d-1: timeline (cross-chapter "story so far" memo) ───────────────────────

_DEFAULT_TIMELINE_LIMIT = 25


@dataclass
class TimelineEvent:
    """One narrative event up to the reading position."""
    title: str
    summary: str | None
    event_date: str | None
    participants: list[str] = field(default_factory=list)


@dataclass
class TimelineBrief:
    """Recent story events before the chapter being translated. ``found`` is
    False when the book has no knowledge project (cold start)."""
    found: bool = False
    events: list[TimelineEvent] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "TimelineBrief":
        return cls(found=False)


def _parse_timeline_event(raw: dict) -> TimelineEvent:
    parts = raw.get("participants", [])
    participants = [str(p) for p in parts] if isinstance(parts, list) else []
    return TimelineEvent(
        title=str(raw.get("title", "")),
        summary=raw.get("summary"),
        event_date=raw.get("event_date"),
        participants=participants,
    )


async def fetch_timeline(
    book_id: str,
    chapter_order: int,
    limit: int = _DEFAULT_TIMELINE_LIMIT,
) -> TimelineBrief:
    """Fetch recent narrative events before ``chapter_order`` from knowledge-service.

    Calls: POST {knowledge}/internal/knowledge/timeline

    ``chapter_order`` is the book-service global chapter ``sort_order`` (the
    reading position knowledge's ``event_order`` is keyed on) — NOT the job-local
    ``chapter_index``. The endpoint resolves project + owner tenant from
    ``book_id`` server-side, so translation passes only ``book_id`` + the reading
    position. Returns a populated ``TimelineBrief`` on success, or an empty one
    when the feature is off (no URL) or on any failure. Never raises.
    """
    if not settings.knowledge_service_internal_url:
        return TimelineBrief.empty()

    try:
        async with httpx.AsyncClient(timeout=_KNOWLEDGE_FETCH_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.knowledge_service_internal_url}"
                f"/internal/knowledge/timeline",
                json={
                    "book_id": book_id,
                    "chapter_order": chapter_order,
                    "limit": limit,
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
            if resp.status_code != 200:
                log.warning(
                    "timeline returned %d for book=%s — no timeline context",
                    resp.status_code, book_id,
                )
                return TimelineBrief.empty()
            payload = resp.json()
            events = [
                _parse_timeline_event(e)
                for e in payload.get("events", []) if isinstance(e, dict)
            ]
            return TimelineBrief(found=bool(payload.get("found", False)), events=events)
    except Exception as exc:
        log.warning(
            "timeline fetch failed for book=%s: %s — no timeline context",
            book_id, exc,
        )
        return TimelineBrief.empty()
