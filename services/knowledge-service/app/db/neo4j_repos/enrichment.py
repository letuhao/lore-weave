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

from app.db.neo4j_helpers import CypherSession

__all__ = [
    "promote_enriched_facts",
    "retract_enriched_facts",
    "upsert_enriched_anchor",
    "upsert_enriched_fact",
]


_FREE_STALE_GLOSSARY_ANCHOR_CYPHER = """
MATCH (stale:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
WHERE stale.id <> $canon_id
SET stale.glossary_entity_id = NULL, stale.updated_at = datetime()
"""

_UPSERT_ANCHOR_CYPHER = """
MERGE (e:Entity {id: $canon_id})
ON CREATE SET
  e.user_id = $user_id,
  e.glossary_entity_id = $glossary_entity_id,
  e.name = $name,
  e.canonical_name = $canon_name,
  e.kind = $kind,
  e.project_id = $project_id,
  e.confidence = $anchor_confidence,
  e.source_type = $anchor_source_type,
  e.source_types = [$anchor_source_type],
  e.origin = $origin,
  e.pending_validation = true,
  e.promoted_from_proposal_id = $proposal_id,
  e.original_technique = $technique,
  e.created_at = datetime(),
  e.updated_at = datetime()
ON MATCH SET
  e.glossary_entity_id = coalesce(e.glossary_entity_id, $glossary_entity_id),
  e.updated_at = datetime()
"""

_UPSERT_ENRICHED_FACT_CYPHER = """
MATCH (e:Entity {id: $canon_id})
MERGE (f:Fact {id: $node_id})
ON CREATE SET
  f.user_id = $user_id,
  f.project_id = $project_id,
  f.type = 'enrichment',
  f.dimension = $dimension,
  f.content = $content,
  f.confidence = $confidence,
  f.pending_validation = true,
  f.source_type = $source_type,
  f.source_types = [$source_type],
  f.origin = $origin,
  f.promoted_from_proposal_id = $proposal_id,
  f.original_technique = $technique,
  f.valid_until = NULL,
  f.created_at = datetime(),
  f.updated_at = datetime()
ON MATCH SET
  f.content = $content,
  f.confidence = $confidence,
  f.pending_validation = true,
  f.source_type = $source_type,
  f.source_types = [$source_type],
  f.origin = $origin,
  f.valid_until = NULL,
  f.updated_at = datetime()
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
    r.updated_at = datetime()
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
    f.updated_at = datetime()
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
    r.updated_at = datetime()
RETURN nfacts AS affected
"""

_RETRACT_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND f.origin = $origin
  AND f.promoted_from_proposal_id = $proposal_id
SET f.valid_until = datetime(), f.updated_at = datetime()
WITH count(f) AS nfacts
MATCH ()-[r:RELATES_TO]->()
WHERE r.user_id = $user_id
  AND r.origin = $origin
  AND r.promoted_from_proposal_id = $proposal_id
SET r.valid_until = datetime(), r.updated_at = datetime()
RETURN nfacts AS affected
"""


async def upsert_enriched_anchor(
    session: CypherSession,
    *,
    user_id: str,
    glossary_entity_id: str,
    canon_id: str,
    name: str,
    canon_name: str,
    kind: str,
    project_id: str,
    anchor_confidence: float,
    anchor_source_type: str,
    origin: str,
    proposal_id: str,
    technique: str,
) -> None:
    """Ensure the entity anchor exists so the enriched edge has an endpoint.

    Two statements, in this order and not the other: free any stale claim on the glossary
    id FIRST, then MERGE. Reversing them trips the UNIQUE on `:Entity(glossary_entity_id)`.
    """
    await session.run(
        _FREE_STALE_GLOSSARY_ANCHOR_CYPHER,
        user_id=user_id, glossary_entity_id=glossary_entity_id, canon_id=canon_id,
    )
    await session.run(
        _UPSERT_ANCHOR_CYPHER,
        user_id=user_id, glossary_entity_id=glossary_entity_id, canon_id=canon_id,
        name=name, canon_name=canon_name, kind=kind, project_id=project_id,
        anchor_confidence=anchor_confidence, anchor_source_type=anchor_source_type,
        origin=origin, proposal_id=proposal_id, technique=technique,
    )


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
        _UPSERT_ENRICHED_FACT_CYPHER,
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
        _PROMOTE_CYPHER,
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
        _RETRACT_CYPHER, user_id=user_id, origin=origin, proposal_id=proposal_id,
    )
    record = await result.single()
    return int(record["affected"]) if record else 0
