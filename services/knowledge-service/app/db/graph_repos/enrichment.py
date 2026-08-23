"""Lore-enrichment write-back, promote and retract (plan T17).

Moved out of `app/routers/internal_enrichment.py`. Three operations, five statements, and
the reasoning that makes them safe travels with them because it is not obvious from the
Cypher alone:

**The anchor is keyed on the CANONICAL id, not the glossary id.** `Entity.id` is a hash of
(user, project, canonical_name, kind), matching the glossary→KG sync. Keying on the
canonical id makes write-back idempotent across glossary churn — re-promote, delete and
recreate of the same name, or a rename all resolve to ONE node instead of tripping the
UNIQUE on `:Entity(id)`.

**A stale glossary anchor is freed BEFORE the claim.** A renamed or deleted-recreated
entity can leave another node still holding this `glossary_entity_id`; setting it below
would trip the UNIQUE. Same null-before-claim discipline the canonical sync uses.

**ON CREATE and ON MATCH are strictly distinct (H0 / FIX-2).** On MATCH a pre-existing
canon anchor stays EXACTLY as it is — enrichment never makes a canon node look more or less
canon; only `updated_at` bumps and a missing glossary anchor is back-filled. On CREATE the
node is born MARKED as enrichment (`origin='enrichment'`, `pending_validation=true`,
`confidence < 1.0`) so it is never indistinguishable from canon. A genuine glossary sync
clears those markers on match, when the owner actually authors or promotes it.

**Promote RETAINS the origin marker.** It flips `pending_validation` and stamps the actor,
but `origin` / `promoted_from_proposal_id` / `original_technique` stay: how a fact entered
the graph remains auditable after it becomes canon.

**Retract is SOFT.** It sets `valid_until` so the rows leave the active graph (the
neighbourhood query filters `valid_until IS NULL`) without a hard delete — reversible by
clearing it, and it can never remove canon because it filters on this proposal's own
`origin` + `promoted_from_proposal_id`.
"""

from __future__ import annotations

from app.db.graph_repos.entities import GLOBAL_PROJECT_SENTINEL

from loreweave_extraction.canonical import entity_canonical_id

from app.db.cypher_dialect import render
from app.db.neo4j_helpers import engine_of, CypherSession

__all__ = [
    "promote_enriched_facts",
    "retract_enriched_facts",
    "upsert_enriched_anchor",
    "upsert_enriched_fact",
]


# T35 — RESOLVE the anchor before touching anything, the same safety property
# `merge_entity` uses. The derived id is a hash of (name, kind); a glossary rename updates
# the node in place and leaves `e.id` alone, so after a rename the recomputed hash matches
# NOTHING and the MERGE below used to mint a second node — and the free-stale statement,
# which runs first, stripped the glossary anchor off the author's real character to give it
# to that stub.
#
# THE ORDER OF THE coalesce IS THE SAFETY PROPERTY. A node already sitting at the caller's
# id wins, so this is a strict no-op for every write that works today; the anchor holder is
# consulted only when nothing is at that id — i.e. exactly the rename/re-kind case. Reversing
# the two would hijack a deliberate re-anchor: `enriched-promote` moving a glossary id to a
# different entity passes that entity's real id, and it must be honoured.
_RESOLVE_ANCHOR_CYPHER = """
OPTIONAL MATCH (byId:Entity {id: $canon_id, user_id: $user_id})
OPTIONAL MATCH (byAnchor:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
RETURN coalesce(byId.id, byAnchor.id, $canon_id) AS eid
"""


_FREE_STALE_GLOSSARY_ANCHOR_CYPHER = """
MATCH (stale:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
WHERE stale.id <> $canon_id
SET stale.glossary_entity_id = NULL, stale.updated_at = {NOW}
"""

_UPSERT_ANCHOR_CYPHER = """
// §10.1/§10.2 — engine-neutral. `coalesce` for every create-only field; `updated_at` was in
// BOTH branches so it stays unconditional; `glossary_entity_id` was ALREADY a coalesce on the
// MATCH arm and the create arm set it outright, which is the same thing on an absent node.
//
// ⚠️ `user_id` moved into the MERGE KEY. Unlike `provenance` and `entity_status` this query
// had no trailing `WITH … WHERE`, so no tenancy filter is being replaced — the key is what
// there is. `$canon_id` is the derived canonical entity id, which already scopes to the user.
MERGE (e:Entity {id: $canon_id, user_id: $user_id})
SET e.glossary_entity_id       = coalesce(e.glossary_entity_id, $glossary_entity_id),
    e.name                     = coalesce(e.name, $name),
    e.canonical_name           = coalesce(e.canonical_name, $canon_name),
    e.kind                     = coalesce(e.kind, $kind),
    e.project_id               = coalesce(e.project_id, $project_id),
    e.confidence               = coalesce(e.confidence, $anchor_confidence),
    e.source_type              = coalesce(e.source_type, $anchor_source_type),
    e.source_types             = coalesce(e.source_types, [$anchor_source_type]),
    e.origin                   = coalesce(e.origin, $origin),
    e.pending_validation       = coalesce(e.pending_validation, true),
    e.promoted_from_proposal_id = coalesce(e.promoted_from_proposal_id, $proposal_id),
    e.original_technique       = coalesce(e.original_technique, $technique),
    e.created_at               = coalesce(e.created_at, {NOW}),
    e.updated_at               = {NOW}
"""

_UPSERT_ENRICHED_FACT_CYPHER = """
MATCH (e:Entity {id: $canon_id})
// §10.1/§10.2 — engine-neutral, and note this one is NOT all-coalesce. Its ON MATCH branch
// deliberately OVERWRITES content/confidence/pending_validation/source_type(s)/origin/
// valid_until: an enrichment re-run REPLACES its own output, which is last-write-wins by
// design. Those stay unconditional. Only the fields the MATCH arm never touched — the
// identity, the dimension, the proposal provenance, created_at — take `coalesce`.
//
// ⚠️ Reading the two branches as "create sets everything, match accumulates" and coalescing
// the lot would have frozen every enriched fact at its first value — a re-run would report
// success and change nothing.
MERGE (f:Fact {id: $node_id, user_id: $user_id})
SET f.project_id                = coalesce(f.project_id, $project_id),
    f.type                      = coalesce(f.type, 'enrichment'),
    f.dimension                 = coalesce(f.dimension, $dimension),
    f.promoted_from_proposal_id = coalesce(f.promoted_from_proposal_id, $proposal_id),
    f.original_technique        = coalesce(f.original_technique, $technique),
    f.created_at                = coalesce(f.created_at, {NOW}),
    f.content                   = $content,
    f.confidence                = $confidence,
    f.pending_validation        = true,
    f.source_type               = $source_type,
    f.source_types              = [$source_type],
    f.origin                    = $origin,
    f.valid_until               = NULL,
    f.updated_at                = {NOW}
MERGE (e)-[r:RELATES_TO {id: $edge_id}]->(f)
SET r.user_id = $user_id,
    r.predicate = '补充',
    r.subject_id = e.id,
    r.object_id = $node_id,
    r.confidence = $confidence,
    r.pending_validation = true,
    r.source_type = $source_type,
    r.origin = $origin,
    r.promoted_from_proposal_id = $proposal_id,
    r.original_technique = $technique,
    r.valid_until = NULL,
    r.updated_at = {NOW}
"""

_PROMOTE_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND f.origin = $origin
  AND f.promoted_from_proposal_id = $proposal_id
SET f.source_type = 'glossary',
    f.source_types = ['glossary'],
    f.confidence = 1.0,
    f.pending_validation = false,
    f.promoted_by = $promoted_by,
    f.promoted_at = $promoted_at,
    f.updated_at = {NOW}
WITH count(f) AS nfacts
MATCH ()-[r:RELATES_TO]->()
WHERE r.user_id = $user_id
  AND r.origin = $origin
  AND r.promoted_from_proposal_id = $proposal_id
SET r.source_type = 'glossary',
    r.confidence = 1.0,
    r.pending_validation = false,
    r.promoted_by = $promoted_by,
    r.promoted_at = $promoted_at,
    r.updated_at = {NOW}
RETURN nfacts AS affected
"""

_RETRACT_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND f.origin = $origin
  AND f.promoted_from_proposal_id = $proposal_id
SET f.valid_until = {NOW}, f.updated_at = {NOW}
WITH count(f) AS nfacts
MATCH ()-[r:RELATES_TO]->()
WHERE r.user_id = $user_id
  AND r.origin = $origin
  AND r.promoted_from_proposal_id = $proposal_id
SET r.valid_until = {NOW}, r.updated_at = {NOW}
RETURN nfacts AS affected
"""


async def upsert_enriched_anchor(
    session: CypherSession,
    *,
    user_id: str,
    glossary_entity_id: str,
    name: str,
    canon_name: str,
    kind: str,
    project_id: str,
    anchor_confidence: float,
    anchor_source_type: str,
    origin: str,
    proposal_id: str,
    technique: str,
) -> str:
    """Ensure the entity anchor exists so the enriched edge has an endpoint.

    **Returns the id the anchor actually resolved to**, which is not always `canon_id`: after
    a glossary rename the real node still carries its pre-rename id (T35). The caller must
    attach its facts to THIS id — using the recomputed hash would hang them off a node the
    anchor no longer lives on.

    Three statements, in this order and not another: resolve, free any stale claim on the
    glossary id, then MERGE. Freeing before the MERGE is required because
    `:Entity(glossary_entity_id)` is UNIQUE; resolving before the free is what stops the
    "stale" claim being the author's own renamed character.
    """
    # T35 — DERIVED HERE, not by the caller. Where to mint when nothing exists yet is a
    # storage detail of this layer; a router that computes it has to know that `Entity.id`
    # is `hash(name, kind)`, which is the coupling T35 exists to remove. The caller now
    # passes what it actually knows — the glossary anchor and the entity's properties.
    canon_id = entity_canonical_id(
        user_id,
        None if project_id == GLOBAL_PROJECT_SENTINEL else project_id,
        name, kind)
    res = await session.run(
        _RESOLVE_ANCHOR_CYPHER,
        user_id=user_id, glossary_entity_id=glossary_entity_id, canon_id=canon_id,
    )
    rec = await res.single()
    eid = rec["eid"] if rec else canon_id
    await session.run(
        render(_FREE_STALE_GLOSSARY_ANCHOR_CYPHER, engine_of(session)),
        user_id=user_id, glossary_entity_id=glossary_entity_id, canon_id=eid,
    )
    await session.run(
        render(_UPSERT_ANCHOR_CYPHER, engine_of(session)),
        user_id=user_id, glossary_entity_id=glossary_entity_id, canon_id=eid,
        name=name, canon_name=canon_name, kind=kind, project_id=project_id,
        anchor_confidence=anchor_confidence, anchor_source_type=anchor_source_type,
        origin=origin, proposal_id=proposal_id, technique=technique,
    )
    return eid


async def upsert_enriched_fact(
    session: CypherSession,
    *,
    user_id: str,
    canon_id: str,
    node_id: str,
    edge_id: str,
    project_id: str,
    dimension: str,
    content: str,
    confidence: float,
    source_type: str,
    origin: str,
    proposal_id: str,
    technique: str,
) -> None:
    """One enriched fact plus the edge attaching it to the anchor. `confidence` is capped
    below 1.0 by the caller (H0) — a write-back is never canon."""
    await session.run(
        render(_UPSERT_ENRICHED_FACT_CYPHER, engine_of(session)),
        user_id=user_id, canon_id=canon_id, node_id=node_id, edge_id=edge_id,
        project_id=project_id, dimension=dimension, content=content,
        confidence=confidence, source_type=source_type, origin=origin,
        proposal_id=proposal_id, technique=technique,
    )


async def promote_enriched_facts(
    session: CypherSession,
    *,
    user_id: str,
    origin: str,
    proposal_id: str,
    promoted_by: str,
    promoted_at,
) -> int:
    """Promote one proposal's enriched facts to canon. Returns the fact count."""
    result = await session.run(
        render(_PROMOTE_CYPHER, engine_of(session)),
        user_id=user_id, origin=origin, proposal_id=proposal_id,
        promoted_by=promoted_by, promoted_at=promoted_at,
    )
    record = await result.single()
    return int(record["affected"]) if record else 0


async def retract_enriched_facts(
    session: CypherSession, *, user_id: str, origin: str, proposal_id: str,
) -> int:
    """Soft-retract one proposal's enriched facts. Returns the fact count."""
    result = await session.run(
        render(_RETRACT_CYPHER, engine_of(session)),
        user_id=user_id, origin=origin, proposal_id=proposal_id,
    )
    record = await result.single()
    return int(record["affected"]) if record else 0
