"""K11.7 — events repository.

Functions over `:Event` nodes — discrete narrative events
extracted from chapters or chat. Same idempotency pattern as
K11.5a entities and K11.6 relations: a deterministic id derived
from `(user_id, project_id, chapter_id, normalized_title)`
makes re-extraction a no-op.

Two temporal axes per KSA §3.4 + the K11.3 schema indexes:
  - `event_order` — narrative position (the order events appear
    in the text). Indexed via `event_user_order`. Used by the L4
    timeline retrieval.
  - `chronological_order` — in-story chronology (the order
    events happened from the characters' POV). Optional, no
    index in the K11.3 schema; useful for flashback / non-linear
    narratives.

`chapter_id` is the K11.3-indexed cascade key — partial
re-extraction of a chapter starts by deleting that chapter's
events via the `event_user_chapter` index.

Reference: KSA §3.4 (Event/Fact nodes), K11.3 schema indexes
event_user_order, event_user_chapter, event_user_evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.canonical import canonicalize_text

logger = logging.getLogger(__name__)

__all__ = [
    "Event",
    "event_id",
    "merge_event",
    "get_event",
    "list_events_for_chapter",
    "list_events_in_order",
    "delete_events_with_zero_evidence",
]


def event_id(
    user_id: str,
    project_id: str | None,
    chapter_id: str | None,
    title: str,
) -> str:
    """Deterministic id for an `:Event` node.

    Same `(user_id, project_id, chapter_id, normalized_title)`
    tuple produces the same id, forever. Re-extracting the same
    event from the same chapter is a no-op against the K11.7
    repo. Title normalization uses `canonicalize_text` (lower +
    collapse whitespace + strip punctuation) so cosmetic edits
    don't fork the node.

    Two events with the same title in the same chapter collapse
    to one node — by design. If you actually mean two distinct
    events (e.g., "Kai duels Zhao" appears twice in chapter 12,
    once early and once late), differentiate them by appending a
    distinguishing suffix to the title at extraction time.
    """
    if not user_id:
        raise ValueError("user_id is required for event_id")
    if not title:
        raise ValueError("title is required for event_id")
    canonical = canonicalize_text(title)
    if not canonical:
        raise ValueError(
            f"title {title!r} canonicalizes to empty string — cannot derive id"
        )
    key = (
        f"v1:{user_id}:{project_id or 'global'}:"
        f"{chapter_id or '_nochapter_'}:{canonical}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Event(BaseModel):
    """Pydantic projection of an `:Event` node."""

    id: str
    user_id: str
    project_id: str | None = None
    title: str
    canonical_title: str
    summary: str | None = None
    chapter_id: str | None = None
    event_order: int | None = None
    chronological_order: int | None = None
    participants: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    source_types: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    mention_count: int = 0
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_event(node: Any) -> Event:
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return Event.model_validate(data)


# ── merge_event ───────────────────────────────────────────────────────


_MERGE_EVENT_CYPHER = """
MERGE (e:Event {id: $id})
ON CREATE SET
  e.user_id = $user_id,
  e.project_id = $project_id,
  e.title = $title,
  e.canonical_title = $canonical_title,
  e.summary = $summary,
  e.chapter_id = $chapter_id,
  e.event_order = $event_order,
  e.chronological_order = $chronological_order,
  e.participants = $participants,
  e.confidence = $confidence,
  e.source_types = [$source_type],
  e.evidence_count = 0,
  e.mention_count = 0,
  e.archived_at = NULL,
  e.created_at = datetime(),
  e.updated_at = datetime()
ON MATCH SET
  e.summary = coalesce($summary, e.summary),
  e.event_order = coalesce($event_order, e.event_order),
  e.chronological_order = coalesce($chronological_order, e.chronological_order),
  e.participants = CASE
    WHEN size($participants) = 0 THEN e.participants
    ELSE e.participants + [p IN $participants WHERE NOT p IN e.participants]
  END,
  e.source_types = CASE
    WHEN $source_type IN e.source_types THEN e.source_types
    ELSE e.source_types + $source_type
  END,
  e.confidence = CASE
    WHEN $confidence > e.confidence THEN $confidence
    ELSE e.confidence
  END,
  e.updated_at = datetime()
WITH e
WHERE e.user_id = $user_id
RETURN e
"""


async def merge_event(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    title: str,
    summary: str | None = None,
    chapter_id: str | None = None,
    event_order: int | None = None,
    chronological_order: int | None = None,
    participants: list[str] | None = None,
    source_type: str = "book_content",
    confidence: float = 0.0,
) -> Event:
    """Idempotent upsert. Same (user, project, chapter, title)
    returns the same node.

    Multi-source semantics mirror K11.5a `merge_entity`:
      - `source_types` accumulates distinct sources
      - `confidence` is max across calls
      - `participants` union-merges (no duplicates)
      - `summary` / `event_order` / `chronological_order` upgrade
        from NULL but do NOT overwrite existing values (first
        write wins for those — extraction shouldn't second-guess
        a confirmed timestamp)

    The participants merge uses a list-comprehension dedup
    instead of `apoc.coll.union` so the schema runner has no APOC
    dependency on the merge path. APOC is loaded for vector
    indexes but we keep query code APOC-free.

    K11.7-R1 normalizations:
      - R1: `participants` is order-preserving deduped in
        Python before being passed to Cypher. The ON MATCH branch
        already deduped against the existing list, but ON CREATE
        stored the raw input — so a sloppy SVO extractor passing
        `["a", "a", "b"]` would have landed `["a", "a", "b"]` on
        first write.
      - R3: `source_type` validated non-empty so trash like `""`
        can't enter the `source_types` accumulator.
      - R4: `summary` empty-string normalized to None so the
        ON MATCH `coalesce($summary, e.summary)` treats it as
        "no new value" rather than wiping the stored summary.
    """
    if not title:
        raise ValueError("title must be a non-empty string")
    if not source_type:
        raise ValueError("source_type must be a non-empty string")
    eid = event_id(
        user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        title=title,
    )
    canonical_title = canonicalize_text(title)
    # R1: order-preserving dedup. dict.fromkeys preserves insert
    # order in Python 3.7+, which is also Cypher list traversal
    # order, so the first-spotted entity stays at index 0.
    deduped_participants = list(dict.fromkeys(participants or []))
    # R4: empty string → None so coalesce in Cypher treats it as
    # "no new value", not "deliberate clear".
    normalized_summary = summary or None
    result = await run_write(
        session,
        _MERGE_EVENT_CYPHER,
        user_id=user_id,
        id=eid,
        project_id=project_id,
        title=title,
        canonical_title=canonical_title,
        summary=normalized_summary,
        chapter_id=chapter_id,
        event_order=event_order,
        chronological_order=chronological_order,
        participants=deduped_participants,
        source_type=source_type,
        confidence=confidence,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(
            f"merge_event returned no row for id={eid!r}"
        )
    return _node_to_event(record["e"])


# ── get_event ─────────────────────────────────────────────────────────


_GET_EVENT_CYPHER = """
MATCH (e:Event {id: $id})
WHERE e.user_id = $user_id
RETURN e
"""


async def get_event(
    session: CypherSession,
    *,
    user_id: str,
    event_id: str,
) -> Event | None:
    if not event_id:
        raise ValueError("event_id must be a non-empty string")
    result = await run_read(
        session,
        _GET_EVENT_CYPHER,
        user_id=user_id,
        id=event_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_event(record["e"])


# ── list_events_for_chapter ───────────────────────────────────────────


# Uses the K11.3 `event_user_chapter` index — bounded by the
# chapter's event count, not the full graph.
_LIST_EVENTS_FOR_CHAPTER_CYPHER = """
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND e.chapter_id = $chapter_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND ($include_archived OR e.archived_at IS NULL)
RETURN e
ORDER BY coalesce(e.event_order, 2147483647), e.title ASC
LIMIT $limit
"""


async def list_events_for_chapter(
    session: CypherSession,
    *,
    user_id: str,
    chapter_id: str,
    project_id: str | None = None,
    include_archived: bool = False,
    limit: int = 200,
) -> list[Event]:
    """All events for a chapter, ordered by `event_order`
    (narrative position), nulls last (sentinel = max int32).

    K11.7-R1/R2: optional `project_id` filter. Chapter ids are
    usually globally unique, but two projects under the same
    user can collide via test fixtures or sloppy import paths.
    Pass `project_id` when the caller knows which project the
    chapter belongs to; consistent with `list_events_in_order`.
    """
    if not chapter_id:
        raise ValueError("chapter_id must be a non-empty string")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    result = await run_read(
        session,
        _LIST_EVENTS_FOR_CHAPTER_CYPHER,
        user_id=user_id,
        chapter_id=chapter_id,
        project_id=project_id,
        include_archived=include_archived,
        limit=limit,
    )
    return [_node_to_event(record["e"]) async for record in result]


# ── list_events_in_order ──────────────────────────────────────────────


# Uses the K11.3 `event_user_order` index. The optional bounded
# range `[after_order, before_order)` uses the index range scan
# semantics; both bounds optional.
_LIST_EVENTS_IN_ORDER_CYPHER = """
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND ($after_order IS NULL OR e.event_order > $after_order)
  AND ($before_order IS NULL OR e.event_order < $before_order)
  AND ($include_archived OR e.archived_at IS NULL)
RETURN e
ORDER BY coalesce(e.event_order, 2147483647), e.title ASC
LIMIT $limit
"""


async def list_events_in_order(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
    after_order: int | None = None,
    before_order: int | None = None,
    include_archived: bool = False,
    limit: int = 200,
) -> list[Event]:
    """Events in narrative order, optionally bounded by
    `[after_order, before_order)`. Used by the L4 timeline
    retrieval (KSA §4.2). `project_id` scopes to one project; if
    None, returns events across the user's full graph."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if (
        after_order is not None
        and before_order is not None
        and after_order >= before_order
    ):
        raise ValueError(
            f"after_order ({after_order}) must be < before_order ({before_order})"
        )
    result = await run_read(
        session,
        _LIST_EVENTS_IN_ORDER_CYPHER,
        user_id=user_id,
        project_id=project_id,
        after_order=after_order,
        before_order=before_order,
        include_archived=include_archived,
        limit=limit,
    )
    return [_node_to_event(record["e"]) async for record in result]


# ── delete_events_with_zero_evidence ──────────────────────────────────


_DELETE_EVENTS_ZERO_EVIDENCE_CYPHER = """
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.evidence_count = 0
DETACH DELETE e
RETURN count(*) AS deleted
"""


async def delete_events_with_zero_evidence(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Cascade cleanup. Same semantics as K11.5a's
    `delete_entities_with_zero_evidence` — uses the K11.3-R1
    `event_user_evidence` composite index, bounded by the
    calling user's churn.

    **DO NOT run concurrently with extraction.** Same race window
    as the entity cleanup: `merge_event` creates a node with
    `evidence_count=0` and there's a window before K11.8
    increments it. K11.8 owns the orchestration.
    """
    result = await run_write(
        session,
        _DELETE_EVENTS_ZERO_EVIDENCE_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["deleted"])
