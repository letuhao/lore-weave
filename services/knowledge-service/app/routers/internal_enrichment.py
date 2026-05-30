"""C13 — Internal enrichment write-back / promote / retract endpoints.

POST /internal/knowledge/enriched-writeback   — admit an approved enrichment
       proposal's facts into the KG **QUARANTINED** (H0): each enriched fact is
       a node + edge tagged ``source_type='enriched:<technique>'``,
       ``pending_validation=true``, ``confidence < 1.0`` — visibly distinct
       from the glossary-authored canon entity it anchors on.
POST /internal/knowledge/enriched-promote     — flip a previously-written
       enriched fact-set to canon (``source_type='glossary'``, ``confidence=1.0``,
       ``pending_validation=false``) WHILE retaining a permanent origin marker
       (``origin='enrichment'`` + ``promoted_from_proposal_id`` + ``promoted_by`` +
       ``promoted_at`` + ``original_technique``).
POST /internal/knowledge/enriched-retract     — soft-retract a written/promoted
       enriched fact-set (set ``valid_until`` so it leaves the active graph),
       reversible.

This is the KG side of the H0 boundary. The glossary SSOT (entity anchor) is
written by lore-enrichment-service through glossary ``extract-entities`` (Q2);
this endpoint admits the *enriched dimension facts* about that anchor, which
glossary's extract-entities cannot tag with a source_type. Writing QUARANTINED
(non-canonical) enriched facts is NOT a canonical-content write — Q2 forbids
enrichment writing *canonical* Neo4j content directly, and these facts are
explicitly non-canon until the author promotes them.

Idempotency: every enriched node/edge id is deterministic
(``sha256(proposal_id, dimension)``), so a re-call of write-back MERGEs the same
nodes in place — no duplicate canon, no double-write. Promote/retract are
likewise idempotent (set the same target state).

Authentication: X-Internal-Token (service-to-service). The caller
(lore-enrichment-service) has already verified book ownership for promote.
"""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.canonical import canonicalize_entity_name, entity_canonical_id
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/knowledge",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

#: The permanent origin marker stamped on every enriched node/edge (H0 — lifetime
#: "was-makeup" traceability). It SURVIVES promotion: promote flips source_type to
#: 'glossary' + confidence 1.0 but never clears ``origin`` / ``promoted_from_*``.
_ENRICHMENT_ORIGIN = "enrichment"

#: Quarantine ceiling — an enriched fact may never reach canon confidence (1.0)
#: until promotion. The caller supplies confidence < 1.0; we clamp defensively.
_CANON_CONFIDENCE = 1.0


# ── Request / Response models ────────────────────────────────────────


class EnrichedDimensionFact(BaseModel):
    """One generated dimension value to admit as a quarantined fact."""

    dimension: str = Field(min_length=1)
    content: str = Field(min_length=1)
    confidence: float = Field(gt=0.0, lt=1.0)


class EnrichedWritebackRequest(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    proposal_id: UUID
    glossary_entity_id: UUID
    canonical_name: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    technique: str = Field(min_length=1)
    facts: list[EnrichedDimensionFact] = Field(min_length=1)


class EnrichedPromoteRequest(BaseModel):
    user_id: UUID
    proposal_id: UUID
    promoted_by: UUID
    promoted_at: str = Field(min_length=1)


class EnrichedRetractRequest(BaseModel):
    user_id: UUID
    proposal_id: UUID


class EnrichedFactRef(BaseModel):
    fact_id: str
    edge_id: str
    dimension: str
    source_type: str
    confidence: float
    pending_validation: bool


class EnrichedWritebackResponse(BaseModel):
    proposal_id: UUID
    glossary_entity_id: UUID
    facts: list[EnrichedFactRef]
    # The state the facts were left in (quarantined on write-back, canon on
    # promote). Lets the caller assert the H0 boundary held.
    canon: bool = False


class EnrichedMutationResponse(BaseModel):
    proposal_id: UUID
    affected: int
    canon: bool = False
    retracted: bool = False


def _enriched_node_id(proposal_id: str, dimension: str) -> str:
    """Deterministic id for an enriched fact node → idempotent write-back."""
    raw = f"enriched::{proposal_id}::{dimension}".encode("utf-8")
    return "enr_" + hashlib.sha256(raw).hexdigest()[:32]


def _enriched_edge_id(proposal_id: str, dimension: str) -> str:
    raw = f"enriched-edge::{proposal_id}::{dimension}".encode("utf-8")
    return "enre_" + hashlib.sha256(raw).hexdigest()[:32]


@router.post("/enriched-writeback", response_model=EnrichedWritebackResponse)
async def enriched_writeback(
    req: EnrichedWritebackRequest,
) -> EnrichedWritebackResponse:
    """Admit an approved proposal's facts into the KG QUARANTINED (H0).

    Each dimension becomes an enriched ``:Fact`` node tagged
    ``source_type='enriched:<technique>'`` + ``pending_validation=true`` +
    ``confidence < 1.0``, linked from the canon glossary entity via an enriched
    ``:RELATES_TO`` edge (same markers). NEVER canon — only ``enriched-promote``
    canonizes. Idempotent: deterministic ids MERGE in place on re-call.
    """
    source_type = f"enriched:{req.technique}"
    project_id = str(req.project_id) if req.project_id else None
    canon_id = entity_canonical_id(
        str(req.user_id), project_id, req.canonical_name, req.entity_kind
    )
    canon_name = canonicalize_entity_name(req.canonical_name)
    # The minted-anchor confidence (FIX-2 / WARN-2): when write-back is the
    # entity's actual creator (the anchor did not pre-exist), the anchor is born
    # marked-as-enrichment with sub-canon confidence — NEVER canon-looking. Use
    # the strongest fact confidence (already < 1.0), clamped defensively.
    anchor_confidence = min(max((f.confidence for f in req.facts), default=0.5), 0.99)

    written: list[EnrichedFactRef] = []
    async with neo4j_session() as session:
        # Ensure the entity anchor exists in the graph so the enriched edge has an
        # endpoint. Two cases, kept strictly distinct (H0 / FIX-2):
        #   * ON MATCH — a pre-existing canon anchor (synced by the glossary→KG
        #     pipeline) stays EXACTLY as it is. We do not touch its source_type /
        #     confidence / origin; enrichment never makes a canon node look more
        #     or less canon. (Only updated_at bumps, and id is back-filled if a
        #     legacy node lacks one.)
        #   * ON CREATE — enrichment is the entity's CREATOR (anchor didn't
        #     pre-exist). The node is born MARKED-AS-ENRICHMENT: origin=
        #     'enrichment', pending_validation=true, confidence<1.0,
        #     source_type='enriched:<technique>'. It is therefore indistinguishable
        #     from canon NO LONGER — the real glossary→KG sync (a genuine canon
        #     write) clears these markers ON MATCH when the owner authors/promotes.
        await session.run(
            """
            MERGE (e:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
            ON CREATE SET
              e.id = $canon_id,
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
              e.id = coalesce(e.id, $canon_id),
              e.updated_at = datetime()
            """,
            user_id=str(req.user_id),
            glossary_entity_id=str(req.glossary_entity_id),
            canon_id=canon_id,
            name=req.canonical_name,
            canon_name=canon_name,
            kind=req.entity_kind,
            project_id=project_id or "global",
            anchor_confidence=anchor_confidence,
            anchor_source_type=source_type,
            origin=_ENRICHMENT_ORIGIN,
            proposal_id=str(req.proposal_id),
            technique=req.technique,
        )

        for fact in req.facts:
            node_id = _enriched_node_id(str(req.proposal_id), fact.dimension)
            edge_id = _enriched_edge_id(str(req.proposal_id), fact.dimension)
            confidence = min(fact.confidence, 0.99)  # H0: never canon on write-back
            await session.run(
                """
                MATCH (e:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
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
                """,
                user_id=str(req.user_id),
                glossary_entity_id=str(req.glossary_entity_id),
                node_id=node_id,
                edge_id=edge_id,
                project_id=project_id or "global",
                dimension=fact.dimension,
                content=fact.content,
                confidence=confidence,
                source_type=source_type,
                origin=_ENRICHMENT_ORIGIN,
                proposal_id=str(req.proposal_id),
                technique=req.technique,
            )
            written.append(
                EnrichedFactRef(
                    fact_id=node_id,
                    edge_id=edge_id,
                    dimension=fact.dimension,
                    source_type=source_type,
                    confidence=confidence,
                    pending_validation=True,
                )
            )

    logger.info(
        "C13: enriched write-back QUARANTINED proposal=%s entity=%s facts=%d",
        req.proposal_id, req.glossary_entity_id, len(written),
    )
    return EnrichedWritebackResponse(
        proposal_id=req.proposal_id,
        glossary_entity_id=req.glossary_entity_id,
        facts=written,
        canon=False,
    )


@router.post("/enriched-promote", response_model=EnrichedMutationResponse)
async def enriched_promote(
    req: EnrichedPromoteRequest,
) -> EnrichedMutationResponse:
    """Flip a written enriched fact-set to canon (H0 promote).

    ``source_type → 'glossary'``, ``confidence → 1.0``,
    ``pending_validation → false`` on every enriched node + edge of this
    proposal. The permanent origin marker (``origin='enrichment'`` +
    ``promoted_from_proposal_id`` + ``original_technique``) is RETAINED and the
    promote actor/time are stamped (``promoted_by`` / ``promoted_at``). Only the
    facts of THIS proposal are touched (filtered on ``promoted_from_proposal_id``
    + ``origin='enrichment'``). Idempotent.
    """
    async with neo4j_session() as session:
        result = await session.run(
            """
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
            """,
            user_id=str(req.user_id),
            origin=_ENRICHMENT_ORIGIN,
            proposal_id=str(req.proposal_id),
            promoted_by=str(req.promoted_by),
            promoted_at=req.promoted_at,
        )
        record = await result.single()
        affected = record["affected"] if record else 0

    logger.info(
        "C13: enriched PROMOTE → canon proposal=%s facts=%d (origin marker retained)",
        req.proposal_id, affected,
    )
    return EnrichedMutationResponse(
        proposal_id=req.proposal_id, affected=affected, canon=True,
    )


@router.post("/enriched-retract", response_model=EnrichedMutationResponse)
async def enriched_retract(
    req: EnrichedRetractRequest,
) -> EnrichedMutationResponse:
    """Soft-retract an enriched fact-set (reversible).

    Sets ``valid_until`` on every enriched node + edge of this proposal so they
    leave the ACTIVE graph (the neighborhood query filters ``valid_until IS
    NULL``) without a hard delete — reversible by clearing ``valid_until``.
    Mirrors the glossary recycle-bin soft-delete (M6) on the KG side. Only
    touches this proposal's enriched facts; never deletes canon. Idempotent.
    """
    async with neo4j_session() as session:
        result = await session.run(
            """
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
            """,
            user_id=str(req.user_id),
            origin=_ENRICHMENT_ORIGIN,
            proposal_id=str(req.proposal_id),
        )
        record = await result.single()
        affected = record["affected"] if record else 0

    logger.info(
        "C13: enriched RETRACT (soft) proposal=%s facts=%d", req.proposal_id, affected,
    )
    return EnrichedMutationResponse(
        proposal_id=req.proposal_id, affected=affected, retracted=True,
    )
