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
from app.db.neo4j_repos.temporal import (
    MAINTAIN_RELATION_CHAIN_CYPHER,
    ORDINAL_OPEN_CEILING,
)

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
    "SubgraphNode",
    "SubgraphEdge",
    "Subgraph",
    "SUBGRAPH_MAX_NODE_CAP",
    "SUBGRAPH_MAX_HOPS",
    "relation_id",
    "create_relation",
    "recreate_relation",
    "find_relations_for_entity",
    "find_relations_2hop",
    "get_project_subgraph",
    "invalidate_relation",
    "get_relation",
]

# C18 — hard ceilings for the project subgraph read (G5). The route's
# `limit` (node cap) and `hops` params are clamped to these so a caller
# cannot ask for an unbounded traversal that OOMs Neo4j on a hub node.
# The cap is enforced IN the Cypher (deterministic ORDER + LIMIT on the
# seed-node collection), never post-filtered after fetching everything.
SUBGRAPH_MAX_NODE_CAP = 500
SUBGRAPH_MAX_HOPS = 3


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
    # F3 — story (valid) time axis (chapter ordinals). The existing
    # valid_from/valid_until above are wall-clock TRANSACTION-time; these are the
    # STORY-time half-open interval [valid_from_ordinal, valid_to_ordinal) over
    # the (subject, predicate) arc. valid_from_ordinal is stamped at write time
    # (the chapter ordinal the edge was established at, on the same scale as
    # events.event_order); valid_to_ordinal is set ONLY by temporal.maintain_chain
    # when a later instance on the same (subject, predicate) chain supersedes it.
    # NULL on legacy / positionless edges. See app.db.neo4j_repos.temporal + §12.3.
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None
    valid_to_ordinal_eff: int | None = None
    # dec-3 (D-KG-INSTORY-EVENTDATE) — detected in-story (narrative) time as a
    # truncated ISO string: "YYYY" / "YYYY-MM" / "YYYY-MM-DD". An ADDITIONAL,
    # optional valid-time REFINEMENT alongside the chapter-ordinal axis
    # (valid_from_ordinal) — chapter-ordinal stays the PRIMARY / spoiler-safe
    # story-time axis; event_date_iso is a SECONDARY descriptive sort/filter key
    # supplied only when the prose carries an explicit in-story date. NULL is the
    # dominant case and never affects the ordinal chain. Mirrors :Event /
    # :Fact event_date_iso (same truncated-ISO shape, precision-preferring merge).
    event_date_iso: str | None = None
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


# KG customizable-ontology (L7, D-KG-L7-CARDINALITY) — auto-close the prior
# OPEN instance of a `single_active` edge type for this `(subject, predicate)`,
# BEFORE the new instance is MERGEd. Runs in the same CypherSession transaction
# as the create, so the close + the new-open are atomic (a reader never sees two
# open instances, and a rollback leaves both untouched).
#
# Cardinality semantic: `single_active` means a subject holds AT MOST ONE open
# instance of this predicate at a time (e.g. CURRENT_SECT — joining sect B closes
# the open membership of sect A). So the close scopes to the same SUBJECT +
# PREDICATE under the SAME `$user_id` partition (no cross-tenant close), across
# ANY object, and only edges still open (`valid_until IS NULL`). The new
# instance's OWN id is excluded so re-running an idempotent create of the *same*
# relation never closes itself, and re-asserting the identical (subj,pred,obj) is
# a clean no-op. `multi_active` (e.g. PURSUES — multiple coexisting drives) never
# reaches this query. Mirrors the `invalidate_relation` close primitive
# (sets `valid_until` + `updated_at`).
#
# Project scoping is IMPLICIT and complete: `Entity.id` (entity_canonical_id)
# folds project_id into its hash, so `{id: $subject_id}` matches exactly one
# project's subject node, and every outgoing edge of that node was created with
# that project's (also project-scoped) objects. A user's single_active write in
# project A therefore cannot reach an open edge in project B — locked by
# test_L7_single_active_does_not_cross_project_boundary.
_CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER = """
MATCH (subj:Entity {id: $subject_id})-[rp:RELATES_TO]->(obj:Entity)
WHERE rp.user_id = $user_id
  AND subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND rp.predicate = $predicate
  AND rp.valid_until IS NULL
  AND rp.id <> $relation_id
SET rp.valid_until = datetime(),
    rp.updated_at = datetime()
RETURN count(rp) AS closed
"""


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
  // F3 — story valid-time axis. valid_from_ordinal is the chapter ordinal the
  // edge was established at; a fresh edge opens its interval (valid_to_ordinal
  // NULL → eff = +∞ null-sink). The interval CLOSE is done by
  // temporal.maintain_chain after the merge, never here.
  r.valid_from_ordinal = $valid_from_ordinal,
  r.valid_to_ordinal = NULL,
  r.valid_to_ordinal_eff = $open_ceiling,
  // dec-3 — detected in-story date (optional valid-time refinement). NULL when the
  // prose carried no explicit calendar date. Additive: never participates in the
  // ordinal chain, only annotates/sorts.
  r.event_date_iso = $event_date_iso,
  r.pending_validation = $pending_validation,
  // KG customizable-ontology (L7) — stamp the resolved-schema version this edge
  // was written under (M3) + the layer-4 partition seam (M2, NULL at v1). Both
  // additive; NULL for legacy/un-adopted writes (no behavior change).
  r.schema_version = $schema_version,
  r.graph_id = $graph_id,
  r.created_at = datetime(),
  // T4.1 flywheel — the extraction job that first minted this relation (net-new).
  r.created_job_id = $job_id,
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
  // KG customizable-ontology (L7 activation) — re-confirm the schema version on a
  // re-matched edge so an edge first written pre-activation (NULL) gets stamped on
  // the next extraction under the resolved schema. COALESCE so a legacy/un-adopted
  // persist (schema_version NULL) NEVER wipes an existing stamp — only a non-NULL
  // new value updates. graph_id is intentionally NOT touched on MATCH: it is NULL
  // at v1 everywhere, and overwriting would clobber a future partition assignment
  // (M2). The ON CREATE branch still sets graph_id for fresh edges.
  r.schema_version = coalesce($schema_version, r.schema_version),
  // F3 — backfill the story-time lower bound on a later positioned re-extraction
  // (an edge first written positionless keeps NULL until a positioned source
  // re-mentions it); never overwrite an existing one. valid_to_ordinal is owned
  // by maintain_chain, so it is NOT touched on MATCH here.
  r.valid_from_ordinal = coalesce(r.valid_from_ordinal, $valid_from_ordinal),
  r.valid_to_ordinal_eff = coalesce(
    r.valid_to_ordinal_eff,
    CASE WHEN r.valid_to_ordinal IS NULL THEN $open_ceiling ELSE r.valid_to_ordinal END
  ),
  // dec-3 — prefer the MORE precise (longer truncated-ISO) in-story date on
  // re-mention (mirrors :Event/:Fact): a less-precise re-mention never downgrades
  // the stored precision; NULL new leaves the stored one; NULL stored adopts the
  // new (backfill on a later positioned re-extraction).
  r.event_date_iso = CASE
    WHEN $event_date_iso IS NULL THEN r.event_date_iso
    WHEN r.event_date_iso IS NULL THEN $event_date_iso
    WHEN size($event_date_iso) > size(r.event_date_iso) THEN $event_date_iso
    ELSE r.event_date_iso
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
    schema_version: int | None = None,
    graph_id: str | None = None,
    cardinality: str | None = None,
    job_id: str | None = None,
    valid_from_ordinal: int | None = None,
    event_date_iso: str | None = None,
    maintain_chain: bool = False,
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

    `cardinality` (KG L7, D-KG-L7-CARDINALITY): when ``"single_active"``, the
    prior OPEN edge of this `(subject, predicate, object)` under the SAME
    `$user_id` is auto-closed (`valid_until = now()`) BEFORE the new instance is
    written — so a `single_active` edge type can only hold one open instance at a
    time. ``"multi_active"`` / ``None`` (the default) ⇒ no auto-close, exactly
    today's behavior. The close runs in the same session transaction as the
    create (atomic). The new relation's own id is excluded from the close, so a
    pure idempotent re-create of the same edge never closes itself.

    F3 — `valid_from_ordinal` is the STORY-time lower bound (chapter ordinal) the
    edge was established at (same scale as `events.event_order`). `maintain_chain`
    (the EXTRACTION path, §12.3.2) re-derives the ordinal `valid_to_ordinal` chain
    for this `(subject, predicate)` AFTER the merge via `temporal.maintain_chain`
    — the ordinal-aware interval-split that is correct under out-of-order/backfill
    arrival, unlike `single_active` (which closes ANY open instance by wall-clock
    and inverts intervals, A2). `single_active` and `maintain_chain` are distinct
    mechanisms: use `single_active` for monotonic L7/user edits, `maintain_chain`
    for extraction. Both default off ⇒ byte-identical legacy behaviour.

    dec-3 (D-KG-INSTORY-EVENTDATE) — `event_date_iso` is the OPTIONAL detected
    in-story (narrative) date, a truncated ISO string ("YYYY" / "YYYY-MM" /
    "YYYY-MM-DD"). It is an ADDITIVE valid-time refinement ALONGSIDE
    `valid_from_ordinal` (the primary chapter-ordinal axis), never a replacement.
    `None` (the dominant case) is null-safe and never affects the ordinal chain.
    Empty string normalizes to `None`; on re-mention the MORE precise date wins.
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
    # dec-3 — empty string → None so the Cypher's "NULL = no new value" precision
    # merge treats a blank date as absent (never clobbers a stored one on MATCH).
    normalized_event_date_iso = event_date_iso or None
    # L7 single_active auto-close — close the prior OPEN instance (same tenant,
    # same endpoints+predicate) before the MERGE of the new one. multi_active /
    # None ⇒ skip entirely (legacy path is byte-identical: no extra query).
    if cardinality == "single_active":
        await run_write(
            session,
            _CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER,
            user_id=user_id,
            relation_id=rid,
            subject_id=subject_id,
            predicate=predicate,
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
        valid_from_ordinal=valid_from_ordinal,
        open_ceiling=ORDINAL_OPEN_CEILING,
        event_date_iso=normalized_event_date_iso,
        pending_validation=pending_validation,
        schema_version=schema_version,
        graph_id=graph_id,
        job_id=job_id,
    )
    record = await result.single()
    if record is None:
        return None
    # F3 — drive the ordinal-aware interval-split close (the EXTRACTION path).
    # Re-derives valid_to_ordinal over the (subject, predicate) chain from
    # valid_from_ordinal order AFTER the new instance is in place, so a back-
    # filled out-of-order edge never inverts a later interval (A2). Only when a
    # story-time position exists; legacy/positionless writes skip it.
    if maintain_chain and valid_from_ordinal is not None:
        await run_write(
            session,
            MAINTAIN_RELATION_CHAIN_CYPHER,
            user_id=user_id,
            subject_id=subject_id,
            predicate=predicate,
            open_ceiling=ORDINAL_OPEN_CEILING,
        )
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


# ── get_project_subgraph (C18 — n-hop, node-capped) ───────────────────


class SubgraphNode(BaseModel):
    """One node in the project subgraph — a lightweight `:Entity`
    projection typed for the C19 canvas.

    Deliberately NOT the full `Entity` model: the canvas only needs
    identity + a couple of layout/style signals (kind for colour,
    anchor_score/mention_count for node sizing), so we keep the
    payload small. The canvas pulls full detail lazily via the
    existing `GET /entities/{id}` route on click.
    """

    id: str
    name: str
    kind: str
    anchor_score: float = 0.0
    mention_count: int = 0
    glossary_entity_id: str | None = None
    # G4 (W2): in a WORLD rollup union, the source member project this node
    # came from — lets the C19 canvas legend nodes per book. None for the
    # single-project C18/C19 view (which never sets it).
    source_project_id: str | None = None


class SubgraphEdge(BaseModel):
    """One edge in the project subgraph — a `:RELATES_TO` projection.

    `id` is the deterministic `relation_id`; `source`/`target` are the
    subject/object entity ids so the canvas can wire endpoints without
    a second lookup. Only edges BETWEEN two nodes that survived the
    node cap are returned (no dangling pointers into capped-out nodes).
    """

    id: str
    source: str
    target: str
    predicate: str
    confidence: float = 0.0


class Subgraph(BaseModel):
    """The `{nodes, edges}` payload for the C19 graph canvas.

    `node_cap_hit` is true when the deterministic node cap trimmed the
    result — the FE can show a "showing top N — expand to load more"
    affordance. Raw nodes + edges only; NO server-side layout (the
    canvas hand-rolls force/radial in C19)."""

    nodes: list[SubgraphNode] = Field(default_factory=list)
    edges: list[SubgraphEdge] = Field(default_factory=list)
    node_cap_hit: bool = False


# C18 — project-wide subgraph. Two-stage, cap-IN-the-query design so a
# hub entity can never explode the result or OOM Neo4j:
#
#   Stage 1 (seeds): collect up to $limit Entity nodes in the project
#     partition, deterministically ordered (anchor_score DESC,
#     mention_count DESC, id ASC) so the SAME query returns the SAME
#     nodes every call — C19 expand/load-more stability depends on this.
#     The LIMIT is applied HERE, on the ordered node collection, before
#     any edge traversal — this is the unbounded-traversal guard.
#
#   Stage 2 (edges): return only :RELATES_TO edges whose BOTH endpoints
#     are in the capped seed set. No traversal beyond the seed set, so
#     the edge count is bounded by the in-set adjacency, never the
#     global fan-out of a hub.
#
# Both stages bind BOTH $user_id AND $project_id on every node — no
# cross-user and no cross-project bleed. valid_until IS NULL +
# confidence >= $min_confidence + archived_at IS NULL match the L2
# loader's active-edge filters so the canvas shows the live graph.
_PROJECT_SUBGRAPH_CYPHER = """
CALL {
  WITH $user_id AS user_id, $project_id AS project_id
  MATCH (n:Entity)
  WHERE n.user_id = user_id
    AND n.project_id = project_id
    AND n.archived_at IS NULL
  RETURN n
  ORDER BY coalesce(n.anchor_score, 0.0) DESC,
           coalesce(n.mention_count, 0) DESC,
           n.id ASC
  LIMIT $limit
}
WITH collect(n) AS seeds
WITH seeds, [s IN seeds | s.id] AS seed_ids
UNWIND seeds AS node
WITH seed_ids, collect(DISTINCT properties(node)) AS node_props
OPTIONAL MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a.id IN seed_ids
  AND b.id IN seed_ids
  AND a.project_id = $project_id
  AND b.project_id = $project_id
  AND r.user_id = $user_id
  AND r.valid_until IS NULL
  AND coalesce(r.confidence, 0.0) >= $min_confidence
  AND (NOT $exclude_pending OR coalesce(r.pending_validation, false) = false)
RETURN node_props,
       collect(DISTINCT properties(r)) AS edge_props
"""

# C18 — ego-expansion. Same partition + active-edge filters, but the
# node set is the neighbourhood of $center within $hops, not the
# project-wide top-N.
#
# Hub-safety (adversary F1): we do NOT enumerate full variable-length
# paths (`(c)-[*1..3]-(m)`) — on a dense hub that materializes ~d^hops
# paths before any LIMIT could apply, the very explosion the cap is
# meant to prevent. Instead we expand the *reachable node frontier*
# hop-by-hop, capping the DISTINCT node set to $limit after EACH hop
# (`WITH ... collect(DISTINCT ...)[..$limit]`). Each hop's relationship
# scan is therefore bounded by the already-capped frontier (≤ $limit
# nodes), not the global fan-out — the work per hop is O($limit * avg
# degree), independent of any single hub's degree-cubed path count.
# Stage 3 below selects the in-set edges, identical to the project-wide
# path.
#
# Determinism: the per-hop `[..$limit]` slice is applied to a frontier
# ORDERed by (anchor_score DESC, mention_count DESC, id ASC), and id is
# UNIQUE, so the trimmed frontier — and thus the final node set — is
# stable across calls (C19 expand/load-more).
#
# active-edge filter (adversary F3): the per-hop expansion uses the SAME
# predicate as the returned-edge stage (confidence ≥ $min_confidence,
# valid_until IS NULL, not pending) so a node is only reachable via an
# edge that will also be returned — no orphan nodes reached through a
# quarantined/low-confidence edge that the edge stage then drops.
#
# Partition: every frontier node is scoped to BOTH $user_id AND
# $project_id (and archived_at IS NULL); a neighbour outside the
# partition is never admitted to the frontier, so a path cannot leak
# across project/user via an intermediate.
# Single bounded-frontier expansion step, reused (unrolled) once per
# hop. Given a list of frontier node ids ($frontier_ids), return up to
# $limit DISTINCT *new* partition-scoped neighbours reachable via an
# ACTIVE edge (same predicate as the returned-edge stage → no orphan
# nodes reached through a quarantined edge). Capping the result to
# $limit here bounds the next hop's scan, so total work is
# O($hops * $limit * avg_degree), independent of any hub's degree.
_EGO_HOP_STEP = """
  UNWIND $frontier_ids AS fid
  MATCH (f:Entity {id: fid})-[r:RELATES_TO]-(nbr:Entity)
  WHERE nbr.user_id = $user_id
    AND nbr.project_id = $project_id
    AND nbr.archived_at IS NULL
    AND NOT nbr.id IN $visited_ids
    AND r.user_id = $user_id
    AND r.valid_until IS NULL
    AND coalesce(r.confidence, 0.0) >= $min_confidence
    AND (NOT $exclude_pending OR coalesce(r.pending_validation, false) = false)
  WITH DISTINCT nbr
  ORDER BY coalesce(nbr.anchor_score, 0.0) DESC,
           coalesce(nbr.mention_count, 0) DESC,
           nbr.id ASC
  LIMIT $limit
  RETURN collect(nbr.id) AS next_ids
"""

# The center-node lookup (partition-scoped). Returns the center's id +
# props, or no row when the center is missing / cross-partition (→ empty
# subgraph, no existence leak).
_EGO_CENTER_CYPHER = """
MATCH (c:Entity {id: $center})
WHERE c.user_id = $user_id
  AND c.project_id = $project_id
  AND c.archived_at IS NULL
RETURN c.id AS id
"""

# Final assembly: given the resolved seed id set (center + capped
# per-hop frontiers, already ≤ $limit), fetch the node props + the
# in-set active edges. Identical edge stage to the project-wide query
# (both endpoints partition-scoped — adversary F2 belt).
_EGO_ASSEMBLE_CYPHER = """
MATCH (n:Entity)
WHERE n.id IN $seed_ids
  AND n.user_id = $user_id
  AND n.project_id = $project_id
WITH collect(properties(n)) AS node_props
OPTIONAL MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a.id IN $seed_ids
  AND b.id IN $seed_ids
  AND a.project_id = $project_id
  AND b.project_id = $project_id
  AND r.user_id = $user_id
  AND r.valid_until IS NULL
  AND coalesce(r.confidence, 0.0) >= $min_confidence
  AND (NOT $exclude_pending OR coalesce(r.pending_validation, false) = false)
RETURN node_props,
       collect(DISTINCT properties(r)) AS edge_props
"""


def _node_props_to_subgraph_node(props: dict[str, Any]) -> SubgraphNode:
    return SubgraphNode(
        id=str(props.get("id", "")),
        name=str(props.get("name", "")),
        kind=str(props.get("kind", "")),
        anchor_score=float(props.get("anchor_score") or 0.0),
        mention_count=int(props.get("mention_count") or 0),
        glossary_entity_id=props.get("glossary_entity_id"),
    )


def _edge_props_to_subgraph_edge(props: dict[str, Any]) -> SubgraphEdge | None:
    rid = props.get("id")
    subject_id = props.get("subject_id")
    object_id = props.get("object_id")
    if not rid or not subject_id or not object_id:
        return None
    return SubgraphEdge(
        id=str(rid),
        source=str(subject_id),
        target=str(object_id),
        predicate=str(props.get("predicate", "")),
        confidence=float(props.get("confidence") or 0.0),
    )


async def get_project_subgraph(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    hops: int = 1,
    limit: int = 200,
    center: str | None = None,
    min_confidence: float = 0.8,
    exclude_pending: bool = True,
) -> Subgraph:
    """C18 (G5) — read-only project subgraph for the C19 canvas.

    Returns `{nodes, edges}` for the `(user_id, project_id)` partition.
    Two modes:

      - **project-wide** (`center=None`): the top-`limit` entities by
        `anchor_score DESC, mention_count DESC, id ASC` plus every
        active `:RELATES_TO` edge between them. This is the default
        "show me the graph" view.
      - **ego-expansion** (`center` set): the `hops`-bounded
        neighbourhood of the `center` entity (powers the canvas
        expand-hop / click-to-expand). Same cap + deterministic order.

    The node cap is enforced **in the Cypher** (`LIMIT` on a
    deterministically-ordered node collection), never post-filtered —
    a hub entity with thousands of edges cannot blow the result or
    OOM Neo4j. Edges are returned only between nodes that survived the
    cap, so there are no dangling pointers.

    Multi-tenant + multi-project safety: BOTH `$user_id` AND
    `$project_id` are bound on every node in the query; a `project_id`
    the caller does not own (or a different project) yields no foreign
    nodes. `center` that doesn't exist / is cross-partition simply
    yields an empty subgraph (no existence leak).

    `node_cap_hit` is true when the result was trimmed to `limit` —
    the FE shows an "expand to load more" affordance.
    """
    if not project_id:
        raise ValueError("project_id must be a non-empty string")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if hops <= 0:
        raise ValueError(f"hops must be positive, got {hops}")
    # Clamp to the hard ceilings — defence in depth even though the
    # route also validates via Query(le=...). A direct repo caller
    # cannot bypass the cap.
    effective_limit = min(limit, SUBGRAPH_MAX_NODE_CAP)
    effective_hops = min(hops, SUBGRAPH_MAX_HOPS)

    if center:
        seed_ids = await _ego_seed_ids(
            session,
            user_id=user_id,
            project_id=project_id,
            center=center,
            hops=effective_hops,
            limit=effective_limit,
            min_confidence=min_confidence,
            exclude_pending=exclude_pending,
        )
        if not seed_ids:
            # center missing / cross-partition → empty subgraph (no leak)
            return Subgraph(nodes=[], edges=[], node_cap_hit=False)
        result = await run_read(
            session,
            _EGO_ASSEMBLE_CYPHER,
            user_id=user_id,
            project_id=project_id,
            seed_ids=seed_ids,
            min_confidence=min_confidence,
            exclude_pending=exclude_pending,
        )
    else:
        result = await run_read(
            session,
            _PROJECT_SUBGRAPH_CYPHER,
            user_id=user_id,
            project_id=project_id,
            limit=effective_limit,
            min_confidence=min_confidence,
            exclude_pending=exclude_pending,
        )
    record = await result.single()
    if record is None:
        return Subgraph(nodes=[], edges=[], node_cap_hit=False)

    raw_nodes = record["node_props"] or []
    raw_edges = record["edge_props"] or []
    nodes = [_node_props_to_subgraph_node(dict(p)) for p in raw_nodes]
    edges = [
        e
        for e in (
            _edge_props_to_subgraph_edge(dict(p)) for p in raw_edges
        )
        if e is not None
    ]
    # node_cap_hit: we asked for effective_limit seeds and got exactly
    # that many → there may be more (the cap bit). Fewer → the whole
    # partition (or ego neighbourhood) fit under the cap.
    node_cap_hit = len(nodes) >= effective_limit
    return Subgraph(nodes=nodes, edges=edges, node_cap_hit=node_cap_hit)


# ── get_world_subgraph (G4 / W2 — rollup union over a world's projects) ──


async def get_world_subgraph(
    session: CypherSession,
    *,
    user_id: str,
    project_ids: list[str],
    limit: int = 200,
    min_confidence: float = 0.8,
) -> Subgraph:
    """G4 (W2) — a world's rollup graph = the UNION of each member project's
    C18 subgraph (the world-level/bible project PLUS each member book's project).

    Merged in application code: every sub-query still binds BOTH ``user_id`` AND
    its own ``project_id``, so the union is N isolated per-partition reads
    stitched together — it never issues a cross-partition Cypher, and there is no
    cross-user or cross-project bleed (a project the user doesn't own yields an
    empty subgraph, contributing nothing).

    The result is a FOREST of per-book components (C18 edges are intra-project),
    NOT a connected cross-book graph — cross-book entity unification is out of
    scope (world-core territory). Each node is tagged with its
    ``source_project_id`` so the FE can legend per book.

    Re-cap: the merged node set is trimmed to ``limit`` by the SAME global order
    as C18 (``anchor_score DESC, mention_count DESC, id ASC``). ``node_cap_hit``
    is set if ANY member's own subgraph hit its cap OR the union re-cap trimmed —
    a large book crowding out a small one is flagged, never silent. Edges are
    kept only between nodes that survived the cap (no dangling pointers).
    """
    effective_limit = min(max(1, limit), SUBGRAPH_MAX_NODE_CAP)
    nodes_by_id: dict[str, SubgraphNode] = {}
    all_edges: list[SubgraphEdge] = []
    any_member_capped = False
    for pid in project_ids:
        if not pid:
            continue
        sg = await get_project_subgraph(
            session,
            user_id=user_id,
            project_id=pid,
            limit=effective_limit,
            min_confidence=min_confidence,
        )
        any_member_capped = any_member_capped or sg.node_cap_hit
        for n in sg.nodes:
            n.source_project_id = pid
            # ids are project-scoped, so a collision is not expected; dedup
            # defensively (first writer wins) so the union never doubles a node.
            nodes_by_id.setdefault(n.id, n)
        all_edges.extend(sg.edges)

    merged = sorted(
        nodes_by_id.values(),
        key=lambda n: (-n.anchor_score, -n.mention_count, n.id),
    )
    capped = merged[:effective_limit]
    union_trimmed = len(merged) > effective_limit
    surviving = {n.id for n in capped}
    edges = [e for e in all_edges if e.source in surviving and e.target in surviving]
    return Subgraph(
        nodes=capped,
        edges=edges,
        node_cap_hit=any_member_capped or union_trimmed,
    )


async def _ego_seed_ids(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    center: str,
    hops: int,
    limit: int,
    min_confidence: float,
    exclude_pending: bool,
) -> list[str]:
    """Bounded-frontier BFS for the ego seed set (adversary F1).

    Resolves the center (partition-scoped), then expands the reachable
    node frontier hop-by-hop. After EACH hop the cumulative seed set is
    capped to ``limit`` (the per-hop step itself returns at most
    ``limit`` deterministically-ordered new neighbours), so the next
    hop's relationship scan starts from a bounded frontier — total work
    is O(hops * limit * avg_degree), never a hub's degree^hops path
    enumeration. Returns the ordered seed id list (center first, then
    capped to ``limit``); empty when the center is missing/cross-partition.
    """
    center_res = await run_read(
        session,
        _EGO_CENTER_CYPHER,
        user_id=user_id,
        project_id=project_id,
        center=center,
    )
    center_row = await center_res.single()
    if center_row is None:
        return []

    seed_order: list[str] = [center_row["id"]]
    visited: set[str] = {center_row["id"]}
    frontier: list[str] = [center_row["id"]]

    for _ in range(hops):
        if not frontier or len(seed_order) >= limit:
            break
        hop_res = await run_read(
            session,
            _EGO_HOP_STEP,
            user_id=user_id,
            project_id=project_id,
            frontier_ids=frontier,
            visited_ids=list(visited),
            min_confidence=min_confidence,
            exclude_pending=exclude_pending,
            limit=limit,
        )
        hop_row = await hop_res.single()
        next_ids: list[str] = (hop_row["next_ids"] if hop_row else None) or []
        fresh = [nid for nid in next_ids if nid not in visited]
        if not fresh:
            break
        for nid in fresh:
            if len(seed_order) >= limit:
                break
            visited.add(nid)
            seed_order.append(nid)
        frontier = fresh
    return seed_order[:limit]


# ── recreate_relation (user-correction path) ──────────────────────────


# Phase B (F5) — the user-correction recreate. DELIBERATELY SEPARATE from
# create_relation: its ON MATCH clears `valid_until` (RESURRECTS a previously-
# invalidated edge) and pins confidence=1.0 + pending_validation=false. The
# extraction path (create_relation) must NEVER resurrect a user-invalidated
# edge on re-mention — so this resurrect logic lives in its own query that the
# extraction writers do not call. A user "correct this relation" produces a
# fresh, authoritative edge even if the (subject,predicate,object) tuple was
# invalidated before.
_RECREATE_RELATION_CYPHER = """
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
  r.confidence = 1.0,
  r.source_event_ids = [],
  r.source_chapter = $source_chapter,
  r.valid_from = datetime(),
  r.valid_until = NULL,
  r.pending_validation = false,
  r.created_at = datetime(),
  r.updated_at = datetime()
ON MATCH SET
  r.confidence = 1.0,
  r.pending_validation = false,
  r.valid_until = NULL,
  r.updated_at = datetime()
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
"""


async def recreate_relation(
    session: CypherSession,
    *,
    user_id: str,
    subject_id: str,
    predicate: str,
    object_id: str,
    source_chapter: str | None = None,
) -> Relation | None:
    """User-authored relation (the "correct" path). Creates the
    `(subject)-[predicate]->(object)` edge with confidence 1.0 and, crucially,
    **resurrects `valid_until` to NULL** if the tuple was previously
    invalidated (F5). This is a separate primitive from `create_relation` so
    the extraction writers can never accidentally revive a user-invalidated
    edge on re-extraction.

    Returns the edge, or `None` if either endpoint is missing for this user.
    """
    if not predicate:
        raise ValueError("predicate must be a non-empty string")
    if not subject_id or not object_id:
        raise ValueError("subject_id and object_id must be non-empty")
    rid = relation_id(
        user_id=user_id,
        subject_id=subject_id,
        predicate=predicate,
        object_id=object_id,
    )
    result = await run_write(
        session,
        _RECREATE_RELATION_CYPHER,
        user_id=user_id,
        relation_id=rid,
        subject_id=subject_id,
        object_id=object_id,
        predicate=predicate,
        source_chapter=source_chapter,
    )
    record = await result.single()
    if record is None:
        return None
    return _edge_props_to_relation(
        rel_props=dict(record["rel"]),
        subject=dict(record["subj"]),
        object_=dict(record["obj"]),
    )


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
