"""K11.6 — relations repository.

Functions over `(:Entity)-[:RELATES_TO]->(:Entity)` edges. Every
edge is keyed by a deterministic `relation_id` derived from
`(user_id, subject_id, predicate, object_id)` so re-extracting
the same SVO from any source is idempotent.

Each edge accumulates a `source_event_ids` list — the same SVO
spotted in two different events appends two ids, and the same
SVO spotted twice in the same event is a no-op (the existing
list already contains the id).

Temporal model: `valid_from` is set on creation; `valid_until`
is null while the relation holds and is set by
`invalidate_relation` when the user (or a contradicting Pass 2
LLM extraction) supersedes it. Default queries filter
`valid_until IS NULL` so superseded relations don't pollute the
RAG context loader.

Pass 1 quarantine: pattern-extracted relations carry
`pending_validation = true` and `confidence < 0.8` so the
default L2 loader excludes them. K17 LLM Pass 2 promotes them
by writing a fresh relation with `pending_validation = false`
and the higher confidence score (`merge_entity`-style
max-confidence semantics on the existing edge).

Reference: KSA §3.4.C provenance edges, §5.1 Pass 1 quarantine,
KSA L2 loader Cypher (lines 2123-2133).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Phase 4b-α: relation_id moved to loreweave_extraction.canonical.
# Re-exported below for back-compat with non-extraction call sites.
from loreweave_extraction.canonical import relation_id

from app.db.neo4j_helpers import CypherSession, run_read, run_write

# K11.6-R1/R1: 1-hop direction options. "both" returns outgoing
# AND incoming edges, which is what the L2 RAG context loader
# actually needs ("facts about Kai" includes both Kai-as-subject
# and Kai-as-object). KSA §4.2 example only shows outgoing
# because that one query was subject-anchored.
RelationDirection = Literal["outgoing", "incoming", "both"]

logger = logging.getLogger(__name__)

__all__ = [
    "Relation",
    "RelationHop",
    "relation_id",
    "create_relation",
    "find_relations_for_entity",
    "find_relations_2hop",
    "invalidate_relation",
    "get_relation",
]


class Relation(BaseModel):
    """Pydantic projection of a `:RELATES_TO` edge.

    The endpoints are returned alongside the edge properties so
    the caller can render `(subject_name)-[predicate]->(object_name)`
    without a second round-trip. Endpoint nodes are projected as
    just `id` + `name` + `kind` to keep the payload small —
    callers that need the full node go through K11.5's
    `get_entity`.
    """

    id: str
    user_id: str
    subject_id: str
    object_id: str
    predicate: str
    confidence: float = 0.0
    source_event_ids: list[str] = Field(default_factory=list)
    source_chapter: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    pending_validation: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Endpoint projection — populated by find_* helpers.
    subject_name: str | None = None
    subject_kind: str | None = None
    object_name: str | None = None
    object_kind: str | None = None


class RelationHop(BaseModel):
    """One row of a 2-hop traversal.

    A 2-hop result has:
      - `via` — the intermediate entity (`hop1.object` == `hop2.subject`)
      - `hop1` — the first edge (anchor → via)
      - `hop2` — the second edge (via → target)

    Returned as a single row per traversal so the caller can
    render the full path without reassembling.
    """

    hop1: Relation
    hop2: Relation
    via_id: str
    via_name: str
    via_kind: str


def _temporal_to_native(value: Any) -> Any:
    if value is not None and hasattr(value, "to_native"):
        return value.to_native()
    return value


def _edge_props_to_relation(
    *,
    rel_props: dict[str, Any],
    subject: dict[str, Any] | None,
    object_: dict[str, Any] | None,
) -> Relation:
    """Build a `Relation` from a `(rel_props, subject, object)`
    triple.

    `rel_props` is the dict-of-properties returned by
    `properties(r)` in Cypher — we don't try to use the live
    `neo4j.graph.Relationship` object because the bolt driver's
    relationship type doesn't expose `.items()` on every version
    we may run against, and a property dict is forward-compatible.
    """
    data = dict(rel_props)
    for key, val in list(data.items()):
        data[key] = _temporal_to_native(val)
    if subject is not None:
        data["subject_name"] = subject.get("name")
        data["subject_kind"] = subject.get("kind")
    if object_ is not None:
        data["object_name"] = object_.get("name")
        data["object_kind"] = object_.get("kind")
    return Relation.model_validate(data)


# ── create_relation ───────────────────────────────────────────────────


# Structural MERGE on the edge `id` property. We can't use the
# bare structural pattern `(a)-[r:RELATES_TO {predicate: $p}]->(b)`
# because that would collide two relations with the same
# (subject, predicate, object) but different temporal windows —
# the deterministic id property is the explicit identity.
#
# The two MATCHes ensure both endpoints belong to the calling
# user. WHERE filtering after the MATCH covers the multi-tenant
# safety check before we touch the edge.
_CREATE_RELATION_CYPHER = """
MATCH (subj:Entity {id: $subject_id})
WHERE subj.user_id = $user_id
MATCH (obj:Entity {id: $object_id})
WHERE obj.user_id = $user_id
MERGE (subj)-[r:RELATES_TO {id: $relation_id}]->(obj)
ON CREATE SET
  r.user_id = $user_id,
  r.subject_id = $subject_id,
  r.object_id = $object_id,
  r.predicate = $predicate,
  r.confidence = $confidence,
  r.source_event_ids = CASE
    WHEN $source_event_id IS NULL THEN []
    ELSE [$source_event_id]
  END,
  r.source_chapter = $source_chapter,
  r.valid_from = coalesce($valid_from, datetime()),
  r.valid_until = NULL,
  r.pending_validation = $pending_validation,
  r.created_at = datetime(),
  r.updated_at = datetime()
ON MATCH SET
  r.source_event_ids = CASE
    WHEN $source_event_id IS NULL OR $source_event_id IN r.source_event_ids
      THEN r.source_event_ids
    ELSE r.source_event_ids + $source_event_id
  END,
  r.confidence = CASE
    WHEN $confidence > r.confidence THEN $confidence
    ELSE r.confidence
  END,
  r.pending_validation = CASE
    WHEN $confidence > r.confidence THEN $pending_validation
    ELSE r.pending_validation
  END,
  r.updated_at = datetime()
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
"""


async def create_relation(
    session: CypherSession,
    *,
    user_id: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    confidence: float = 0.0,
    source_event_id: str | None = None,
    source_chapter: str | None = None,
    valid_from: datetime | None = None,
    pending_validation: bool = False,
) -> Relation | None:
    """Idempotent edge upsert. Re-running with the same
    `(subject_id, predicate, object_id)` returns the same edge —
    no duplicates — and appends `source_event_id` to the
    accumulated list (or no-ops if already present).

    Returns `None` if either endpoint does not exist under the
    calling user (e.g., subject was deleted, or someone passed a
    cross-tenant id). Caller should treat this as "nothing to
    relate" and either log or merge the missing endpoint via K11.5
    before retrying.

    Multi-source confidence (matches K11.5a `merge_entity`): if
    the new confidence beats the stored one, the edge takes the
    higher value AND adopts the new `pending_validation` flag.
    This is how K17 (LLM Pass 2) promotes a Pass 1 quarantined
    edge: re-create with higher confidence + `pending_validation
    = false`, and the existing edge is upgraded in place.
    """
    if not predicate:
        raise ValueError("predicate must be a non-empty string")
    if not subject_id:
        raise ValueError("subject_id must be a non-empty string")
    if not object_id:
        raise ValueError("object_id must be a non-empty string")
    rid = relation_id(
        user_id=user_id,
        subject_id=subject_id,
        predicate=predicate,
        object_id=object_id,
    )
    result = await run_write(
        session,
        _CREATE_RELATION_CYPHER,
        user_id=user_id,
        relation_id=rid,
        subject_id=subject_id,
        object_id=object_id,
        predicate=predicate,
        confidence=confidence,
        source_event_id=source_event_id,
        source_chapter=source_chapter,
        valid_from=valid_from,
        pending_validation=pending_validation,
    )
    record = await result.single()
    if record is None:
        return None
    return _edge_props_to_relation(
        rel_props=dict(record["rel"]),
        subject=dict(record["subj"]),
        object_=dict(record["obj"]),
    )


# ── get_relation ──────────────────────────────────────────────────────


_GET_RELATION_CYPHER = """
MATCH (subj:Entity)-[r:RELATES_TO {id: $relation_id}]->(obj:Entity)
WHERE r.user_id = $user_id
  AND subj.user_id = $user_id
  AND obj.user_id = $user_id
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
"""


async def get_relation(
    session: CypherSession,
    *,
    user_id: str,
    relation_id: str,
) -> Relation | None:
    """Fetch a single relation by its deterministic id. Returns
    `None` if no row matches under the calling user."""
    if not relation_id:
        raise ValueError("relation_id must be a non-empty string")
    result = await run_read(
        session,
        _GET_RELATION_CYPHER,
        user_id=user_id,
        relation_id=relation_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _edge_props_to_relation(
        rel_props=dict(record["rel"]),
        subject=dict(record["subj"]),
        object_=dict(record["obj"]),
    )


# ── find_relations_for_entity (1-hop) ─────────────────────────────────


# K11.5a's `entity_user_canonical` index makes the anchor lookup
# fast. The traversal then follows incident RELATES_TO edges —
# Neo4j keeps adjacency info next to the node, so the per-hop
# cost is bounded by the entity's fan-out, not the global graph.
#
# Filters (apply to all three direction templates):
#   - r.confidence >= $min_confidence (0.8 default excludes Pass 1
#     quarantined edges)
#   - r.valid_until IS NULL (excludes superseded relations)
#   - coalesce(r.pending_validation, false) = false when
#     $exclude_pending is true (matches KSA L2 loader)
#   - peer.archived_at IS NULL by default (no broken pointers
#     into hidden entities)
#   - both anchor and peer must share $project_id when set
#     (K11.6-R1/R2: cross-project edges are usually noise for the
#     L2 loader)
#
# Three templates, one per direction. We pick at call time so
# Neo4j can plan each shape optimally — a single template with
# `(anchor)-[r]-(peer)` (undirected) would force the planner to
# walk both sides for the outgoing-only case.

_FIND_RELATIONS_1HOP_OUTGOING_CYPHER = """
MATCH (anchor:Entity {id: $entity_id})-[r:RELATES_TO]->(peer:Entity)
WHERE anchor.user_id = $user_id
  AND peer.user_id = $user_id
  AND ($project_id IS NULL OR anchor.project_id = $project_id)
  AND ($project_id IS NULL OR peer.project_id = $project_id)
  AND r.confidence >= $min_confidence
  AND r.valid_until IS NULL
  AND (NOT $exclude_pending OR coalesce(r.pending_validation, false) = false)
  AND ($include_archived_peer OR peer.archived_at IS NULL)
RETURN properties(r) AS rel,
       properties(anchor) AS subj,
       properties(peer) AS obj
ORDER BY r.confidence DESC, r.predicate ASC, peer.name ASC
LIMIT $limit
"""

_FIND_RELATIONS_1HOP_INCOMING_CYPHER = """
MATCH (peer:Entity)-[r:RELATES_TO]->(anchor:Entity {id: $entity_id})
WHERE anchor.user_id = $user_id
  AND peer.user_id = $user_id
  AND ($project_id IS NULL OR anchor.project_id = $project_id)
  AND ($project_id IS NULL OR peer.project_id = $project_id)
  AND r.confidence >= $min_confidence
  AND r.valid_until IS NULL
  AND (NOT $exclude_pending OR coalesce(r.pending_validation, false) = false)
  AND ($include_archived_peer OR peer.archived_at IS NULL)
RETURN properties(r) AS rel,
       properties(peer) AS subj,
       properties(anchor) AS obj
ORDER BY r.confidence DESC, r.predicate ASC, peer.name ASC
LIMIT $limit
"""

# UNION of the two single-direction queries. Each arm runs against
# its own template so the planner can use the directional traversal.
# UNION (not UNION ALL) deduplicates a self-loop edge that would
# otherwise appear twice.
_FIND_RELATIONS_1HOP_BOTH_CYPHER = """
CALL {
  WITH $user_id AS user_id, $entity_id AS entity_id,
       $project_id AS project_id, $min_confidence AS min_confidence,
       $exclude_pending AS exclude_pending,
       $include_archived_peer AS include_archived_peer
  MATCH (anchor:Entity {id: entity_id})-[r:RELATES_TO]->(peer:Entity)
  WHERE anchor.user_id = user_id
    AND peer.user_id = user_id
    AND (project_id IS NULL OR anchor.project_id = project_id)
    AND (project_id IS NULL OR peer.project_id = project_id)
    AND r.confidence >= min_confidence
    AND r.valid_until IS NULL
    AND (NOT exclude_pending OR coalesce(r.pending_validation, false) = false)
    AND (include_archived_peer OR peer.archived_at IS NULL)
  RETURN properties(r) AS rel,
         properties(anchor) AS subj,
         properties(peer) AS obj
  UNION
  WITH $user_id AS user_id, $entity_id AS entity_id,
       $project_id AS project_id, $min_confidence AS min_confidence,
       $exclude_pending AS exclude_pending,
       $include_archived_peer AS include_archived_peer
  MATCH (peer:Entity)-[r:RELATES_TO]->(anchor:Entity {id: entity_id})
  WHERE anchor.user_id = user_id
    AND peer.user_id = user_id
    AND (project_id IS NULL OR anchor.project_id = project_id)
    AND (project_id IS NULL OR peer.project_id = project_id)
    AND r.confidence >= min_confidence
    AND r.valid_until IS NULL
    AND (NOT exclude_pending OR coalesce(r.pending_validation, false) = false)
    AND (include_archived_peer OR peer.archived_at IS NULL)
  RETURN properties(r) AS rel,
         properties(peer) AS subj,
         properties(anchor) AS obj
}
RETURN rel, subj, obj
ORDER BY rel.confidence DESC, rel.predicate ASC
LIMIT $limit
"""

_DIRECTION_TO_CYPHER: dict[str, str] = {
    "outgoing": _FIND_RELATIONS_1HOP_OUTGOING_CYPHER,
    "incoming": _FIND_RELATIONS_1HOP_INCOMING_CYPHER,
    "both": _FIND_RELATIONS_1HOP_BOTH_CYPHER,
}


async def find_relations_for_entity(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    project_id: str | None = None,
    direction: RelationDirection = "both",
    min_confidence: float = 0.8,
    exclude_pending: bool = True,
    include_archived_peer: bool = False,
    limit: int = 100,
) -> list[Relation]:
    """1-hop RELATES_TO traversal from the given entity.

    K11.6-R1/R1 fix: returns BOTH directions by default. The KSA
    §4.2 "facts about Kai" loader needs `(Kai)-[loyal_to]->(X)`
    AND `(Y)-[ally_of]->(Kai)` — the previous outgoing-only shape
    silently dropped the latter. `direction="outgoing"` and
    `direction="incoming"` opt into single-direction queries
    when the caller knows what they want.

    K11.6-R1/R2 fix: optional `project_id` filter. The L2 RAG
    loader scopes queries to the chapter's project; without this
    filter, cross-project edges from other works pollute the
    context. `project_id=None` keeps the "all projects for this
    user" behavior for callers that genuinely need it (memory UI
    cross-project search).

    Default filters match the L2 RAG context loader (KSA lines
    2123-2127): confidence >= 0.8, valid_until IS NULL,
    pending_validation = false. Override `exclude_pending=False`
    for the memory UI's "Quarantine" tab.

    Archived peer entities (the "other end" of the edge,
    regardless of direction) are excluded by default — a relation
    that points at a hidden entity creates a dangling pointer in
    the L2 context. Override with `include_archived_peer=True`.
    """
    if not entity_id:
        raise ValueError("entity_id must be a non-empty string")
    if direction not in _DIRECTION_TO_CYPHER:
        raise ValueError(
            f"direction must be one of {sorted(_DIRECTION_TO_CYPHER)}, "
            f"got {direction!r}"
        )
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(
            f"min_confidence must be in [0,1], got {min_confidence}"
        )
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    cypher = _DIRECTION_TO_CYPHER[direction]
    result = await run_read(
        session,
        cypher,
        user_id=user_id,
        entity_id=entity_id,
        project_id=project_id,
        min_confidence=min_confidence,
        exclude_pending=exclude_pending,
        include_archived_peer=include_archived_peer,
        limit=limit,
    )
    return [
        _edge_props_to_relation(
            rel_props=dict(record["rel"]),
            subject=dict(record["subj"]),
            object_=dict(record["obj"]),
        )
        async for record in result
    ]


# ── find_relations_2hop ───────────────────────────────────────────────


# 2-hop traversal: anchor → via → target. The first hop is
# constrained to a specific predicate set ($hop1_types) so the
# caller can ask things like "find Kai's allies' loyalties"
# (hop1='ally', hop2 in ['loyal_to', 'enemy_of', 'member_of']).
# Without the hop1 predicate filter, 2-hop fans out
# combinatorially and the query would blow up on hub entities.
#
# Both edges respect the same default filters as the 1-hop query.
# The intermediate `via` node MUST belong to the same user, but
# the relation between via and target is allowed to have its own
# confidence — the more conservative call uses the same
# min_confidence for both hops.
_FIND_RELATIONS_2HOP_CYPHER = """
MATCH (anchor:Entity {id: $entity_id})-[r1:RELATES_TO]->(via:Entity)
      -[r2:RELATES_TO]->(target:Entity)
WHERE anchor.user_id = $user_id
  AND via.user_id = $user_id
  AND target.user_id = $user_id
  AND ($project_id IS NULL OR anchor.project_id = $project_id)
  AND ($project_id IS NULL OR via.project_id = $project_id)
  AND ($project_id IS NULL OR target.project_id = $project_id)
  AND r1.predicate IN $hop1_types
  AND ($hop2_types IS NULL OR r2.predicate IN $hop2_types)
  AND r1.confidence >= $min_confidence
  AND r2.confidence >= $min_confidence
  AND r1.valid_until IS NULL
  AND r2.valid_until IS NULL
  AND coalesce(r1.pending_validation, false) = false
  AND coalesce(r2.pending_validation, false) = false
  AND via.archived_at IS NULL
  AND target.archived_at IS NULL
  AND target.id <> anchor.id
RETURN properties(r1) AS r1_rel,
       properties(anchor) AS r1_subj,
       properties(via) AS r1_obj,
       properties(r2) AS r2_rel,
       properties(via) AS r2_subj,
       properties(target) AS r2_obj
ORDER BY (r1.confidence + r2.confidence) DESC, target.name ASC
LIMIT $limit
"""


async def find_relations_2hop(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    hop1_types: list[str],
    hop2_types: list[str] | None = None,
    project_id: str | None = None,
    min_confidence: float = 0.8,
    limit: int = 100,
) -> list[RelationHop]:
    """2-hop outgoing traversal with predicate filters.

    `hop1_types` is REQUIRED and acts as the fan-out gate — without
    it, a hub entity (e.g., a main character with hundreds of
    outgoing edges) would multiply at the second hop and blow the
    query budget. The plan calls for "<200ms at 10k entity scale"
    which only works if the first hop is selective.

    `hop2_types=None` allows any predicate on the second hop.

    Returns one `RelationHop` per (hop1, hop2) pair, sorted by
    summed confidence descending. The intermediate `via` node
    is exposed as `via_id` / `via_name` / `via_kind` on each row.
    """
    if not entity_id:
        raise ValueError("entity_id must be a non-empty string")
    if not hop1_types:
        raise ValueError(
            "hop1_types must be a non-empty list — 2-hop traversals "
            "without a first-hop filter explode on hub entities"
        )
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(
            f"min_confidence must be in [0,1], got {min_confidence}"
        )
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    result = await run_read(
        session,
        _FIND_RELATIONS_2HOP_CYPHER,
        user_id=user_id,
        entity_id=entity_id,
        hop1_types=list(hop1_types),
        hop2_types=list(hop2_types) if hop2_types is not None else None,
        project_id=project_id,
        min_confidence=min_confidence,
        limit=limit,
    )
    hops: list[RelationHop] = []
    async for record in result:
        hop1 = _edge_props_to_relation(
            rel_props=dict(record["r1_rel"]),
            subject=dict(record["r1_subj"]),
            object_=dict(record["r1_obj"]),
        )
        hop2 = _edge_props_to_relation(
            rel_props=dict(record["r2_rel"]),
            subject=dict(record["r2_subj"]),
            object_=dict(record["r2_obj"]),
        )
        via = dict(record["r1_obj"])
        hops.append(
            RelationHop(
                hop1=hop1,
                hop2=hop2,
                via_id=str(via.get("id", "")),
                via_name=str(via.get("name", "")),
                via_kind=str(via.get("kind", "")),
            )
        )
    return hops


# ── invalidate_relation ───────────────────────────────────────────────


_INVALIDATE_RELATION_CYPHER = """
MATCH (subj:Entity)-[r:RELATES_TO {id: $relation_id}]->(obj:Entity)
WHERE r.user_id = $user_id
  AND subj.user_id = $user_id
  AND obj.user_id = $user_id
SET r.valid_until = coalesce($valid_until, datetime()),
    r.updated_at = datetime()
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
"""


async def invalidate_relation(
    session: CypherSession,
    *,
    user_id: str,
    relation_id: str,
    valid_until: datetime | None = None,
) -> Relation | None:
    """Soft-invalidate a relation by setting `valid_until`.

    Idempotent — re-invalidating an already-invalid edge updates
    `valid_until` to the new timestamp (or `now()` if not given).
    Default filters in the find helpers exclude relations with
    `valid_until IS NOT NULL`, so callers that need to inspect
    historical relations must opt in via lower-level queries.

    Returns `None` if no relation matches the id under the
    calling user.
    """
    if not relation_id:
        raise ValueError("relation_id must be a non-empty string")
    result = await run_write(
        session,
        _INVALIDATE_RELATION_CYPHER,
        user_id=user_id,
        relation_id=relation_id,
        valid_until=valid_until,
    )
    record = await result.single()
    if record is None:
        return None
    return _edge_props_to_relation(
        rel_props=dict(record["rel"]),
        subject=dict(record["subj"]),
        object_=dict(record["obj"]),
    )
