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

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)

__all__ = [
    "Entity",
    "merge_entity",
    "upsert_glossary_anchor",
    "get_entity",
    "find_entities_by_name",
    "archive_entity",
    "restore_entity",
    "delete_entities_with_zero_evidence",
]


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
