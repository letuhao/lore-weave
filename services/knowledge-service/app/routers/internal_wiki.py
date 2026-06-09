"""C5 (D4-03) — Internal wiki-neighborhood read endpoint.

POST /internal/knowledge/wiki-neighborhood

Service-to-service read surface for the wiki-from-KG renderer that
lives inside **glossary-service** (glossary hosts the wiki feature but
does NOT hold the entity-to-entity relationship graph — that graph is
only in Neo4j here, keyed by ``glossary_entity_id``).

Given a ``(user_id, glossary_entity_id)`` pair this returns the
anchored entity plus its 1-hop ``:RELATES_TO`` neighborhood. Each
relation carries ``confidence`` + ``pending_validation`` and the entity
carries ``source_types``, so the glossary renderer can mark enriched
material (``source_type='enriched'``, pending, ``confidence < 1.0``)
visibly distinct from glossary-authored canon
(``source_type='glossary'``, ``confidence = 1.0``) — H0 LOCKED.

This is a **READ-ONLY** path (Q2 LOCKED): the wiki/enrichment machinery
never writes Neo4j canonical content directly. The write-back goes
through the glossary SSOT wiki tables.

Authentication: X-Internal-Token (service-to-service). Trusts the
caller's ``user_id`` — glossary-service passes the book owner's id,
which is the Neo4j tenant key.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import get_neighborhood_by_glossary_id
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.wiki_gen_jobs import ActiveJobExists, WikiGenJobsRepo
from app.deps import get_knowledge_pool, get_projects_repo
from app.jobs.wiki_gen_enqueue import enqueue_wiki_gen
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/knowledge",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


# ── Request / Response models ────────────────────────────────────────


class WikiNeighborhoodRequest(BaseModel):
    user_id: UUID
    glossary_entity_id: UUID
    # Cap on the relation payload. Mirrors ENTITIES_DETAIL_REL_CAP; a
    # caller that wants fewer (a compact wiki body) can lower it.
    rel_cap: int = Field(default=200, ge=1, le=200)


class NeighborRelation(BaseModel):
    """One 1-hop edge, flattened for the wiki renderer.

    ``source_type`` is DERIVED here so the H0 distinction is computed
    once, server-side, rather than re-derived in Go: an edge is
    ``enriched`` when it is pending validation OR sub-canonical
    confidence (< 1.0); otherwise it is glossary canon. The renderer
    must surface this marker, never silently merge enriched as canon.
    """

    predicate: str
    subject_name: str | None = None
    subject_kind: str | None = None
    object_name: str | None = None
    object_kind: str | None = None
    confidence: float = 0.0
    pending_validation: bool = False
    source_type: str = "glossary"


class WikiNeighborhoodResponse(BaseModel):
    """Empty/None neighborhood is a first-class valid result: ``found``
    is False, ``relations`` is empty, and the renderer produces a
    minimal body (no crash)."""

    found: bool = False
    glossary_entity_id: UUID
    name: str | None = None
    kind: str | None = None
    # The entity's own canon status. Glossary-anchored entities carry
    # ``source_types=['glossary']``; an enriched-origin entity carries
    # an ``enriched``/``enriched:<technique>`` marker.
    source_types: list[str] = Field(default_factory=list)
    entity_source_type: str = "glossary"
    relations: list[NeighborRelation] = Field(default_factory=list)
    total_relations: int = 0
    relations_truncated: bool = False


def _derive_source_type(
    *, pending_validation: bool, confidence: float
) -> str:
    """H0: an edge is enriched (quarantined) when it is pending
    validation OR its confidence is below canon (1.0). Canon edges are
    validated AND confidence == 1.0."""
    if pending_validation or confidence < 1.0:
        return "enriched"
    return "glossary"


def _entity_source_type(source_types: list[str]) -> str:
    """H0: glossary canon iff the entity bears the ``glossary`` source
    marker and no enriched marker. Any ``enriched``-prefixed marker
    makes the entity itself enriched-origin."""
    if any(st == "enriched" or st.startswith("enriched:") for st in source_types):
        return "enriched"
    if "glossary" in source_types:
        return "glossary"
    # No explicit marker → treat as enriched (fail-safe: never silently
    # promote unknown-origin content to canon — H0).
    return "enriched" if source_types else "glossary"


@router.post(
    "/wiki-neighborhood",
    response_model=WikiNeighborhoodResponse,
)
async def get_wiki_neighborhood(
    req: WikiNeighborhoodRequest,
) -> WikiNeighborhoodResponse:
    """C5 (D4-03) — read an entity's 1-hop KG neighborhood for the
    glossary wiki renderer. Read-only; never writes Neo4j (Q2)."""
    async with neo4j_session() as session:
        detail = await get_neighborhood_by_glossary_id(
            session,
            user_id=str(req.user_id),
            glossary_entity_id=str(req.glossary_entity_id),
            rel_cap=req.rel_cap,
        )

    if detail is None:
        # Not synced into the KG yet, or cross-user — a valid empty
        # neighborhood, not an error.
        return WikiNeighborhoodResponse(glossary_entity_id=req.glossary_entity_id)

    relations = [
        NeighborRelation(
            predicate=r.predicate,
            subject_name=r.subject_name,
            subject_kind=r.subject_kind,
            object_name=r.object_name,
            object_kind=r.object_kind,
            confidence=r.confidence,
            pending_validation=r.pending_validation,
            source_type=_derive_source_type(
                pending_validation=r.pending_validation,
                confidence=r.confidence,
            ),
        )
        for r in detail.relations
    ]

    return WikiNeighborhoodResponse(
        found=True,
        glossary_entity_id=req.glossary_entity_id,
        name=detail.entity.name,
        kind=detail.entity.kind,
        source_types=detail.entity.source_types,
        entity_source_type=_entity_source_type(detail.entity.source_types),
        relations=relations,
        total_relations=detail.total_relations,
        relations_truncated=detail.relations_truncated,
    )


# ── wiki-llm M6 — batch generation trigger ───────────────────────────────────

_redis_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    """Lazy module-level redis client for the wiki-gen XADD (mirrors the summary
    enqueue pattern; one client per process)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url)
    return _redis_client


class WikiGenerateRequest(BaseModel):
    user_id: UUID
    model_source: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    #: the entities to generate. Empty is rejected (the glossary delegate resolves
    #: the selection by kind and passes explicit ids); generate-ALL is a follow-up.
    entity_ids: list[str] = Field(default_factory=list)
    max_spend_usd: Decimal | None = None


@router.post("/books/{book_id}/wiki/generate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_wiki_generation(
    book_id: UUID,
    req: WikiGenerateRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> dict:
    """Create a wiki-gen job for the book + enqueue it. 202 + job_id on accept;
    404 not_indexed if the user has no project for the book; 409 (+ the existing
    job_id) when an active job already holds the per-book lock."""
    if not req.entity_ids:
        raise HTTPException(status_code=400, detail="entity_ids required")
    projects = await projects_repo.list(req.user_id, book_id=book_id, limit=1)
    if not projects:
        raise HTTPException(status_code=404, detail="not_indexed")

    repo = WikiGenJobsRepo(get_knowledge_pool())
    try:
        job = await repo.create(
            user_id=req.user_id, project_id=projects[0].project_id, book_id=book_id,
            model_source=req.model_source, model_ref=req.model_ref,
            entity_ids=req.entity_ids, max_spend_usd=req.max_spend_usd,
            items_total=len(req.entity_ids),
        )
    except ActiveJobExists as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "active_job_exists",
                "job_id": str(exc.existing_job_id) if exc.existing_job_id else None,
            },
        )
    await enqueue_wiki_gen(_redis(), str(job.job_id))
    return {"job_id": str(job.job_id), "status": "pending"}
