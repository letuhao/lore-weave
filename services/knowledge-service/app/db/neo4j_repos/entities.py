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

from pydantic import BaseModel, Field, computed_field

from app.db.neo4j_helpers import CypherSession, run_read, run_read_any_owner, run_write
from app.db.repositories import VersionMismatchError
from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)
from app.db.neo4j_repos.relations import Relation, relation_id

logger = logging.getLogger(__name__)

__all__ = [
    "Entity",
    "EntityDetail",
    "VectorSearchHit",
    "SUPPORTED_VECTOR_DIMS",
    "ENTITIES_DETAIL_REL_CAP",
    "ENTITY_STATUSES",
    "ENTITY_SORT_KEYS",
    "merge_entity",
    "upsert_glossary_anchor",
    "get_entity",
    "get_entity_by_id_any_owner",
    "find_entities_by_name",
    "find_entities_by_vector",
    "set_entity_embedding",
    "find_entities_needing_embedding",
    "link_to_glossary",
    "get_entity_by_glossary_id",
    "unlink_from_glossary",
    "reset_glossary_anchors",
    "recompute_anchor_score",
    "find_gap_candidates",
    "archive_entity",
    "user_archive_entity",
    "restore_entity",
    "delete_entities_with_zero_evidence",
    "list_entities_filtered",
    "get_entity_with_relations",
    "get_neighborhood_by_glossary_id",
    "update_entity_fields",
    "unlock_entity_user_edited",
    "merge_entities",
    "MergeEntitiesError",
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

    # K19d γ-a: set to True by `update_entity_fields` (backing the
    # PATCH /entities/{id} route). Once true, `merge_entity`'s
    # ON MATCH branch no longer re-adds extracted name variants to
    # `aliases` — the extractor can't silently undo a user's edit.
    # Existing nodes created before K19d γ-a lack this property and
    # read-path `coalesce(user_edited, false) = false` treats them
    # as un-edited, preserving the old behaviour on re-extraction.
    user_edited: bool = False

    # C9 (D-K19d-γa-01): optimistic-concurrency counter. Bumped by
    # every user-facing write (PATCH, unlock, user-merge, extraction
    # merge_entity). Pre-C9 nodes without the property read as 1 via
    # `_node_to_entity`'s coalesce — the first write after C9 will
    # mint the value. Router hands out weak ETags of the form
    # `W/"<version>"` and requires If-Match on PATCH.
    version: int = 1

    # Cycle 73e: True when minted by Pass2 writer's Tier-B autocreate
    # (relation subject/object unresolved against extracted entity
    # list AND not in anchors). Cleared on legit re-extraction via
    # `_MERGE_ENTITY_CYPHER`'s ON MATCH promotion CASE. Legacy nodes
    # without the property read as False via `_node_to_entity` +
    # `coalesce(e.auto_created, false)` Cypher idiom.
    auto_created: bool = False

    created_at: datetime | None = None
    updated_at: datetime | None = None

    # C8 (C8-entity-status LOCKED) — DERIVED status, never a stored
    # column. The two-layer anchor model already carries the source
    # fields (`archived_at`, `glossary_entity_id`); `status` is a pure
    # projection over them so the FE renders ⭐/💭/📦 without inferring
    # the precedence itself.
    #
    # Precedence (BE+FE MUST agree): `archived` wins over `canonical`.
    # A soft-archive (`_ARCHIVE_CYPHER`) already nulls
    # `glossary_entity_id`, so in practice the two are mutually
    # exclusive — but if a future write path ever leaves both set, an
    # archived entity must read as archived (it is out of the active
    # retrieval set), not canonical. `discovered` = unanchored + active.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        if self.archived_at is not None:
            return "archived"
        if self.glossary_entity_id is not None:
            return "canonical"
        return "discovered"


# C8 — closed set of derivable statuses, exposed so the router's
# Query(enum) validation + the filter Cypher reference one source of
# truth instead of three hardcoded literals.
ENTITY_STATUSES: tuple[str, ...] = ("canonical", "discovered", "archived")

# C8 — sort keys accepted by `list_entities_filtered`. `mention_count`
# is the legacy default (browse-by-frequency); `anchor_score` surfaces
# the two-layer-anchored entities first (the semantic-curation view).
ENTITY_SORT_KEYS: tuple[str, ...] = ("mention_count", "anchor_score")


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
    # C9 (D-K19d-γa-01): pre-C9 entities lack the `version` property.
    # Coalesce to 1 so reads succeed without a batch backfill; the
    # first post-C9 write will mint a real value. Matches the
    # `coalesce(user_edited, false)` backfill idiom already in use.
    #
    # /review-impl HIGH lock: this default MUST match every Cypher
    # `coalesce(e.version, N)` / `coalesce(t.version, N)` in this
    # module. If they drift, pre-C9 entities become permanently
    # uneditable — FE reads version=1, sends If-Match=1, but Cypher
    # compares against current_version=0 → 412 forever. Verified by
    # `test_cypher_version_coalesce_default_matches_read_path`.
    if data.get("version") is None:
        data["version"] = 1
    # Cycle 73e: legacy (pre-73e) entities lack `auto_created`. Coalesce
    # to False at read time; Cypher read sites mirror via `coalesce(
    # e.auto_created, false)` per the same backfill idiom.
    if data.get("auto_created") is None:
        data["auto_created"] = False
    return Entity.model_validate(data)


# ── merge_entity ──────────────────────────────────────────────────────


# K19d γ-a: the ON MATCH aliases CASE has three arms. The first
# (`coalesce(e.user_edited, false) = true`) is the K19d γ-a lock —
# once the user has edited aliases via PATCH, the extractor must
# not silently re-add removed variants. The coalesce handles pre-
# γ-a nodes lacking the property (null → false = un-edited) so
# existing extraction behaviour is preserved until a user explicitly
# touches the row. The remaining arms are the pre-γ-a append logic.
#
# Cycle 73e: `auto_created` flag tracks entities minted by the
# Pass2 writer's Tier-B autocreate path (relation subject/object
# unresolved against extracted entity list AND not in anchors).
# Read sites MUST use `coalesce(e.auto_created, false)` because
# legacy nodes (pre-73e) lack the property — same backfill idiom
# as `user_edited` and `version`. ON MATCH promotion: any non-auto
# write (default `$auto_created = false`) clears the flag — so
# a real extractor hit on a previously-auto-created entity promotes
# it (cycle 73e M1 fold).
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
  e.provenances = [$provenance],
  e.confidence = $confidence,
  e.glossary_entity_id = NULL,
  e.anchor_score = 0.0,
  e.archived_at = NULL,
  e.evidence_count = 0,
  e.mention_count = 0,
  e.user_edited = false,
  e.version = 1,
  e.auto_created = $auto_created,
  e.created_at = datetime(),
  // T4.1 flywheel — the extraction job that first minted this node (net-new
  // attribution). Set ONLY on create, so it permanently credits the creating
  // job; a later match by another job never changes it. NULL for non-job writes
  // and pre-T4.1 nodes.
  e.created_job_id = $job_id,
  e.updated_at = datetime()
ON MATCH SET
  e.aliases = CASE
    WHEN coalesce(e.user_edited, false) = true THEN e.aliases
    WHEN $name IN e.aliases THEN e.aliases
    ELSE e.aliases + $name
  END,
  e.source_types = CASE
    WHEN $source_type IN e.source_types THEN e.source_types
    ELSE e.source_types + $source_type
  END,
  // CM5 provenance — accumulate the deduped set of authorship origins
  // (PO: accumulate). Mirrors source_types. coalesce guards pre-CM5 nodes
  // that have no provenances property yet.
  e.provenances = CASE
    WHEN $provenance IN coalesce(e.provenances, []) THEN e.provenances
    ELSE coalesce(e.provenances, []) + $provenance
  END,
  e.confidence = CASE
    WHEN $confidence > e.confidence THEN $confidence
    ELSE e.confidence
  END,
  e.auto_created = CASE
    WHEN $auto_created = false THEN false
    ELSE coalesce(e.auto_created, false)
  END,
  e.version = coalesce(e.version, 1) + 1,
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
    auto_created: bool = False,
    provenance: str = "human_authored",
    job_id: str | None = None,
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

    Cycle 73e: `auto_created` defaults False (legit extractor write).
    When True, marks the entity as minted by Pass2 writer's autocreate
    path (relation subject/object unresolved). ON MATCH promotion
    semantics: a later auto_created=False call (real extraction)
    clears the flag, so the "show only auto-created" UI list shrinks
    naturally on legit re-extraction.
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
        auto_created=auto_created,
        provenance=provenance,
        job_id=job_id,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(
            f"merge_entity returned no row for id={canonical_id!r} "
            f"(user_id={user_id!r}) — driver contract violation"
        )
    return _node_to_entity(record["e"])


# ── merge_entity_at_id (C17 alias-map redirect target) ────────────────


async def merge_entity_at_id(
    session: CypherSession,
    *,
    user_id: str,
    id: str,
    project_id: str | None,
    name: str,
    kind: str,
    source_type: str,
    confidence: float = 0.0,
    provenance: str = "human_authored",
) -> "Entity | None":
    """C17 — upsert at a caller-supplied entity id (no SHA derivation).

    Used by ``resolve_or_merge_entity`` after an alias-map redirect
    hit: the lookup said "name X redirects to id Y", so MATCH on Y
    directly + apply the standard ON MATCH alias/source_type/confidence
    union semantics inline. Cannot delegate to ``_MERGE_ENTITY_CYPHER``
    because that helper's ``ON CREATE`` branch would resurrect a
    deleted target as a fresh shell with the supplied name+kind,
    silently corrupting the redirect.

    Returns ``None`` when the supplied id does not match any existing
    node (caller should fall through to the SHA-hash path with a
    WARNING log — alias-map row points at a deleted target). Distinct
    from ``merge_entity`` which always creates if missing.

    The canonical_name is derived from the supplied name so the ON
    MATCH branch correctly registers the new spelling as an alias.
    canonical_version is fixed at 1 because the redirect target was
    written under the same version that resolved it.
    """
    canonical_name = canonicalize_entity_name(name)
    # We deliberately use a different Cypher than _MERGE_ENTITY_CYPHER
    # because ON CREATE here would resurrect a deleted target — the
    # alias-map row pointed at it, so creating a fresh shell with the
    # SUPPLIED name+kind would silently corrupt the redirect.
    # Instead: MATCH-only; if the node doesn't exist, return None and
    # let the caller fall through.
    result = await run_write(
        session,
        """
        MATCH (e:Entity {id: $id})
        WHERE e.user_id = $user_id
        SET e.aliases = CASE
              WHEN coalesce(e.user_edited, false) = true THEN e.aliases
              WHEN $name IN e.aliases THEN e.aliases
              ELSE e.aliases + $name
            END,
            e.source_types = CASE
              WHEN $source_type IN e.source_types THEN e.source_types
              ELSE e.source_types + $source_type
            END,
            e.provenances = CASE
              WHEN $provenance IN coalesce(e.provenances, []) THEN e.provenances
              ELSE coalesce(e.provenances, []) + $provenance
            END,
            e.confidence = CASE
              WHEN $confidence > e.confidence THEN $confidence
              ELSE e.confidence
            END,
            e.version = coalesce(e.version, 1) + 1,
            e.updated_at = datetime()
        RETURN e
        """,
        user_id=user_id,
        id=id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        source_type=source_type,
        confidence=confidence,
        provenance=provenance,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


# ── upsert_glossary_anchor ────────────────────────────────────────────


# `__was_created` is a TRANSIENT create-vs-match marker: ON CREATE sets it true,
# it is read into the `was_created` return column, then REMOVEd in the same
# statement so it never persists on the node. This is how the counted projection
# (kg_project_entities_to_nodes / WS-4B) reports {nodes_created, nodes_existing}
# without a fragile created_at==updated_at heuristic. ON MATCH never sets it, so
# `coalesce(e.__was_created, false)` is false on an existing node. Existing callers
# that read only `record["e"]` are unaffected by the extra return column.
_UPSERT_ANCHOR_CYPHER = """
MERGE (e:Entity {id: $id})
ON CREATE SET
  e.__was_created = true,
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
WITH e, coalesce(e.__was_created, false) AS was_created
REMOVE e.__was_created
WITH e, was_created
WHERE e.user_id = $user_id
RETURN e, was_created
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
    entity, _ = await upsert_glossary_anchor_counted(
        session,
        user_id=user_id,
        project_id=project_id,
        glossary_entity_id=glossary_entity_id,
        name=name,
        kind=kind,
        aliases=aliases,
        canonical_version=canonical_version,
    )
    return entity


async def upsert_glossary_anchor_counted(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    glossary_entity_id: str,
    name: str,
    kind: str,
    aliases: list[str] | None = None,
    canonical_version: int = 1,
) -> tuple[Entity, bool]:
    """Like `upsert_glossary_anchor`, but ALSO reports whether the node was
    newly CREATED (`True`) or already existed and was updated (`False`) — the
    accounting `kg_project_entities_to_nodes` (WS-4B) needs to return
    `{nodes_created, nodes_existing}`. The MERGE stays idempotent; the flag is
    the transient `__was_created` marker (see `_UPSERT_ANCHOR_CYPHER`)."""
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
    return _node_to_entity(record["e"]), bool(record["was_created"])


# ── existing_entity_node_ids (WS-4B fail-fast endpoint precheck) ───────


_EXISTING_NODE_IDS_CYPHER = """
UNWIND $ids AS wanted
MATCH (e:Entity {id: wanted})
WHERE e.user_id = $user_id
RETURN e.id AS id
"""


async def existing_entity_node_ids(
    session: CypherSession,
    *,
    user_id: str,
    ids: list[str],
) -> set[str]:
    """Return the subset of `ids` that already exist as `:Entity` nodes for
    `user_id`. Used by `kg_propose_edge`'s fail-fast endpoint precheck (WS-4B):
    an edge whose endpoints aren't nodes yet would park then fail at confirm
    (`create_relation` matches endpoints by `Entity.id`), so we reject it up
    front with `KG_ENDPOINT_NOT_NODE`. Matching by `id` mirrors exactly how the
    confirm-time write resolves the endpoints."""
    if not ids:
        return set()
    result = await run_read(
        session,
        _EXISTING_NODE_IDS_CYPHER,
        user_id=user_id,
        ids=list(ids),
    )
    return {record["id"] async for record in result}


# ── resolve_kg_entity_id_by_glossary_id (W11-M2 reader bridge) ─────────

_KG_ID_BY_GLOSSARY_ID_CYPHER = """
MATCH (e:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
WHERE ($project_id IS NULL OR e.project_id = $project_id)
  AND e.archived_at IS NULL
RETURN e.id AS id
LIMIT 1
"""


async def resolve_kg_entity_id_by_glossary_id(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    glossary_entity_id: str,
) -> str | None:
    """W11-M2 — map a GLOSSARY entity id (what the reader tools surface from the
    canon cast) to its anchored KG `:Entity.id` (a canonical hash), so `lore_entity`
    can read the entity's KG facts/status. Scoped to `user_id` (the owner) AND
    `project_id` (the reader's granted book) — a glossary id from a DIFFERENT project
    the owner happens to own resolves to None here, so the KG read can't cross the
    grant boundary. Returns None when the canon entity has no KG anchor (→ the reader
    gets canon-only, no KG facts) or the id doesn't belong to this project."""
    if not glossary_entity_id:
        return None
    result = await run_read(
        session,
        _KG_ID_BY_GLOSSARY_ID_CYPHER,
        user_id=user_id,
        project_id=project_id,
        glossary_entity_id=glossary_entity_id,
    )
    async for record in result:
        return record["id"]
    return None


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


# Any-owner lookup: matches by the globally-unique `Entity.id` with NO
# `user_id` filter. `Entity.id` is a deterministic, globally-unique key
# (schema uniqueness constraint), so this cannot collide across tenants —
# it returns the single owning entity (incl. its owner `user_id` +
# `project_id`).
_GET_ENTITY_ANY_OWNER_CYPHER = """
MATCH (e:Entity {id: $id})
RETURN e
"""


async def get_entity_by_id_any_owner(
    session: CypherSession,
    canonical_id: str,
) -> Entity | None:
    """Look up an entity by its globally-unique id WITHOUT a `user_id`
    filter. Returns the entity incl. its owner `user_id` + `project_id`,
    or None if no node matches.

    SECURITY: this bypasses the per-tenant `user_id` filter that every
    other `:Entity` read enforces. It is safe ONLY because `Entity.id` is
    globally unique (no cross-tenant collision), and it MUST be paired with
    an explicit grant check on the returned entity's project before any of
    its data is exposed to the caller. Used by
    `_resolve_entity_project_grant` to resolve-to-owner for the grant-gated
    edge timeline (D-KG-LD-GRANTEE-TIMELINE)."""
    # run_read() REQUIRES a user_id and asserts the cypher references $user_id — this
    # query intentionally does neither, so it raised TypeError on every call and
    # kg_entity_edge_timeline (its only consumer) could never work.
    result = await run_read_any_owner(
        session,
        _GET_ENTITY_ANY_OWNER_CYPHER,
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
       $canonical_name AS canonical_name, $exclude_project_ids AS exclude_project_ids
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND e.canonical_name = canonical_name
    AND (project_id IS NULL OR e.project_id = project_id)
    AND (size(exclude_project_ids) = 0 OR NOT coalesce(e.project_id, '') IN exclude_project_ids)
  RETURN e
  UNION
  WITH $user_id AS user_id, $project_id AS project_id, $name AS name,
       $exclude_project_ids AS exclude_project_ids
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND name IN e.aliases
    AND (project_id IS NULL OR e.project_id = project_id)
    AND (size(exclude_project_ids) = 0 OR NOT coalesce(e.project_id, '') IN exclude_project_ids)
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


_LIST_PROJECT_ENTITY_NAMES_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.project_id = $project_id
  AND e.archived_at IS NULL
RETURN e.name AS name, e.aliases AS aliases
"""


async def list_project_entity_names(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
) -> list[tuple[str, list[str]]]:
    """M-recall — every active entity's display name + aliases for a project.

    Feeds the Aho-Corasick anchor dictionary (`app.context.anchors`) that lets the
    CJK/VI grounding path resolve message anchors the whitespace-blind intent
    classifier can't. Owner + project scoped (tenancy). Returns `(name, aliases)`
    pairs; the automaton adds every surface form (name + aliases) as a pattern and
    emits `name` as the canonical anchor `find_entities_by_name` then resolves.
    """
    result = await run_read(
        session,
        _LIST_PROJECT_ENTITY_NAMES_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    out: list[tuple[str, list[str]]] = []
    async for rec in result:
        name = rec["name"]
        if not name:
            continue
        aliases = [str(a) for a in (rec["aliases"] or []) if a]
        out.append((str(name), aliases))
    return out


_MOST_CONNECTED_ENTITY_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.project_id = $project_id
  AND e.archived_at IS NULL
OPTIONAL MATCH (e)-[r:RELATES_TO]-()
WHERE r.user_id = $user_id AND r.valid_until IS NULL
WITH e, count(r) AS degree
RETURN e.name AS name, degree
ORDER BY degree DESC, coalesce(e.anchor_score, 0) DESC, e.name ASC
LIMIT 1
"""


async def get_most_connected_entity(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
) -> str | None:
    """M-recall role-resolution — the project's most structurally-central entity
    (highest live-relation degree), the reliable "protagonist" signal for a novel.

    Used to resolve role-referenced anchors ("主角"/"the protagonist" → 张若尘)
    the dictionary matcher can't (the role term isn't an entity name). Degree
    (not anchor_score alone) because the most-connected node in a story graph is
    almost always the lead character, whereas a high-salience node could be a
    place. Owner+project scoped; None for an empty graph. The caller caches it."""
    result = await run_read(
        session,
        _MOST_CONNECTED_ENTITY_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None or not record["name"]:
        return None
    return str(record["name"])


_FIND_BY_NAME_CYPHER_ACTIVE = """
CALL {
  WITH $user_id AS user_id, $project_id AS project_id,
       $canonical_name AS canonical_name, $exclude_project_ids AS exclude_project_ids
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND e.canonical_name = canonical_name
    AND e.archived_at IS NULL
    AND (project_id IS NULL OR e.project_id = project_id)
    AND (size(exclude_project_ids) = 0 OR NOT coalesce(e.project_id, '') IN exclude_project_ids)
  RETURN e
  UNION
  WITH $user_id AS user_id, $project_id AS project_id, $name AS name,
       $exclude_project_ids AS exclude_project_ids
  MATCH (e:Entity)
  WHERE e.user_id = user_id
    AND name IN e.aliases
    AND e.archived_at IS NULL
    AND (project_id IS NULL OR e.project_id = project_id)
    AND (size(exclude_project_ids) = 0 OR NOT coalesce(e.project_id, '') IN exclude_project_ids)
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
    exclude_project_ids: list[str] | None = None,
) -> list[Entity]:
    """Find entities matching a display name within a user's namespace.

    Matches both the canonicalized form (via the `canonical_name`
    composite index) AND any historical alias spelling. Ranking
    prefers anchored entities (anchor_score=1.0) over discovered
    ones, then by confidence, then alphabetically.

    `project_id=None` means "search across all projects for this
    user" (cross-project alias resolution). When set, filters to
    one project and uses the `entity_user_project` index.

    D16 (spec 07 §Q4) — `exclude_project_ids` removes matches from those projects even under the
    all-projects fallback. The memory_* tools pass the user's ASSISTANT project ids here when a
    session has no explicit project, so a novel-writing session can never surface work-diary entities.
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
        exclude_project_ids=list(exclude_project_ids or []),
    )
    return [_node_to_entity(record["e"]) async for record in result]


async def resolve_participant_anchors(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    names: list[str],
) -> dict[str, str]:
    """KG-TL Option A (D-KG-TL-PARTICIPANT-ANCHOR) — resolve participant NAME →
    glossary ``entity_id`` (the durable anchor stored on
    ``:Event.participant_entity_ids``).

    Identical resolution to the read-time timeline localizer: for each DISTINCT
    name take the best :func:`find_entities_by_name` match that carries a glossary
    anchor (the helper ranks anchored entities first). A name with no anchored
    match is OMITTED from the result — the caller maps it to the ``""`` sentinel
    (Neo4j lists can't hold nulls) → source fallback + marker (AC-T3, never a
    silent mix). Best-effort: a per-name resolution error is logged and skipped,
    never raised into the write/backfill path. One session for the whole batch.
    """
    out: dict[str, str] = {}
    for name in {n for n in names if n and n.strip()}:
        try:
            matches = await find_entities_by_name(
                session, user_id=user_id, project_id=project_id, name=name,
            )
        except Exception as exc:  # best-effort — a miss never breaks the write
            logger.warning("participant anchor resolution failed for %r: %s", name, exc)
            continue
        for ent in matches:
            if ent.glossary_entity_id:
                out[name] = ent.glossary_entity_id
                break
    return out


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

# D-K19c.4-01 — user-archive variant: same soft-archive as `_ARCHIVE_CYPHER`
# but PRESERVES both `glossary_entity_id` (the glossary anchor FK) AND
# `anchor_score`. A user "delete" is a "hide now, restore later" gesture; the
# glossary entry still exists. Unlike §3.4.F glossary-deletion (FK gone →
# score 0 is consistent), here we keep the anchor intact so a later
# `restore_entity` brings the entity back FULLY anchored — `restore_entity`
# does NOT recompute the score, so zeroing it here would leave a restored,
# FK-anchored entity ranking as unanchored (weighted_score = raw × 0) until
# the next recompute pass. Archived rows are excluded from all queries by the
# `archived_at IS NULL` filter, so the preserved score is inert while hidden.
_USER_ARCHIVE_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
SET e.archived_at = datetime(),
    e.archive_reason = $reason,
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


async def user_archive_entity(
    session: CypherSession,
    *,
    user_id: str,
    canonical_id: str,
    reason: str = "user_archived",
) -> Entity | None:
    """D-K19c.4-01 — soft-archive an entity for the USER "hide it" flow,
    PRESERVING both its `glossary_entity_id` anchor AND its `anchor_score`
    so a later `restore_entity` re-shows it FULLY anchored (the glossary
    entry still exists). `restore_entity` does NOT recompute the score, so
    zeroing it here would leave a restored, FK-anchored entity ranking as
    unanchored until the next recompute pass.

    Same idempotence + edge-preservation as `archive_entity` (no
    `archived_at IS NULL` guard; EVIDENCED_BY / RELATES_TO / timeline edges
    untouched) — the difference is that the glossary FK + score are kept.
    Use `archive_entity` (which NULLs the FK + zeroes the score) for the
    §3.4.F glossary-deleted path, where the glossary entry itself is gone.
    """
    result = await run_write(
        session,
        _USER_ARCHIVE_CYPHER,
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


# ── K17 entity-embedding WRITE pipeline ────────────────────────────────
#
# The read counterpart (find_entities_by_vector, above) expects every
# anchored :Entity to carry `embedding_{dim}` + `embedding_model`. K17 is the
# producer that stamps them. Mirrors the passage embedding write
# (app/db/neo4j_repos/passages.py upsert_passage): dim-validated f-string into
# the property name (closed-set, no injection), only the dim-matching property
# written so mixed-model tenants coexist. Unlike passages (chapter-scoped,
# MERGE-on-ingest), an entity already exists — we MATCH and SET in place.

# `embed_prop` is f-string-substituted; it is validated against the closed
# SUPPORTED_VECTOR_DIMS set below, so there is no injection surface.
_SET_ENTITY_EMBEDDING_CYPHER_TEMPLATE = """
MATCH (e:Entity {{id: $id}})
WHERE e.user_id = $user_id
SET e.{embed_prop} = $embedding,
    e.embedding_model = $embedding_model,
    e.embedding_version = $embedding_version
RETURN e.id AS id
"""
# NOTE: deliberately does NOT touch `e.updated_at`. Embedding is a DERIVED-data
# write, not a content edit; bumping the shared `updated_at` would make an
# embedded entity falsely float to the top of the recency-ordered listing
# queries (`ORDER BY e.updated_at DESC` — list_entities_filtered etc.) and skew
# `find_entities_needing_embedding`'s own newest-content-first ordering.
# `embedding_version` is the embed-freshness tracker (review-impl MED).


async def set_entity_embedding(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    embedding: list[float],
    embedding_dim: int,
    embedding_model: str,
    embedding_version: int,
) -> bool:
    """Stamp a per-dim embedding on an EXISTING `:Entity` (K17).

    MATCH (not MERGE) — the entity must already exist (created by the Pass-2
    writer / glossary anchor). Writes only the `embedding_{dim}` property that
    matches `embedding_dim`; the other dim properties stay untouched so
    mixed-model tenants (projects on different embedding models) coexist —
    same invariant as `upsert_passage`. `embedding_version` records the
    entity's `version` at embed time so the dirty-signal in
    `find_entities_needing_embedding` can detect content drift. Returns True
    when a row was updated, False when no entity matched (id/user mismatch)."""
    if embedding_dim not in SUPPORTED_VECTOR_DIMS:
        raise ValueError(
            f"unsupported embedding_dim {embedding_dim}; "
            f"must be one of {SUPPORTED_VECTOR_DIMS}"
        )
    if len(embedding) != embedding_dim:
        raise ValueError(
            f"embedding length {len(embedding)} does not match dim {embedding_dim}"
        )
    cypher = _SET_ENTITY_EMBEDDING_CYPHER_TEMPLATE.format(
        embed_prop=f"embedding_{embedding_dim}",
    )
    result = await run_write(
        session,
        cypher,
        user_id=user_id,
        id=entity_id,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
    )
    record = await result.single()
    return record is not None


# Anchored entities whose embedding is MISSING or STALE for the project's
# current model: never embedded, embedded under a different model, or whose
# content (version) advanced since the last embed. Scoped to anchored
# (glossary_entity_id) + active (not archived) entities — exactly the set the
# read path (find_entities_by_vector) can surface, so we never embed an orphan
# KG node that would never be returned anyway.
_FIND_NEEDING_EMBEDDING_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.glossary_entity_id IS NOT NULL
  AND e.archived_at IS NULL
  AND (
    e.embedding_model IS NULL
    OR e.embedding_model <> $embedding_model
    OR coalesce(e.embedding_version, -1) < coalesce(e.version, 1)
  )
RETURN e
ORDER BY e.updated_at DESC
LIMIT $limit
"""


async def find_entities_needing_embedding(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    embedding_model: str,
    limit: int = 200,
) -> list[Entity]:
    """Anchored, active entities that need a (re)embed for `embedding_model`.

    "Need" = never embedded, embedded under a different model, or content
    advanced (`embedding_version < version`) since the last embed. Newest-first
    so an incremental run after an extraction touches the just-changed entities
    first. The producer (`app.extraction.entity_embedder`) drains this with a
    per-run cap; `limit` bounds one batch."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    result = await run_read(
        session,
        _FIND_NEEDING_EMBEDDING_CYPHER,
        user_id=user_id,
        project_id=project_id,
        embedding_model=embedding_model,
        limit=limit,
    )
    out: list[Entity] = []
    async for record in result:
        out.append(_node_to_entity(record["e"]))
    return out


# ── link_to_glossary / unlink_from_glossary ───────────────────────────


# Look up the existing entity by its glossary FK. This is the
# rename-aware path: the canonical_id is hash-derived from the
# CURRENT name, so if the name changed in glossary the id won't
# match anymore — but the glossary_entity_id link still does.
#
# D-KG-GLOSSARY-FK-GLOBAL-UNIQUE: scoped by `project_id` as well as `user_id`. The FK
# is now unique per (user, project), so a user with two knowledge projects over the
# same book has TWO nodes for the same glossary entity — one per project. Without the
# project filter this would match both and silently return an arbitrary one.
_FIND_BY_GLOSSARY_ID_CYPHER = """
MATCH (e:Entity {glossary_entity_id: $glossary_entity_id})
WHERE e.user_id = $user_id AND e.project_id = $project_id
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
    project_id: str,
    glossary_entity_id: str,
) -> Entity | None:
    """Look up an anchored entity by its glossary FK, WITHIN one project.

    The rename-aware companion to `get_entity`. After
    `link_to_glossary` updates an entity's name across canonical
    boundaries, the caller can find it again via this function
    even though `entity_canonical_id(new_name, kind)` no longer
    matches the stored id.

    `project_id` is REQUIRED (D-KG-GLOSSARY-FK-GLOBAL-UNIQUE): the FK is unique per
    (user, project), so the same glossary entity may have one node in each of the
    user's projects. Omitting the scope would return an arbitrary project's node.

    Multi-row safety: the schema enforces uniqueness on
    `(user_id, project_id, glossary_entity_id)`, so a properly-applied
    schema makes multi-row results impossible. The runtime
    safety net below catches the brief window where a misuse,
    a missing schema, or a race could produce two rows — instead
    of crashing on `result.single()`, we iterate, take the first
    row, and warn if a second row exists. Belt + suspenders.
    """
    if not glossary_entity_id:
        raise ValueError("glossary_entity_id must be a non-empty string")
    if not project_id:
        raise ValueError("project_id must be a non-empty string")
    result = await run_read(
        session,
        _FIND_BY_GLOSSARY_ID_CYPHER,
        user_id=user_id,
        project_id=project_id,
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
            "for glossary_entity_id=%r user_id=%r project_id=%r — schema constraint "
            "entity_glossary_fk_unique should have prevented this. "
            "Returning the first match; investigate the data.",
            extra_count,
            glossary_entity_id,
            user_id,
            project_id,
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


# ── reset_glossary_anchors (E3 maintenance) ───────────────────────────
#
# Glossary-tiering G4e (genre·kind·attribute epic) TRUNCATEs
# glossary_entities under the full-reset (R2), orphaning every Neo4j
# anchor: each :Entity node's `glossary_entity_id` now points at a
# glossary entity id that no longer exists, so `get_entity_by_glossary_id`
# returns a node the SSOT can't back. This maintenance op clears the
# anchor FK from all :Entity nodes (a reset, not a per-entity unlink),
# returning them to the discovered tier. anchor_score is set to 0.0 (the
# next recompute_anchor_score pass restores fractional discovered-tier
# scores) and any anchored name/kind stays in place — only the broken FK
# is cleared.
#
# Scoping: pass user_id to reset one tenant's anchors; pass user_id=None
# to reset EVERY anchor in the graph (the post-truncate full reset — only
# safe because the KG holds test data at this epic, per E3/R4).
#
# This does NOT run automatically. Invoke it deliberately after the G4e
# glossary reset, e.g. from a maintenance shell:
#
#     from app.db.neo4j_helpers import get_session
#     from app.db.neo4j_repos.entities import reset_glossary_anchors
#     async with get_session() as session:
#         n = await reset_glossary_anchors(session, user_id=None)
#         print(f"cleared {n} glossary anchors")
#
# (run_read/run_write inject $user_id for verification; the all-tenants
# path passes user_id=None and the Cypher guards with a NULL check so the
# verification wrapper still receives the parameter.)
_RESET_GLOSSARY_ANCHORS_CYPHER = """
MATCH (e:Entity)
WHERE e.glossary_entity_id IS NOT NULL
  AND ($user_id IS NULL OR e.user_id = $user_id)
SET e.glossary_entity_id = NULL,
    e.anchor_score = 0.0,
    e.updated_at = datetime()
RETURN count(e) AS cleared
"""


async def reset_glossary_anchors(
    session: CypherSession,
    *,
    user_id: str | None = None,
) -> int:
    """Clear `glossary_entity_id` from every anchored :Entity node.

    E3 maintenance for the glossary-tiering G4e full reset: glossary
    entities were truncated, so every anchor FK is dangling. This
    detaches them (returns the nodes to the discovered tier) without
    deleting any node. Returns the number of anchors cleared.

    Pass ``user_id`` to scope to one tenant; ``None`` resets all
    anchors in the graph (only safe on test data — see E3/R4).

    Idempotent: a second run finds no anchored nodes and returns 0.
    """
    result = await run_write(
        session,
        _RESET_GLOSSARY_ANCHORS_CYPHER,
        user_id=user_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["cleared"])


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
# C8: the status predicate is a derived filter over `archived_at` +
# `glossary_entity_id`, matching `Entity.status`'s precedence. When
# `$status` is NULL the legacy default holds — active (non-archived)
# entities only, canonical + discovered mixed. A non-NULL `$status`
# selects exactly one tier (and `status='archived'` is the ONLY way to
# surface archived rows, which the default still hides).
_LIST_ENTITIES_FILTER_WHERE = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND ($kind IS NULL OR e.kind = $kind)
  AND (
    CASE $status
      WHEN 'archived'   THEN e.archived_at IS NOT NULL
      WHEN 'canonical'  THEN e.archived_at IS NULL AND e.glossary_entity_id IS NOT NULL
      WHEN 'discovered' THEN e.archived_at IS NULL AND e.glossary_entity_id IS NULL
      ELSE e.archived_at IS NULL
    END
  )
  AND (
    $search IS NULL
    OR toLower(e.name) CONTAINS toLower($search)
    OR any(alias IN e.aliases WHERE toLower(alias) CONTAINS toLower($search))
  )
"""

_LIST_ENTITIES_COUNT_CYPHER = _LIST_ENTITIES_FILTER_WHERE + """
RETURN count(e) AS total
"""

# C8: sort_by is interpolated from a CLOSED allowlist (ENTITY_SORT_KEYS),
# never user text — Cypher can't parameterize an ORDER BY property, so
# the value is validated against the allowlist in the function body
# before this template is .format()-ed. mention_count + anchor_score
# both keep the (name ASC, id ASC) stable tiebreak so pagination is
# deterministic.
_LIST_ENTITIES_PAGE_CYPHER_TEMPLATE = _LIST_ENTITIES_FILTER_WHERE + """
RETURN e
ORDER BY e.{sort_key} DESC, e.name ASC, e.id ASC
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
    status: str | None = None,
    sort_by: str = "mention_count",
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

    **C8 — `status` filter + `sort_by`.**
      - `status=None` (default): active (non-archived) entities,
        canonical + discovered mixed — the legacy behaviour.
      - `status ∈ ENTITY_STATUSES`: select exactly that derived tier.
        `status='archived'` is the only way to surface archived rows.
      - `sort_by ∈ ENTITY_SORT_KEYS`: `mention_count` (default) or
        `anchor_score`. Validated against the closed allowlist before
        interpolation — a bad value raises ValueError (router 422s on
        the enum before reaching here, so this is a defence-in-depth
        guard against non-router callers and Cypher injection).
    """
    if status is not None and status not in ENTITY_STATUSES:
        raise ValueError(
            f"unsupported status {status!r}; must be one of {ENTITY_STATUSES}"
        )
    if sort_by not in ENTITY_SORT_KEYS:
        raise ValueError(
            f"unsupported sort_by {sort_by!r}; must be one of {ENTITY_SORT_KEYS}"
        )
    count_result = await run_read(
        session,
        _LIST_ENTITIES_COUNT_CYPHER,
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        search=search,
        status=status,
    )
    count_record = await count_result.single()
    total = int(count_record["total"]) if count_record else 0
    if total == 0:
        return ([], 0)
    page_cypher = _LIST_ENTITIES_PAGE_CYPHER_TEMPLATE.format(sort_key=sort_by)
    page_result = await run_read(
        session,
        page_cypher,
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        search=search,
        status=status,
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


# ── C5 (D4-03) — get_neighborhood_by_glossary_id ─────────────────────
#
# Wiki-from-KG read path. glossary-service hosts the wiki feature but
# does NOT hold the entity-to-entity relationship graph — that lives
# only here in Neo4j, keyed by `glossary_entity_id`. The wiki renderer
# in glossary-service calls the internal endpoint that wraps this, so
# it can build an article body from the entity's 1-hop neighborhood.
#
# This is a READ-ONLY path (Q2 LOCKED: enrichment/wiki never write
# Neo4j canonical content directly). It is the glossary-FK-keyed twin
# of `get_entity_with_relations`: same relation projection + cap, but
# matched by the glossary FK instead of the canonical id, because the
# wiki caller knows the glossary entity_id, not the hash-derived
# canonical_id (which drifts on rename).

# D-KG-GLOSSARY-FK-GLOBAL-UNIQUE: `project_id` is OPTIONAL here. The only caller is
# glossary-service's wiki renderer (POST /internal/knowledge/wiki-neighborhood), which
# knows a BOOK, not a knowledge project — requiring the scope would be a cross-service
# contract change for a read-only panel. When it is NULL we match the user's nodes and
# take the first in a DETERMINISTIC order (by project_id), warning if more than one
# matched. Today exactly one node carries a given FK per user, so behaviour is
# unchanged; the ordering + warning make the ambiguity explicit if a second project
# ever anchors the same entity.
_GET_NEIGHBORHOOD_BY_GLOSSARY_ID_CYPHER = """
MATCH (e:Entity {glossary_entity_id: $glossary_entity_id})
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
WITH e ORDER BY e.project_id ASC
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


async def get_neighborhood_by_glossary_id(
    session: CypherSession,
    *,
    user_id: str,
    glossary_entity_id: str,
    project_id: str | None = None,
    rel_cap: int = ENTITIES_DETAIL_REL_CAP,
) -> EntityDetail | None:
    """C5 (D4-03) — entity + 1-hop active RELATES_TO edges, keyed by the
    glossary FK rather than the canonical id.

    Returns None when no anchored entity carries the given
    `glossary_entity_id` for this user (a glossary entity that has
    never been synced into the KG, or a cross-user lookup). A None
    result is a VALID "empty neighborhood" signal for the wiki
    renderer — it produces a minimal body rather than failing.

    `project_id` is OPTIONAL (D-KG-GLOSSARY-FK-GLOBAL-UNIQUE): the FK is unique per
    (user, project), so a user with two knowledge projects over the same book has one
    node per project. The wiki caller knows a book, not a project, so when the scope
    is omitted we take the first node in a deterministic order (by `project_id`) and
    warn if more than one matched — rather than silently picking an arbitrary one.

    Relations carry `confidence` + `pending_validation`, and the
    entity carries `source_types`, so the caller can mark enriched
    (`source_type='enriched'`, pending, confidence<1.0) facts as
    visibly distinct from glossary canon (H0 LOCKED).
    """
    if not glossary_entity_id:
        raise ValueError("glossary_entity_id must be a non-empty string")
    result = await run_read(
        session,
        _GET_NEIGHBORHOOD_BY_GLOSSARY_ID_CYPHER,
        user_id=user_id,
        project_id=project_id,
        glossary_entity_id=glossary_entity_id,
        rel_cap=rel_cap,
    )
    # NOT `result.single()`: without a project scope the FK can now legitimately match
    # one node per project. Take the first (deterministically ordered) and say so.
    record = None
    extra = 0
    async for row in result:
        if record is None:
            record = row
        else:
            extra += 1
    if extra:
        logger.warning(
            "get_neighborhood_by_glossary_id: %d extra node(s) for "
            "glossary_entity_id=%r user_id=%r with no project scope — returning the "
            "lowest project_id. Pass project_id to disambiguate.",
            extra, glossary_entity_id, user_id,
        )
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


# ── K19d γ-a — update_entity_fields (PATCH backend) ──────────────────
#
# Only fields the caller passes are written — None leaves the existing
# value alone. `user_edited=true` is set unconditionally on any write
# so future merge_entity calls gate alias re-append (see
# `_MERGE_ENTITY_CYPHER`). Cross-user / missing returns None.
#
# The CASE-wrapped SET clauses are a Cypher quirk: Neo4j doesn't have
# per-property conditional updates out of the box, so we use
# `CASE WHEN $foo IS NULL THEN e.foo ELSE $foo END` per field. The
# parameter list still names every field; unprovided ones are passed
# as NULL from Python so the CASE short-circuits to e.field.
#
# `canonical_name` is derived from the new `name` when name changes —
# otherwise the canonical_id hash and the actual node name would drift.
# The canonical_id itself is immutable (merge_entity's deterministic
# hash depends on it) so renaming an entity doesn't re-key it; only
# the display property + canonical_name change.

# C9 (D-K19d-γa-01): atomic optimistic-concurrency via FOREACH. The
# Cypher MATCHes the row; FOREACH conditionally mutates only when the
# caller's expected_version matches `coalesce(e.version, 1)`. Returns
# the node + an `applied` flag:
#   - applied=True  → post-write state; helper returns Entity
#   - applied=False → pre-check state (unchanged); helper raises
#                     VersionMismatchError carrying the current Entity
#   - MATCH produces no row → helper returns None (router 404s)
# Single round-trip, atomic under `run_write`'s transaction.
_UPDATE_ENTITY_FIELDS_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
// Phase B: capture the pre-edit snapshot in the SAME query (design §6.3 —
// same-Cypher, NOT read-before-write, so before/after are TOCTOU-consistent).
// The WITH materialises `before` eagerly, before the FOREACH SET mutates e.
WITH e, coalesce(e.version, 1) AS current_version,
     {name: e.name, kind: e.kind, aliases: coalesce(e.aliases, [])} AS before
FOREACH (_ IN CASE WHEN current_version = $expected_version THEN [1] ELSE [] END |
  SET
    e.name = CASE WHEN $name IS NULL THEN e.name ELSE $name END,
    e.canonical_name = CASE
      WHEN $canonical_name IS NULL THEN e.canonical_name
      ELSE $canonical_name
    END,
    e.kind = CASE WHEN $kind IS NULL THEN e.kind ELSE $kind END,
    e.aliases = CASE
      WHEN $aliases IS NULL THEN e.aliases
      ELSE $aliases
    END,
    e.user_edited = true,
    e.version = current_version + 1,
    e.updated_at = datetime()
)
RETURN e, current_version = $expected_version AS applied, before
"""


async def update_entity_fields(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    name: str | None,
    kind: str | None,
    aliases: list[str] | None,
    expected_version: int,
) -> tuple[Entity | None, dict | None]:
    """K19d.5 + C9 — patch an entity's display fields with optimistic
    concurrency.

    Phase B: returns ``(entity, before)`` where ``before`` is the pre-edit
    ``{name, kind, aliases}`` snapshot captured in the SAME Cypher (design §6.3)
    — used by the router to emit a ``knowledge.entity_corrected`` event.
    ``before`` is ``None`` when no row matched. On a version mismatch the
    function still raises ``VersionMismatchError`` (before is irrelevant — no
    edit happened).

    Sets `user_edited=true` + bumps `version` on any successful write.
    `expected_version` must match the row's current version (coalesced
    to 0 for pre-C9 nodes lacking the property). Mismatch raises
    ``VersionMismatchError`` carrying the current Entity so the router
    can emit a 412 with the refreshed baseline body.

    Returns the updated Entity on success, or None when no row matches
    (cross-user / missing id — router collapses to 404).

    `aliases` replaces the full list when provided (not append — the
    whole point of the user_edited lock is that the user's list is
    authoritative). Pass the empty list to clear; pass None to leave
    the existing aliases alone.

    At least one of name / kind / aliases must be non-None; the
    router-level Pydantic validator enforces that contract.

    Derived value: when `name` changes, `canonical_name` is updated
    to the new canonicalization. The entity's immutable canonical_id
    hash does NOT change — future extractions with the old name will
    still dedupe onto this node via the hash, so the rename has no
    downstream consequence beyond display.
    """
    canonical_name = (
        canonicalize_entity_name(name) if name is not None else None
    )
    result = await run_write(
        session,
        _UPDATE_ENTITY_FIELDS_CYPHER,
        user_id=user_id,
        id=entity_id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        aliases=aliases,
        expected_version=expected_version,
    )
    record = await result.single()
    if record is None:
        return None, None
    entity = _node_to_entity(record["e"])
    if not record["applied"]:
        raise VersionMismatchError(entity)
    before_raw = record["before"]
    before = dict(before_raw) if before_raw is not None else None
    return entity, before


# C9 (D-K19d-γa-02) — unlock user_edited so extractions can contribute
# aliases again. Idempotent: a second unlock on an already-unlocked
# entity succeeds (still bumps version — cheap and keeps the "any
# user-facing write bumps" invariant honest). No If-Match — matches
# the /archive pattern; a one-way flag flip has no concurrency hazard
# worth a baseline-refresh dance.
_UNLOCK_ENTITY_CYPHER = """
MATCH (e:Entity {id: $id})
WHERE e.user_id = $user_id
SET
  e.user_edited = false,
  e.version = coalesce(e.version, 1) + 1,
  e.updated_at = datetime()
RETURN e
"""


async def unlock_entity_user_edited(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
) -> Entity | None:
    """C9 — clear the user_edited lock on an entity. Returns the
    updated Entity or None when no row matches (router 404s)."""
    result = await run_write(
        session,
        _UNLOCK_ENTITY_CYPHER,
        user_id=user_id,
        id=entity_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_entity(record["e"])


# ── K19d γ-b — merge_entities ────────────────────────────────────────
#
# Combines two entities owned by the same user into one. Target
# survives; source is DETACH DELETEd. Both RELATES_TO and
# EVIDENCED_BY edge sets are re-homed onto the target BEFORE
# source is deleted, so provenance is preserved.
#
# `:RELATES_TO` edges carry a deterministic `id` = sha256 of
# `(user_id, subject_id, predicate, object_id)`. Since subject
# (or object) changes from source→target, the id must change too —
# we can't rewire in-place. Approach: read source's edges in
# Python, compute new ids, batch-MERGE onto target via UNWIND.
# Existing target edges with the new id get ON MATCH treatment
# (max confidence + source_event_ids union).
#
# `:EVIDENCED_BY` edges key on `{job_id}` per K11.8 — MERGE on
# that dedupes cleanly when target shares an ExtractionSource
# with source.
#
# APOC is available in deployed Neo4j (NEO4J_PLUGINS=['apoc'])
# but knowledge-service deliberately avoids it (events.py L193).
# Keeping that discipline: all hashing in Python, Cypher APOC-free.


class MergeEntitiesError(Exception):
    """Raised by `merge_entities` on validation failure the router
    must distinguish. `error_code` is the stable string mapped to
    HTTP status + structured body."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


_MERGE_LOAD_ENTITIES_CYPHER = """
OPTIONAL MATCH (s:Entity {id: $source_id})
WHERE s.user_id = $user_id
OPTIONAL MATCH (t:Entity {id: $target_id})
WHERE t.user_id = $user_id
RETURN s, t
"""


_MERGE_COLLECT_EDGES_CYPHER = """
MATCH (s:Entity {id: $source_id})
WHERE s.user_id = $user_id
CALL {
  WITH s
  OPTIONAL MATCH (s)-[r:RELATES_TO]->(o:Entity)
  WHERE r.user_id = $user_id AND o.user_id = $user_id
  RETURN collect({
    direction: 'out',
    predicate: r.predicate,
    other_id: o.id,
    confidence: r.confidence,
    source_event_ids: coalesce(r.source_event_ids, []),
    source_chapter: r.source_chapter,
    valid_from: r.valid_from,
    valid_until: r.valid_until,
    pending_validation: r.pending_validation
  }) AS out_edges
}
CALL {
  WITH s
  OPTIONAL MATCH (sub:Entity)-[r:RELATES_TO]->(s)
  WHERE r.user_id = $user_id AND sub.user_id = $user_id
    AND sub <> s
  RETURN collect({
    direction: 'in',
    predicate: r.predicate,
    other_id: sub.id,
    confidence: r.confidence,
    source_event_ids: coalesce(r.source_event_ids, []),
    source_chapter: r.source_chapter,
    valid_from: r.valid_from,
    valid_until: r.valid_until,
    pending_validation: r.pending_validation
  }) AS in_edges
}
RETURN out_edges, in_edges
"""


_MERGE_REWIRE_RELATES_TO_CYPHER = """
UNWIND $edges AS edge
MATCH (subj:Entity {id: edge.subject_id})
WHERE subj.user_id = $user_id
MATCH (obj:Entity {id: edge.object_id})
WHERE obj.user_id = $user_id
MERGE (subj)-[r:RELATES_TO {id: edge.new_id}]->(obj)
ON CREATE SET
  r.user_id = $user_id,
  r.subject_id = edge.subject_id,
  r.object_id = edge.object_id,
  r.predicate = edge.predicate,
  r.confidence = edge.confidence,
  r.source_event_ids = edge.source_event_ids,
  r.source_chapter = edge.source_chapter,
  r.valid_from = edge.valid_from,
  r.valid_until = edge.valid_until,
  r.pending_validation = edge.pending_validation,
  r.created_at = datetime(),
  r.updated_at = datetime()
ON MATCH SET
  r.confidence = CASE
    WHEN edge.confidence > r.confidence THEN edge.confidence
    ELSE r.confidence
  END,
  r.source_event_ids = [
    x IN coalesce(r.source_event_ids, []) + edge.source_event_ids
    WHERE x IS NOT NULL
    | x
  ],
  // C1 / D-K19d-γb-01: AND-combine so a validated edge (false)
  // absorbs a quarantined duplicate (true). NULL default = false
  // to match the codebase-wide convention (relations.py filter
  // helpers all use `coalesce(r.pending_validation, false)`).
  // Consistent NULL semantics across read + merge paths.
  r.pending_validation = coalesce(r.pending_validation, false)
    AND coalesce(edge.pending_validation, false),
  // Earliest non-null valid_from wins; NULL loses to concrete.
  r.valid_from = CASE
    WHEN r.valid_from IS NULL THEN edge.valid_from
    WHEN edge.valid_from IS NULL THEN r.valid_from
    WHEN edge.valid_from < r.valid_from THEN edge.valid_from
    ELSE r.valid_from
  END,
  // valid_until IS NULL means "still active" (relations.py:13) —
  // so NULL wins here. Only when BOTH are concrete do we take MAX.
  r.valid_until = CASE
    WHEN r.valid_until IS NULL OR edge.valid_until IS NULL THEN NULL
    WHEN edge.valid_until > r.valid_until THEN edge.valid_until
    ELSE r.valid_until
  END,
  // Concat distinct source_chapter values so merge history survives.
  // At hobby scale the unbounded string is fine; if it ever grows,
  // swap to a list property.
  r.source_chapter = CASE
    WHEN r.source_chapter IS NULL THEN edge.source_chapter
    WHEN edge.source_chapter IS NULL THEN r.source_chapter
    WHEN r.source_chapter = edge.source_chapter THEN r.source_chapter
    ELSE r.source_chapter + ',' + edge.source_chapter
  END,
  r.updated_at = datetime()
RETURN count(r) AS rewired
"""


_MERGE_REWIRE_EVIDENCED_BY_CYPHER = """
MATCH (s:Entity {id: $source_id})-[e:EVIDENCED_BY]->(ext:ExtractionSource)
WHERE s.user_id = $user_id
WITH e, ext, properties(e) AS props
MATCH (t:Entity {id: $target_id})
WHERE t.user_id = $user_id
MERGE (t)-[e2:EVIDENCED_BY {job_id: props.job_id}]->(ext)
ON CREATE SET e2 = props
RETURN count(e2) AS rewired
"""


_MERGE_UPDATE_TARGET_CYPHER = """
MATCH (s:Entity {id: $source_id})
WHERE s.user_id = $user_id
MATCH (t:Entity {id: $target_id})
WHERE t.user_id = $user_id
// Capture source's glossary anchor before nulling it — we need the
// value to decide whether to inherit it onto target. Clearing first
// avoids a transient state where both source and target carry the
// same glossary_entity_id, which would trip the UNIQUE constraint
// on :Entity(glossary_entity_id).
WITH s, t, s.glossary_entity_id AS src_anchor
SET s.glossary_entity_id = NULL
WITH s, t, src_anchor
SET
  t.aliases = t.aliases + s.aliases + [s.name],
  t.source_types = coalesce(t.source_types, []) + coalesce(s.source_types, []),
  t.mention_count = coalesce(t.mention_count, 0)
                    + coalesce(s.mention_count, 0),
  t.evidence_count = coalesce(t.evidence_count, 0)
                     + coalesce(s.evidence_count, 0),
  t.confidence = CASE
    WHEN coalesce(s.confidence, 0.0) > coalesce(t.confidence, 0.0)
      THEN s.confidence
    ELSE t.confidence
  END,
  t.glossary_entity_id = CASE
    WHEN t.glossary_entity_id IS NULL THEN src_anchor
    ELSE t.glossary_entity_id
  END,
  t.user_edited = true,
  t.version = coalesce(t.version, 1) + 1,
  t.updated_at = datetime()
RETURN t
"""


# T2.1 — re-point the source's `(:Fact)-[:ABOUT]->` edges onto target before the
# DETACH DELETE, else facts about a merged-away entity orphan (vanish from the live
# entity's codex list). MERGE is idempotent — a fact already ABOUT target gains no
# dup; the stale source edge is removed by the DETACH DELETE in step 7.
_MERGE_REWIRE_ABOUT_CYPHER = """
MATCH (f:Fact)-[:ABOUT]->(s:Entity {id: $source_id})
WHERE f.user_id = $user_id
MATCH (t:Entity {id: $target_id})
WHERE t.user_id = $user_id
MERGE (f)-[:ABOUT]->(t)
RETURN count(*) AS rewired
"""


_MERGE_DELETE_SOURCE_CYPHER = """
MATCH (s:Entity {id: $source_id})
WHERE s.user_id = $user_id
DETACH DELETE s
"""


_MERGE_DEDUPE_TARGET_CYPHER = """
MATCH (t:Entity {id: $target_id})
WHERE t.user_id = $user_id
SET t.aliases = $aliases,
    t.source_types = $source_types,
    t.updated_at = datetime()
RETURN t
"""


def _dedupe_preserving_order(items: list[Any]) -> list[Any]:
    """Python dedupe that keeps first-occurrence order. Cypher's
    list-comprehension dedupe is awkward; doing it in Python
    after the merge writes target is simpler and deterministic."""
    seen: set[Any] = set()
    out: list[Any] = []
    for item in items:
        if item is None:
            continue
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


async def merge_entities(
    session: CypherSession,
    *,
    user_id: str,
    source_id: str,
    target_id: str,
) -> Entity:
    """K19d.6 — merge source entity into target, deleting source.

    Raises `MergeEntitiesError` with one of the stable codes:
      - ``same_entity``       — source_id == target_id
      - ``entity_not_found``  — either doesn't exist / cross-user
      - ``entity_archived``   — either has archived_at set
      - ``glossary_conflict`` — both glossary anchors set + distinct

    Returns the updated target Entity on success. Target's
    `user_edited` is set to true so future re-extractions don't
    silently re-append variants the user considered duplicates.

    Contract: `session` must be a fresh AsyncSession with no open
    transaction. C1 wraps steps 4–7 in an explicit transaction and
    Neo4j async sessions do not support nested transactions — a
    caller that wraps `merge_entities` in its own tx would fail at
    the inner `session.begin_transaction()` call.
    """
    if source_id == target_id:
        raise MergeEntitiesError(
            "same_entity",
            "source and target must be distinct entities",
        )

    # 1. Load + validate.
    load_result = await run_read(
        session,
        _MERGE_LOAD_ENTITIES_CYPHER,
        user_id=user_id,
        source_id=source_id,
        target_id=target_id,
    )
    load_row = await load_result.single()
    if load_row is None:
        raise MergeEntitiesError("entity_not_found", "entity not found")
    source_node = load_row["s"]
    target_node = load_row["t"]
    if source_node is None or target_node is None:
        raise MergeEntitiesError("entity_not_found", "entity not found")

    source = _node_to_entity(source_node)
    target = _node_to_entity(target_node)

    if source.archived_at is not None or target.archived_at is not None:
        raise MergeEntitiesError(
            "entity_archived",
            "cannot merge archived entities",
        )

    if (
        source.glossary_entity_id is not None
        and target.glossary_entity_id is not None
        and source.glossary_entity_id != target.glossary_entity_id
    ):
        raise MergeEntitiesError(
            "glossary_conflict",
            "source and target are anchored to different glossary entries",
        )

    # 2. Collect source's edges.
    edges_result = await run_read(
        session,
        _MERGE_COLLECT_EDGES_CYPHER,
        user_id=user_id,
        source_id=source_id,
    )
    edges_row = await edges_result.single()
    out_edges = edges_row["out_edges"] if edges_row else []
    in_edges = edges_row["in_edges"] if edges_row else []

    # 3. Compute new relation_ids pinned to target, build UNWIND payload.
    #    Edges to skip:
    #      - `other_id == target_id` — would become self-loop on
    #        target after rewire.
    #      - `other_id == source_id` — review-impl H1: source has
    #        a self-relation (rare but extractor can produce one).
    #        If we rewired it, the new edge would reference source
    #        as object, and the step 7 DETACH DELETE would destroy
    #        the freshly-created edge, silently losing the self-
    #        relation. In practice self-relations on source are so
    #        rare and semantically weird that dropping them is the
    #        right call — we don't know which endpoint should win.
    rewire_edges: list[dict[str, Any]] = []
    for edge in out_edges:
        other_id = edge.get("other_id")
        if other_id is None or other_id == target_id or other_id == source_id:
            continue
        predicate = edge.get("predicate")
        if not predicate:
            continue
        new_id = relation_id(
            user_id=user_id,
            subject_id=target_id,
            predicate=predicate,
            object_id=other_id,
        )
        rewire_edges.append({
            "new_id": new_id,
            "subject_id": target_id,
            "object_id": other_id,
            "predicate": predicate,
            "confidence": float(edge.get("confidence") or 0.0),
            "source_event_ids": list(edge.get("source_event_ids") or []),
            "source_chapter": edge.get("source_chapter"),
            "valid_from": edge.get("valid_from"),
            "valid_until": edge.get("valid_until"),
            "pending_validation": bool(edge.get("pending_validation") or False),
        })
    for edge in in_edges:
        other_id = edge.get("other_id")
        # in_edges Cypher already filters `sub <> s` so source
        # self-relations never surface here, but skip defensively
        # in case that filter is ever relaxed.
        if other_id is None or other_id == target_id or other_id == source_id:
            continue
        predicate = edge.get("predicate")
        if not predicate:
            continue
        new_id = relation_id(
            user_id=user_id,
            subject_id=other_id,
            predicate=predicate,
            object_id=target_id,
        )
        rewire_edges.append({
            "new_id": new_id,
            "subject_id": other_id,
            "object_id": target_id,
            "predicate": predicate,
            "confidence": float(edge.get("confidence") or 0.0),
            "source_event_ids": list(edge.get("source_event_ids") or []),
            "source_chapter": edge.get("source_chapter"),
            "valid_from": edge.get("valid_from"),
            "valid_until": edge.get("valid_until"),
            "pending_validation": bool(edge.get("pending_validation") or False),
        })

    # C1 / D-K19d-γb-02: steps 4–7 run inside a single explicit
    # transaction so a Neo4j crash or network drop after the
    # glossary pre-clear in step 6 cannot leave source orphaned
    # with glossary_entity_id=NULL. `AsyncTransaction` satisfies
    # the `CypherSession` Protocol structurally (it exposes the
    # same async `run(cypher, **params)` method), so the K11.4
    # helpers work unchanged on it.
    async with await session.begin_transaction() as tx:
        # 4. Batch-MERGE rewired RELATES_TO edges onto target.
        if rewire_edges:
            await run_write(
                tx,
                _MERGE_REWIRE_RELATES_TO_CYPHER,
                user_id=user_id,
                edges=rewire_edges,
            )

        # 5. Rewire EVIDENCED_BY edges.
        await run_write(
            tx,
            _MERGE_REWIRE_EVIDENCED_BY_CYPHER,
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
        )

        # 5b. T2.1 — re-point (:Fact)-[:ABOUT]-> edges onto target (before delete).
        await run_write(
            tx,
            _MERGE_REWIRE_ABOUT_CYPHER,
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
        )

        # 6. Update target metadata — aliases / source_types concat
        #    happens here; dedupe happens below after refetch.
        update_result = await run_write(
            tx,
            _MERGE_UPDATE_TARGET_CYPHER,
            user_id=user_id,
            source_id=source_id,
            target_id=target_id,
        )
        update_row = await update_result.single()
        if update_row is None:
            raise MergeEntitiesError(
                "entity_not_found",
                "entity disappeared during merge",
            )

        # 7. DETACH DELETE source.
        await run_write(
            tx,
            _MERGE_DELETE_SOURCE_CYPHER,
            user_id=user_id,
            source_id=source_id,
        )

    # 8. Dedupe aliases + source_types in Python; write back iff
    #    dedupe shrank either list.
    post = await get_entity(session, user_id=user_id, canonical_id=target_id)
    if post is None:
        raise MergeEntitiesError(
            "entity_not_found",
            "target missing after merge",
        )
    deduped_aliases = _dedupe_preserving_order(post.aliases)
    deduped_source_types = _dedupe_preserving_order(post.source_types)
    if (
        deduped_aliases != post.aliases
        or deduped_source_types != post.source_types
    ):
        await run_write(
            session,
            _MERGE_DEDUPE_TARGET_CYPHER,
            user_id=user_id,
            target_id=target_id,
            aliases=deduped_aliases,
            source_types=deduped_source_types,
        )
        post = await get_entity(session, user_id=user_id, canonical_id=target_id)
        if post is None:
            raise MergeEntitiesError(
                "entity_not_found",
                "target missing after dedupe",
            )
    return post
