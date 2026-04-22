"""K11.5a — entities repository (Neo4j) — core CRUD slice.

Functions over `:Entity` nodes, all going through K11.4's
`run_read` / `run_write` so every Cypher query carries `$user_id`
and is verified at call time. No `session.run(...)` directly.

This slice ships:
  - merge_entity (idempotent upsert)
  - upsert_glossary_anchor (Pass 0 anchor pre-loader)
  - get_entity
  - find_entities_by_name (canonical name + display name)
  - archive_entity / restore_entity (soft delete)
  - delete_entities_with_zero_evidence (cascade cleanup)

Vector search, anchor-score recompute, and gap-candidate queries
are K11.5b. They depend on the same Pydantic model defined here.

Reference: KSA §3.4.E (two-layer anchoring), §3.4.F (archive
cascade), §5.0 (canonical_id).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)
from app.db.neo4j_repos.relations import Relation

logger = logging.getLogger(__name__)

__all__ = [
    "Entity",
    "EntityDetail",
    "VectorSearchHit",
    "SUPPORTED_VECTOR_DIMS",
    "ENTITIES_DETAIL_REL_CAP",
    "merge_entity",
    "upsert_glossary_anchor",
    "get_entity",
    "find_entities_by_name",
    "find_entities_by_vector",
    "link_to_glossary",
    "get_entity_by_glossary_id",
    "unlink_from_glossary",
    "recompute_anchor_score",
    "find_gap_candidates",
    "archive_entity",
    "restore_entity",
    "delete_entities_with_zero_evidence",
    "list_entities_filtered",
    "get_entity_with_relations",
]


# K11.5b — supported embedding dimensions per KSA §3.4.B.
# Mirrors the vector indexes created by the K11.3 schema runner.
# Tuple (not set) for stable iteration; lookup is O(n) on n=4 so
# no hash overhead matters.
SUPPORTED_VECTOR_DIMS: tuple[int, ...] = (384, 1024, 1536, 3072)


class Entity(BaseModel):
    """Pydantic projection of an `:Entity` node.

    Mirrors the property set documented in KSA §3.4.B + §3.4.E.
    Fields that are populated by K11.5b (embeddings) or K11.8
    (evidence_count) are present as Optional so the model can
    represent both a freshly-merged entity and a fully-anchored
    one without two separate types.
    """

    id: str
    user_id: str
    project_id: str | None = None
    name: str
    canonical_name: str
    kind: str
    aliases: list[str] = Field(default_factory=list)
    canonical_version: int = 1
    source_types: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    # Two-layer anchoring (KSA §3.4.E).
    glossary_entity_id: str | None = None
    anchor_score: float = 0.0

    # Soft-archive (KSA §3.4.F).
    archived_at: datetime | None = None
    archive_reason: str | None = None

    # K11.8 maintains this; K11.5a queries against the
    # `entity_user_evidence` composite index.
    evidence_count: int = 0
    # K11.5b: mention_count is the number of times this entity
    # was observed during extraction. K11.8 increments it; K11.5b's
    # recompute_anchor_score divides by max-per-project to derive
    # anchor_score for discovered (non-anchored) entities.
    mention_count: int = 0

    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_entity(node: Any) -> Entity:
    """Convert a neo4j Node (or dict-like) into an `Entity`.

    Tolerates both real `neo4j.graph.Node` instances (which expose
    `.items()` / dict access) and plain dicts so unit tests can
    feed fake rows through the same converter.

    Also converts every bolt-driver temporal value
    (`neo4j.time.{DateTime,Date,Time,Duration}`) into its stdlib
    equivalent via `.to_native()`. K11.5a-R1/R4 fix: scan all
    values rather than a hardcoded field list, so future fields
    (K11.5b embeddings, K11.8 evidence_extracted_at, …) work
    without touching this function.
    """
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return Entity.model_validate(data)


# ── merge_entity ──────────────────────────────────────────────────────


_MERGE_ENTITY_CYPHER = """
MERGE (e:Entity {id: $id})
ON CREATE SET
  e.user_id = $user_id,
  e.project_id = $project_id,
  e.name = $name,
  e.canonical_name = $canonical_name,
  e.kind = $kind,
  e.aliases = [$name],
  e.canonical_version = $canonical_version,
  e.source_types = [$source_type],
  e.confidence = $confidence,
  e.glossary_entity_id = NULL,
  e.anchor_score = 0.0,
  e.archived_at = NULL,
  e.evidence_count = 0,
  e.mention_count = 0,
  e.created_at = datetime(),
  e.updated_at = datetime()
ON MATCH SET
  e.aliases = CASE
    WHEN $name IN e.aliases THEN e.aliases
    ELSE e.aliases + $name
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


async def merge_entity(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    name: str,
    kind: str,
    source_type: str,
    confidence: float = 0.0,
    canonical_version: int = 1,
) -> Entity:
    """Idempotent upsert. Re-running with the same (user_id, project_id,
    name, kind) tuple returns the same node — no duplicates.

    Multi-tenant safety: the canonical_id hash includes user_id,
    so two users cannot produce the same id without a SHA-256
    collision (cosmologically improbable). The trailing
    `WITH e WHERE e.user_id = $user_id` exists ONLY to satisfy
    K11.4's `assert_user_id_param` — it does NOT actually defend
    against the impossible-by-construction id collision case,
    because the MERGE has already mutated the node by the time
    the WHERE filters the return. K11.5a-R1/R2: docstring fixed
    to be honest. The real defense is the canonical_id hash.
    """
    canonical_id = entity_canonical_id(
        user_id=user_id,
        project_id=project_id,
        name=name,
        kind=kind,
        canonical_version=canonical_version,
    )
    # canonical_name is the same string the ID hash is derived from.
    canonical_name = canonicalize_entity_name(name)

    result = await run_write(
        session,
        _MERGE_ENTITY_CYPHER,
        user_id=user_id,
        id=canonical_id,
        project_id=project_id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        canonical_version=canonical_version,
        source_type=source_type,
        confidence=confidence,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(
            f"merge_entity returned no row for id={canonical_id!r} "
            f"(user_id={user_id!r}) — driver contract violation"
        )
    return _node_to_entity(record["e"])


# ── upsert_glossary_anchor ────────────────────────────────────────────


_UPSERT_ANCHOR_CYPHER = """
MERGE (e:Entity {id: $id})
ON CREATE SET
  e.user_id = $user_id,
  e.project_id = $project_id,
  e.name = $name,
  e.canonical_name = $canonical_name,
  e.kind = $kind,
  e.aliases = $aliases,
  e.canonical_version = $canonical_version,
  e.source_types = ['glossary'],
  e.confidence = 1.0,
  e.glossary_entity_id = $glossary_entity_id,
  e.anchor_score = 1.0,
  e.archived_at = NULL,
  e.evidence_count = 0,
  e.mention_count = 0,
  e.created_at = datetime(),
  e.updated_at = datetime()
ON MATCH SET
  e.name = $name,
  e.canonical_name = $canonical_name,
  e.kind = $kind,
  e.aliases = $aliases,
  e.glossary_entity_id = $glossary_entity_id,
  e.anchor_score = 1.0,
  e.archived_at = NULL,
  e.updated_at = datetime()
WITH e
WHERE e.user_id = $user_id
RETURN e
"""


async def upsert_glossary_anchor(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    glossary_entity_id: str,
    name: str,
    kind: str,
    aliases: list[str] | None = None,
    canonical_version: int = 1,
) -> Entity:
    """Upsert a glossary-anchored entity.

    Used by the K13.0 Pass 0 anchor pre-loader to seed the graph
    with curated glossary entries before extraction begins. Setting
    `anchor_score = 1.0` makes these the highest-prior nodes during
    fuzzy entity resolution. Also called on `glossary.entity_created`
    / `glossary.entity_updated` events to keep the canonical fields
    (name, kind, aliases) mirrored from glossary-service.

    `glossary.entity_updated` uses the same query — ON MATCH
    overwrites name/kind/aliases because glossary is the SSOT for
    those fields. Other properties (anchor_score, evidence_count,
    archived_at clearing) are also overwritten to handle the
    "deleted then recreated in glossary" restore path.

    **Known limitation — glossary rename to a different canonical
    name.** The canonical_id is derived from `name`+`kind`. If a
    glossary edit changes the name such that
    `canonicalize_entity_name(new) != canonicalize_entity_name(old)`,
    this function creates a NEW node instead of renaming the
    existing one. K11.5b's `link_to_glossary` will own the rename
    path (lookup-by-glossary_entity_id, then update name in place).
    Tracked as a K11.5b acceptance criterion.
    """
    canonical_id = entity_canonical_id(
        user_id=user_id,
        project_id=project_id,
        name=name,
        kind=kind,
        canonical_version=canonical_version,
    )
    canonical_name = canonicalize_entity_name(name)
    aliases_with_display = list(aliases or [])
    if name not in aliases_with_display:
        aliases_with_display.insert(0, name)

    result = await run_write(
        session,
        _UPSERT_ANCHOR_CYPHER,
        user_id=user_id,
        id=canonical_id,
        project_id=project_id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        aliases=aliases_with_display,
        canonical_version=canonical_version,
        glossary_entity_id=glossary_entity_id,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(
            f"upsert_glossary_anchor returned no row for id={canonical_id!r}"
        )
    return _node_to_entity(record["e"])


# ── get_entity ────────────────────────────────────────────────────────


_GET_ENTITY_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
RETURN e
"""


async def get_entity(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
) -> Entity | None:
    """Look up an entity by its deterministic id. Returns None if
    no row matches — caller decides whether that's an error."""
    result = await run_read(
        session,
        _GET_ENTITY_CYPHER,
        user_id=user_id,
        id=canonical_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


# ── find_entities_by_name ─────────────────────────────────────────────


# K11.5a-R1/R1 fix: split the canonical-name and alias-membership
# arms into separate UNION subqueries. The original single-MATCH
# with `(canonical_name = X OR $name IN aliases)` defeated the
# `entity_user_canonical` composite index — Cypher's planner
# falls back to a label scan when an OR mixes one indexable and
# one non-indexable predicate. The UNION shape lets the first arm
# use the index and the second arm scan only when needed. UNION
# (not UNION ALL) deduplicates rows that match both arms.
#
# CALL { ... } subquery + WITH passes the parameters through
# without copying them on every row. The outer ORDER BY ranks
# the merged result set: anchored above discovered, then by
# confidence, then alphabetical.
_FIND_BY_NAME_CYPHER_ALL = """
CALL {
  WITH $user_id AS user_id, $project_id AS project_id,
       $canonical_name AS canonical_name
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND e.canonical_name = canonical_name
    AND (project_id IS NULL OR e.project_id = project_id)
  RETURN e
  UNION
  WITH $user_id AS user_id, $project_id AS project_id, $name AS name
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND name IN e.aliases
    AND (project_id IS NULL OR e.project_id = project_id)
  RETURN e
}
RETURN e
ORDER BY e.anchor_score DESC, e.confidence DESC, e.name ASC
"""

# K19c.4 — cap for list_user_entities. Shared between the Cypher
# LIMIT clause and the router's Query(le=ENTITIES_MAX_LIMIT) so a
# future raise on one layer can't drift from the other. Matches the
# LIST_ALL_MAX_LIMIT / LOGS_MAX_LIMIT conventions elsewhere.
ENTITIES_MAX_LIMIT = 200


_LIST_USER_ENTITIES_GLOBAL_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.project_id IS NULL
  AND e.archived_at IS NULL
RETURN e
ORDER BY e.updated_at DESC, e.name ASC
LIMIT $limit
"""


# K19d — cap on the detail endpoint's relation payload. 200 active
# relations on a single entity is already power-user territory
# (e.g., a protagonist in a long series); the FE can fetch more
# via a future /entities/{id}/relations paginated endpoint if
# someone actually hits the cap.
ENTITIES_DETAIL_REL_CAP = 200


class EntityDetail(BaseModel):
    """K19d.4 — `GET /v1/knowledge/entities/{id}` response payload.

    Relations are projected with both endpoint node id/name/kind so
    the FE can render `(subject)-[predicate]->(object)` without a
    second round-trip per row. Direction is inferable by comparing
    `relations[i].subject_id == entity.id`.
    """

    entity: Entity
    relations: list[Relation]
    relations_truncated: bool = False
    total_relations: int = 0


async def list_user_entities(
    session: CypherSession,
    *,
    user_id: str,
    scope: str = "global",
    limit: int = 50,
) -> list[Entity]:
    """K19c.4 — list a user's active entities by scope.

    `scope='global'` returns entities with no `project_id` — these
    are the cross-project preferences that surface in the Global
    tab's Preferences section. Project scope lands when K19d
    ships its entity browser.

    Excludes archived entities (`archived_at IS NULL`). Caller
    that needs the archived list should use the existing
    `find_entities_by_name` with `include_archived=True`.
    """
    if scope != "global":
        raise ValueError(f"unsupported scope {scope!r}; only 'global' is supported")
    effective_limit = max(1, min(limit, ENTITIES_MAX_LIMIT))
    result = await run_read(
        session,
        _LIST_USER_ENTITIES_GLOBAL_CYPHER,
        user_id=user_id,
        limit=effective_limit,
    )
    return [_node_to_entity(record["e"]) async for record in result]


_FIND_BY_NAME_CYPHER_ACTIVE = """
CALL {
  WITH $user_id AS user_id, $project_id AS project_id,
       $canonical_name AS canonical_name
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND e.canonical_name = canonical_name
    AND e.archived_at IS NULL
    AND (project_id IS NULL OR e.project_id = project_id)
  RETURN e
  UNION
  WITH $user_id AS user_id, $project_id AS project_id, $name AS name
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND name IN e.aliases
    AND e.archived_at IS NULL
    AND (project_id IS NULL OR e.project_id = project_id)
  RETURN e
}
RETURN e
ORDER BY e.anchor_score DESC, e.confidence DESC, e.name ASC
"""


async def find_entities_by_name(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    name: str,
    include_archived: bool = False,
) -> list[Entity]:
    """Find entities matching a display name within a user's namespace.

    Matches both the canonicalized form (via the `canonical_name`
    composite index) AND any historical alias spelling. Ranking
    prefers anchored entities (anchor_score=1.0) over discovered
    ones, then by confidence, then alphabetically.

    `project_id=None` means "search across all projects for this
    user" (cross-project alias resolution). When set, filters to
    one project and uses the `entity_user_project` index.
    """
    canonical_name = canonicalize_entity_name(name)
    cypher = (
        _FIND_BY_NAME_CYPHER_ALL if include_archived else _FIND_BY_NAME_CYPHER_ACTIVE
    )
    result = await run_read(
        session,
        cypher,
        user_id=user_id,
        project_id=project_id,
        name=name,
        canonical_name=canonical_name,
    )
    return [_node_to_entity(record["e"]) async for record in result]


# ── archive / restore ─────────────────────────────────────────────────


_ARCHIVE_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
SET e.archived_at = datetime(),
    e.anchor_score = 0.0,
    e.glossary_entity_id = NULL,
    e.archive_reason = $reason,
    e.updated_at = datetime()
RETURN e
"""

_RESTORE_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
SET e.archived_at = NULL,
    e.archive_reason = NULL,
    e.updated_at = datetime()
RETURN e
"""


async def archive_entity(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
    reason: str,
) -> Entity | None:
    """Soft-archive an entity (KSA §3.4.F glossary-deletion path).

    Preserves all EVIDENCED_BY edges, RELATES_TO edges, and
    timeline events — only `archived_at`, `anchor_score`, and
    `glossary_entity_id` change. The entity is hidden from
    default RAG queries via `WHERE e.archived_at IS NULL` filters
    elsewhere.

    **Scope: K11.5a only models the §3.4.F glossary-deleted path.**
    The function clears `glossary_entity_id` unconditionally,
    which is correct for `reason='glossary_deleted'` but would
    lose the link on a `'duplicate'` or manual `'user_archive'`
    archive of an anchored entity. Those non-§3.4.F flows are
    K17/K18 scope and will land as separate functions
    (`archive_duplicate`, `user_archive_entity`) when those
    surfaces exist. K11.5a-R1/R5: docstring narrowed.

    `reason` is stored as a free-text property for the audit log.
    Expected value at K11.5a is `'glossary_deleted'`.
    """
    result = await run_write(
        session,
        _ARCHIVE_CYPHER,
        user_id=user_id,
        id=canonical_id,
        reason=reason,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


async def restore_entity(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
) -> Entity | None:
    """Clear `archived_at` and `archive_reason`. Does NOT recompute
    `anchor_score` — that is K11.5b's `recompute_anchor_score`
    responsibility. After restore the score is 0.0 until the next
    recompute pass runs.

    If the user wants to immediately re-anchor a restored entity
    to its glossary entry, call `upsert_glossary_anchor` separately
    — that path explicitly resets `anchor_score` to 1.0.
    """
    result = await run_write(
        session,
        _RESTORE_CYPHER,
        user_id=user_id,
        id=canonical_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


# ── delete_entities_with_zero_evidence ────────────────────────────────


_DELETE_ZERO_EVIDENCE_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.evidence_count = 0
DETACH DELETE e
RETURN count(*) AS deleted
"""


async def delete_entities_with_zero_evidence(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Cascade-delete entities whose EVIDENCED_BY count is zero.

    Called after a partial re-extraction (`extraction_jobs.run`
    with delete-by-chapter cascade) once K11.8's evidence_count
    maintenance has marked orphaned entities. Uses the K11.3-R1
    `entity_user_evidence` composite index so the query latency
    is bounded by the calling user's churn, not the global graph.

    `DETACH DELETE` removes the node and all incident relationships
    in one statement — RELATES_TO edges to other entities, plus
    any remaining EVIDENCED_BY shells. Returns the number of nodes
    deleted so the cascade caller can log it.

    **DO NOT run concurrently with extraction.** `merge_entity`
    creates new nodes with `evidence_count = 0` and there is a
    window between merge and the first `EVIDENCED_BY` edge write
    (which K11.8 increments to ≥1) where a freshly-merged entity
    looks like an orphan. Concurrent cleanup would delete it.
    K11.5a-R1/R6: K11.8 is responsible for orchestrating the
    cleanup against the extraction job lifecycle — call this from
    a paused / completed job state, never mid-run.
    """
    result = await run_write(
        session,
        _DELETE_ZERO_EVIDENCE_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["deleted"])


# ── find_entities_by_vector ───────────────────────────────────────────


class VectorSearchHit(BaseModel):
    """One result row from `find_entities_by_vector`.

    `raw_score` is the cosine similarity from the Neo4j vector
    index; `weighted_score` is `raw_score * anchor_score` and
    is what callers should sort by for two-layer retrieval.
    Both are returned so the caller can log diagnostics or
    apply a different reranking on top.
    """

    entity: Entity
    raw_score: float
    weighted_score: float


# Vector queries always go through this template. The index name
# (`entity_embeddings_<dim>`) is passed as a STRING parameter to
# `db.index.vector.queryNodes` — it is NOT f-string interpolated
# into the cypher, satisfying the "no f-strings in cypher" rule.
#
# Oversample-and-rerank pattern: the vector index is global (no
# user_id filter), so we ask for `oversample_limit` candidates
# (typically `limit * 10`), then post-filter by user_id /
# project_id / archived_at and re-rank by `score * anchor_score`.
# The ORDER BY in the outer return is the source of truth — the
# vector index's own ordering is by raw similarity only.
_FIND_BY_VECTOR_CYPHER_ALL = """
CALL db.index.vector.queryNodes($index_name, $oversample_limit, $query_vector)
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  AND ($embedding_model IS NULL OR node.embedding_model = $embedding_model)
RETURN node AS e,
       score AS raw_score,
       score * coalesce(node.anchor_score, 0.0) AS weighted_score
ORDER BY weighted_score DESC, raw_score DESC
LIMIT $limit
"""

_FIND_BY_VECTOR_CYPHER_ACTIVE = """
CALL db.index.vector.queryNodes($index_name, $oversample_limit, $query_vector)
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  AND ($embedding_model IS NULL OR node.embedding_model = $embedding_model)
  AND node.archived_at IS NULL
RETURN node AS e,
       score AS raw_score,
       score * coalesce(node.anchor_score, 0.0) AS weighted_score
ORDER BY weighted_score DESC, raw_score DESC
LIMIT $limit
"""


async def find_entities_by_vector(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    query_vector: list[float],
    dim: int,
    embedding_model: str | None = None,
    limit: int = 10,
    include_archived: bool = False,
    oversample_factor: int = 10,
) -> list[VectorSearchHit]:
    """Two-layer semantic search over `:Entity` nodes.

    Routes to the dimension-specific vector index per KSA §3.4.B:
      384  → entity_embeddings_384  (small models, e.g. MiniLM)
      1024 → entity_embeddings_1024 (bge-m3, voyage-3, cohere)
      1536 → entity_embeddings_1536 (text-embedding-3-small)
      3072 → entity_embeddings_3072 (text-embedding-3-large)

    The vector index is global (no user_id filter). To get
    `limit` results that all belong to the calling user, we ask
    the index for `limit * oversample_factor` candidates, then
    post-filter by user_id / project_id / archived_at and re-rank
    by `score * anchor_score`. Default oversample factor is 10,
    which is conservative for low-tenant-density dev workloads;
    K11.5b acceptance criterion + Gate 12 will tune it from
    real-world tenant density once K17 starts populating data.

    Two-layer ranking: `weighted_score = raw_score * anchor_score`.
    Anchored entities (`anchor_score=1.0`) keep their full
    similarity; discovered entities (`anchor_score<1.0`) are
    proportionally penalized so canonical entries float to the
    top when raw scores are close. KSA §3.4.E + GraphRAG seed-graph
    research basis (arXiv:2404.16130).

    `embedding_model=None` matches any model — useful for tests
    where the project has no canonical embedding model set.
    Production callers should always pass the project's model so
    cross-model results are excluded (vector spaces are model-
    specific; cosine similarity between bge-m3 and openai-3-small
    is meaningless).
    """
    if dim not in SUPPORTED_VECTOR_DIMS:
        raise ValueError(
            f"unsupported vector dim {dim}; "
            f"must be one of {SUPPORTED_VECTOR_DIMS}"
        )
    if len(query_vector) != dim:
        raise ValueError(
            f"query_vector length {len(query_vector)} does not match dim {dim}"
        )
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if oversample_factor < 1:
        raise ValueError(f"oversample_factor must be >= 1, got {oversample_factor}")

    index_name = f"entity_embeddings_{dim}"
    cypher = (
        _FIND_BY_VECTOR_CYPHER_ALL
        if include_archived
        else _FIND_BY_VECTOR_CYPHER_ACTIVE
    )
    result = await run_read(
        session,
        cypher,
        user_id=user_id,
        index_name=index_name,
        oversample_limit=limit * oversample_factor,
        query_vector=query_vector,
        project_id=project_id,
        embedding_model=embedding_model,
        limit=limit,
    )
    hits: list[VectorSearchHit] = []
    async for record in result:
        hits.append(
            VectorSearchHit(
                entity=_node_to_entity(record["e"]),
                raw_score=float(record["raw_score"]),
                weighted_score=float(record["weighted_score"]),
            )
        )
    return hits


# ── link_to_glossary / unlink_from_glossary ───────────────────────────


# Look up the existing entity by its glossary FK. This is the
# rename-aware path: the canonical_id is hash-derived from the
# CURRENT name, so if the name changed in glossary the id won't
# match anymore — but the glossary_entity_id link still does.
_FIND_BY_GLOSSARY_ID_CYPHER = """
MATCH (e:Entity {glossary_entity_id: $glossary_entity_id})
WHERE e.user_id = $user_id
RETURN e
"""

# Promotion path: take a discovered entity (looked up by its
# current canonical_id) and stamp it with the glossary FK +
# anchor_score=1.0. Also overwrite name/canonical_name/kind/aliases
# from glossary because glossary is the SSOT for those fields.
_PROMOTE_TO_ANCHOR_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
SET e.glossary_entity_id = $glossary_entity_id,
    e.name = $name,
    e.canonical_name = $canonical_name,
    e.kind = $kind,
    e.aliases = $aliases,
    e.anchor_score = 1.0,
    e.archived_at = NULL,
    e.archive_reason = NULL,
    e.updated_at = datetime()
RETURN e
"""


async def link_to_glossary(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
    glossary_entity_id: str,
    name: str,
    kind: str,
    aliases: list[str] | None = None,
) -> Entity | None:
    """Promote a discovered entity to a glossary anchor.

    Used on the K-G-P-1 promotion path (user clicks "Promote to
    glossary" in the gap-report UI) and on the
    `glossary.entity_created` event when a new glossary entry is
    authored that matches an existing discovered entity.

    Sets `glossary_entity_id`, `anchor_score=1.0`, clears any
    archived state, and overwrites name/canonical_name/kind/
    aliases from the glossary payload (glossary is SSOT for those
    fields).

    **Rename-across-canonical fix (K11.5a docstring limitation).**
    `upsert_glossary_anchor` cannot rename an existing node when
    glossary changes the name to a different canonical form,
    because its MERGE key is `id` which is hash-derived from the
    name. `link_to_glossary` solves this by looking up the entity
    by `canonical_id` (caller knows it from the discovered side)
    and updating in place. The id stays stable post-rename — it
    no longer matches `entity_canonical_id(new_name, kind)`, but
    that's fine: future lookups go through glossary_entity_id or
    by name (which now matches via canonical_name + alias).

    Returns `None` if no entity matches the canonical_id under
    the calling user (e.g., someone passed a stale id or a
    cross-tenant id).
    """
    if not canonical_id:
        raise ValueError("canonical_id must be a non-empty string")
    if not glossary_entity_id:
        raise ValueError("glossary_entity_id must be a non-empty string")
    if not name:
        raise ValueError("name must be a non-empty string")
    if not kind:
        raise ValueError("kind must be a non-empty string")
    canonical_name = canonicalize_entity_name(name)
    if not canonical_name:
        raise ValueError(
            f"name {name!r} canonicalizes to empty string — refuse to link"
        )
    aliases_with_display = list(aliases or [])
    if name not in aliases_with_display:
        aliases_with_display.insert(0, name)

    result = await run_write(
        session,
        _PROMOTE_TO_ANCHOR_CYPHER,
        user_id=user_id,
        id=canonical_id,
        glossary_entity_id=glossary_entity_id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        aliases=aliases_with_display,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


async def get_entity_by_glossary_id(
    session: CypherSession,
    *,
    user_id: str,
    glossary_entity_id: str,
) -> Entity | None:
    """Look up an anchored entity by its glossary FK.

    The rename-aware companion to `get_entity`. After
    `link_to_glossary` updates an entity's name across canonical
    boundaries, the caller can find it again via this function
    even though `entity_canonical_id(new_name, kind)` no longer
    matches the stored id.

    Multi-row safety: the K11.3 schema enforces uniqueness on
    `e.glossary_entity_id` (K11.5b-R1/R1), so a properly-applied
    schema makes multi-row results impossible. The runtime
    safety net below catches the brief window where a misuse,
    a missing schema, or a race could produce two rows — instead
    of crashing on `result.single()`, we iterate, take the first
    row, and warn if a second row exists. Belt + suspenders.
    """
    if not glossary_entity_id:
        raise ValueError("glossary_entity_id must be a non-empty string")
    result = await run_read(
        session,
        _FIND_BY_GLOSSARY_ID_CYPHER,
        user_id=user_id,
        glossary_entity_id=glossary_entity_id,
    )
    first: Entity | None = None
    extra_count = 0
    async for record in result:
        if first is None:
            first = _node_to_entity(record["e"])
        else:
            extra_count += 1
    if extra_count:
        logger.error(
            "K11.5b-R1/R2: get_entity_by_glossary_id found %d extra row(s) "
            "for glossary_entity_id=%r user_id=%r — schema constraint "
            "entity_glossary_id_unique should have prevented this. "
            "Returning the first match; investigate the data.",
            extra_count,
            glossary_entity_id,
            user_id,
        )
    return first


# K11.5b-R1/R3: inline anchor_score recompute on unlink.
#
# The naive shape "SET anchor_score = 0.0" makes the entity
# invisible in vector ranking until the next batch
# recompute_anchor_score pass runs (because weighted_score =
# raw_score * 0). A user who clicks "unlink" expects the entity
# to lose its boost, NOT to vanish. We compute the post-unlink
# score inline from the same mention_count / max(mention_count)
# formula recompute uses, scoped to the entity's own project's
# discovered set.
#
# Two-phase Cypher: first MATCH the target, capture its
# project_id, then compute max(mention_count) over the
# discovered set in that project, then SET. We can't use a
# CALL { ... } subquery here because the inner aggregation needs
# a `WITH` boundary the outer SET respects.
_UNLINK_GLOSSARY_CYPHER = """
MATCH (target:Entity {id: $id})
WHERE target.user_id = $user_id
WITH target, target.project_id AS pid
OPTIONAL MATCH (peer:Entity)
WHERE peer.user_id = $user_id
  AND peer.project_id = pid
  AND peer.glossary_entity_id IS NULL
  AND peer.archived_at IS NULL
  AND peer.id <> target.id
WITH target, max(peer.mention_count) AS max_mentions
SET target.glossary_entity_id = NULL,
    target.anchor_score = CASE
      WHEN max_mentions IS NULL OR max_mentions = 0 THEN 0.0
      ELSE toFloat(target.mention_count) / toFloat(max_mentions)
    END,
    target.updated_at = datetime()
RETURN target AS e
"""


async def unlink_from_glossary(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
) -> Entity | None:
    """Manual unlink — clear `glossary_entity_id` without archiving.

    Per the K11.5 plan: "called when user manually unlinks". The
    entity stays visible in RAG queries; its `anchor_score` is
    immediately recomputed inline from
    `mention_count / max(mention_count)` over the discovered set
    in the same project, matching what
    `recompute_anchor_score` would assign on its next pass.

    K11.5b-R1/R3: inline recompute fix. The previous shape set
    `anchor_score = 0.0` and relied on a later batch recompute
    to restore a fractional score. That made a just-unlinked
    entity vanish from vector search ranking
    (`weighted_score = raw_score * 0`) — wrong UX for what is
    meant to be a "lose the boost" action, not a "hide the
    entity" action.

    Distinct from `archive_entity`: archive hides the entity from
    RAG entirely; unlink keeps it visible at its discovered-tier
    score. KSA §3.4.E does not specify the unlink path
    explicitly — this matches the K11.5 plan acceptance row.
    """
    if not canonical_id:
        raise ValueError("canonical_id must be a non-empty string")
    result = await run_write(
        session,
        _UNLINK_GLOSSARY_CYPHER,
        user_id=user_id,
        id=canonical_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


# ── recompute_anchor_score ────────────────────────────────────────────


# Two-step in one Cypher: compute max(mention_count) for the
# (user, project) bucket as a WITH binding, then update every
# discovered entity's anchor_score in proportion.
#
# Anchored entities (glossary_entity_id IS NOT NULL) are skipped
# — their score is fixed at 1.0 by upsert_glossary_anchor and
# link_to_glossary. The recompute is for discovered entities only.
#
# Archived entities (archived_at IS NOT NULL) are also skipped —
# they are out of the active retrieval set and their anchor_score
# stays at 0.
_RECOMPUTE_ANCHOR_SCORE_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.glossary_entity_id IS NULL
  AND e.archived_at IS NULL
WITH max(e.mention_count) AS max_mentions, collect(e) AS entities
UNWIND entities AS e
WITH e, max_mentions
SET e.anchor_score = CASE
  WHEN max_mentions IS NULL OR max_mentions = 0 THEN 0.0
  ELSE toFloat(e.mention_count) / toFloat(max_mentions)
END,
e.updated_at = datetime()
RETURN count(e) AS updated, max_mentions
"""


async def recompute_anchor_score(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> tuple[int, int]:
    """Recompute `anchor_score` for every discovered entity in the
    (user_id, project_id) bucket.

    Formula (KSA §3.4.E): `anchor_score = mention_count /
    max(mention_count)`. The result is a 0..1 score that biases
    semantic search toward frequently-mentioned entities even
    when they are not glossary-anchored. Anchored entities are
    skipped (their score is fixed at 1.0). Archived entities are
    skipped (their score stays at 0).

    `project_id=None` recomputes across all projects for the
    user, with `max(mention_count)` taken globally — usually
    not what you want. Pass `project_id` to scope.

    Returns `(updated_count, max_mentions)`. `max_mentions=0`
    means there are no discovered entities in the bucket and no
    rows were updated; the caller can use this to skip a no-op
    log line.
    """
    result = await run_write(
        session,
        _RECOMPUTE_ANCHOR_SCORE_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return (0, 0)
    return (int(record["updated"]), int(record["max_mentions"] or 0))


# ── find_gap_candidates ───────────────────────────────────────────────


# Discovered entities with no glossary link AND high mention
# count → these are the "gaps" the user should consider promoting.
# Sorted by mention_count descending so the most-mentioned gaps
# float to the top of the gap-report UI.
_FIND_GAP_CANDIDATES_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.glossary_entity_id IS NULL
  AND e.archived_at IS NULL
  AND e.mention_count >= $min_mentions
RETURN e
ORDER BY e.mention_count DESC, e.confidence DESC, e.name ASC
LIMIT $limit
"""


async def find_gap_candidates(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    min_mentions: int = 50,
    limit: int = 100,
) -> list[Entity]:
    """Discovered entities with no glossary link that the user
    should consider promoting.

    Powers the gap-report UI: "we found these entities in your
    book(s) but you haven't added them to the glossary yet." The
    `min_mentions` floor filters out one-off mentions that are
    almost always extraction noise (typos, fleeting references).
    KSA §3.4.E recommends 50 as a starting threshold; the gap-
    report UI may expose this as a user knob.
    """
    if min_mentions < 0:
        raise ValueError(f"min_mentions must be >= 0, got {min_mentions}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    result = await run_read(
        session,
        _FIND_GAP_CANDIDATES_CYPHER,
        user_id=user_id,
        project_id=project_id,
        min_mentions=min_mentions,
        limit=limit,
    )
    return [_node_to_entity(record["e"]) async for record in result]


# ── K19d.2 — list_entities_filtered ──────────────────────────────────
#
# The filter dimensions are documented on the router side (Query()
# params). Here we just build the WHERE clause defensively and page.
# All filters compose with AND; nulls short-circuit their branch so
# a caller that only wants `kind='character'` doesn't pay the search
# CONTAINS cost.
#
# Cardinality note: Neo4j doesn't have a cost estimate like a Postgres
# EXPLAIN, so we order by a stable composite key (mention_count DESC,
# name ASC, id ASC) to guarantee page boundaries are consistent across
# calls. The `id` tiebreaker matters when two entities share name AND
# mention_count — without it, LIMIT/SKIP pagination could silently
# duplicate or drop rows between pages.

# Shared WHERE clause for both the count and paged-rows queries so a
# future filter change only needs one edit. Kept as a string constant
# (not interpolated) because every filter predicate references the
# parameterized `$user_id` / `$project_id` / `$kind` / `$search` —
# no user-supplied value enters the Cypher text. Review-impl M1:
# pagination uses two separate queries (count + page) instead of a
# collect-then-unwind pattern that materialized every matching row
# into memory just to compute total.
_LIST_ENTITIES_FILTER_WHERE = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.archived_at IS NULL
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND ($kind IS NULL OR e.kind = $kind)
  AND (
    $search IS NULL
    OR toLower(e.name) CONTAINS toLower($search)
    OR any(alias IN e.aliases WHERE toLower(alias) CONTAINS toLower($search))
  )
"""

_LIST_ENTITIES_COUNT_CYPHER = _LIST_ENTITIES_FILTER_WHERE + """
RETURN count(e) AS total
"""

_LIST_ENTITIES_PAGE_CYPHER = _LIST_ENTITIES_FILTER_WHERE + """
RETURN e
ORDER BY e.mention_count DESC, e.name ASC, e.id ASC
SKIP $offset LIMIT $limit
"""


async def list_entities_filtered(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    kind: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Entity], int]:
    """K19d.2 — paginated browse with optional project / kind / search.

    Returns `(rows, total_count)`. `total_count` is the server-side
    count matching the filters *before* `SKIP`/`LIMIT`, so the FE can
    render "page 3 of N" without a second round-trip.

    Ordering: `mention_count DESC, name ASC, id ASC`. The id tiebreaker
    guarantees stable pagination even when name + mention collide.

    Archived entities are excluded. Global-scope entities (no
    `project_id`) are included when the `project_id` filter is None.

    Matching `search`:
      - case-insensitive `CONTAINS` on `name`
      - case-insensitive `CONTAINS` on any alias
      - no search → branch short-circuits so filter-free browse isn't
        taxed by the CONTAINS scan.

    Caller is responsible for validating `limit` / `offset` ranges;
    the repo trusts them. Router enforces Query(ge=1, le=200) on
    limit and Query(ge=0) on offset.

    **Implementation: two sequential queries** (count + page) rather
    than a single collect/UNWIND. The collect pattern materialized
    every matching node into server memory just to compute total —
    fine at hobby scale but a real OOM risk for a power-user with
    50k+ entities. Two round-trips (~10ms overhead) buys O(limit)
    memory instead of O(total).
    """
    count_result = await run_read(
        session,
        _LIST_ENTITIES_COUNT_CYPHER,
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        search=search,
    )
    count_record = await count_result.single()
    total = int(count_record["total"]) if count_record else 0
    if total == 0:
        return ([], 0)
    page_result = await run_read(
        session,
        _LIST_ENTITIES_PAGE_CYPHER,
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        search=search,
        offset=offset,
        limit=limit,
    )
    rows = [_node_to_entity(record["e"]) async for record in page_result]
    return rows, total


# ── K19d.4 — get_entity_with_relations ───────────────────────────────
#
# Fetches base entity + 1-hop :RELATES_TO edges in BOTH directions.
# We cap at `ENTITIES_DETAIL_REL_CAP` (200) and surface truncation
# via a flag so the FE can hide the detail panel's "all N relations"
# row count when the real number is higher. Total count is computed
# separately (cheap MATCH COUNT) so the FE doesn't have to infer.
#
# Filters `valid_until IS NULL` so superseded relations don't pollute
# the detail view — same convention as the L2 context loader.

_GET_ENTITY_WITH_RELATIONS_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
// Two CALL subqueries. Each must `collect()` / `count()` internally
// so the outer row isn't dropped when there are zero related edges
// (Neo4j's CALL semantics are join-like; an inner 0-row result kills
// the outer row). OPTIONAL MATCH + filter-null keeps the "no
// relations" case returning entity-only.
CALL {
  WITH e
  OPTIONAL MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
  WHERE (subj = e OR obj = e)
    AND r.user_id = $user_id
    AND r.valid_until IS NULL
  WITH r, subj, obj
  WHERE r IS NOT NULL
  ORDER BY r.confidence DESC, r.created_at DESC
  LIMIT $rel_cap
  RETURN collect({r: r, subj: subj, obj: obj}) AS edges
}
CALL {
  WITH e
  OPTIONAL MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
  WHERE (subj = e OR obj = e)
    AND r.user_id = $user_id
    AND r.valid_until IS NULL
  RETURN count(r) AS total
}
RETURN e, edges, total
"""


async def get_entity_with_relations(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    rel_cap: int = ENTITIES_DETAIL_REL_CAP,
) -> EntityDetail | None:
    """K19d.4 — entity detail with 1-hop active RELATES_TO edges.

    Returns None when the entity doesn't exist OR is owned by another
    user (cross-user collapses to 404 at the router per KSA §6.4).

    Edges are projected with both endpoints so the FE can render
    `(subj)-[predicate]->(obj)` without per-row re-fetching. The
    `Relation` projection fields `subject_name` / `subject_kind` /
    `object_name` / `object_kind` are populated from the endpoint
    nodes here — the canonical Relation nodes don't carry them.

    If `total > rel_cap`, `relations` contains the top-N by
    `(confidence DESC, created_at DESC)` and `relations_truncated=True`.
    """
    result = await run_read(
        session,
        _GET_ENTITY_WITH_RELATIONS_CYPHER,
        user_id=user_id,
        id=entity_id,
        rel_cap=rel_cap,
    )
    record = await result.single()
    if record is None:
        return None
    entity = _node_to_entity(record["e"])
    total = int(record["total"] or 0)

    relations: list[Relation] = []
    for edge in record["edges"]:
        r = edge["r"]
        subj = edge["subj"]
        obj = edge["obj"]
        r_data = dict(r.items() if hasattr(r, "items") else r)
        # Bolt-driver temporal conversions — same pattern as
        # _node_to_entity so Relation's datetime fields round-trip
        # into stdlib types.
        for k, v in list(r_data.items()):
            if v is not None and hasattr(v, "to_native"):
                r_data[k] = v.to_native()
        subj_data = dict(subj.items() if hasattr(subj, "items") else subj)
        obj_data = dict(obj.items() if hasattr(obj, "items") else obj)
        r_data["subject_name"] = subj_data.get("name")
        r_data["subject_kind"] = subj_data.get("kind")
        r_data["object_name"] = obj_data.get("name")
        r_data["object_kind"] = obj_data.get("kind")
        relations.append(Relation.model_validate(r_data))

    return EntityDetail(
        entity=entity,
        relations=relations,
        relations_truncated=total > len(relations),
        total_relations=total,
    )
