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
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import get_neighborhood_by_glossary_id
from app.wiki.context import DEFAULT_KG_LIMIT, gather_entity_context, gather_kg_facts
from app.wiki.fingerprint import stable_hash
from app.wiki.writeback import source_texts
from app.clients.book_client import get_book_client
from app.clients.embedding_client import get_embedding_client
from app.clients.glossary_client import get_glossary_client
from app.clients.reranker_client import get_reranker_client
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.wiki_gen_jobs import ActiveJobExists, WikiGenJob, WikiGenJobsRepo
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


# ── wiki-llm Phase-2 (D-WIKI-P2-KG-SWEEP) — current KG-neighbourhood hashes ────


class WikiKgHashesRequest(BaseModel):
    user_id: UUID
    entity_ids: list[str] = Field(default_factory=list)


class WikiKgHashesResponse(BaseModel):
    hashes: dict[str, str]


@router.post("/books/{book_id}/wiki/kg-hashes", response_model=WikiKgHashesResponse)
async def wiki_kg_hashes(
    book_id: UUID,
    req: WikiKgHashesRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> WikiKgHashesResponse:
    """Recompute the CURRENT ``kg_neighborhood_hash`` for each entity for the KG-drift
    sweep (glossary compares it to the stored ``build_inputs.kg_neighborhood_hash``).

    PARITY IS MANDATORY: this reuses the SAME ``gather_kg_facts`` + ``stable_hash``
    path as generation (``kg_limit=DEFAULT_KG_LIMIT``) so an unchanged neighbourhood
    hashes identically — a divergent hash would false-flag every article.

    An entity whose KG read is UNAVAILABLE (Neo4j down — the ``degraded`` marker) is
    OMITTED, never returned as the empty-list hash, so a transient outage can't drive
    false ``kg_drift``. No project (book not indexed) → an empty map (nothing to sweep).
    """
    if not req.entity_ids:
        return WikiKgHashesResponse(hashes={})
    projects = await projects_repo.list(req.user_id, book_id=book_id, limit=1)
    if not projects:
        return WikiKgHashesResponse(hashes={})
    project = projects[0]

    hashes: dict[str, str] = {}
    for eid in req.entity_ids:
        degraded: dict[str, str] = {}
        facts = await gather_kg_facts(
            entity_id=eid, user_id=req.user_id, project=project,
            kg_limit=DEFAULT_KG_LIMIT, degraded=degraded,
        )
        if degraded.get("kg") == "unavailable":
            continue  # KG unreachable for this entity — omit (don't fabricate a hash)
        hashes[eid] = stable_hash(sorted(facts))
    return WikiKgHashesResponse(hashes=hashes)


# ── wiki-llm W6b-2b — current source text (the change-diff "after") ───────────


class WikiSourceRef(BaseModel):
    source_type: str
    source_id: str


class WikiSourceTextRequest(BaseModel):
    user_id: UUID
    entity_id: str
    sources: list[WikiSourceRef] = Field(default_factory=list)


class WikiSourceTextResponse(BaseModel):
    texts: dict[str, str]


@router.post("/books/{book_id}/wiki/source-text", response_model=WikiSourceTextResponse)
async def wiki_source_text(
    book_id: UUID,
    req: WikiSourceTextRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> WikiSourceTextResponse:
    """The CURRENT source text for each requested source (the W6b-2 diff "after"),
    keyed ``f"{source_type}:{source_id}"``. Re-gathers through the SAME context path
    as generation (``gather_entity_context`` → :func:`source_texts`) so the before
    (captured at gen time) and after are formatted identically — a diff then shows
    only real content changes. Empty when the book isn't indexed or the entity can't
    be gathered (the caller degrades to no-diff). NOTE: a ``block`` source is a
    retrieval result, so its "after" is APPROXIMATE (re-retrieval may differ)."""
    if not req.sources:
        return WikiSourceTextResponse(texts={})
    projects = await projects_repo.list(req.user_id, book_id=book_id, limit=1)
    if not projects:
        return WikiSourceTextResponse(texts={})
    context = await gather_entity_context(
        entity_id=req.entity_id, book_id=book_id, user_id=req.user_id, project=projects[0],
        glossary_client=get_glossary_client(), book_client=get_book_client(),
        embedding_client=get_embedding_client(), reranker_client=get_reranker_client(),
    )
    if context is None:
        return WikiSourceTextResponse(texts={})
    all_texts = source_texts(context)
    wanted = {f"{s.source_type}:{s.source_id}" for s in req.sources}
    return WikiSourceTextResponse(texts={k: v for k, v in all_texts.items() if k in wanted})


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
    #: W5 — optional override model for the corrective revise re-gen (null = prose).
    revise_model_ref: str | None = None
    revise_model_source: str | None = None


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
            revise_model_ref=req.revise_model_ref, revise_model_source=req.revise_model_source,
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


# ── wiki-llm M7b — job status + resume/cancel (closes D-WIKI-M6-RESUME) ───────


class WikiGenJobStatus(BaseModel):
    """The poll shape: the FE drives a progress bar + needs_review/blocked surfacing
    off this. ``items_done``/``entity_ids`` are returned as counts only (the FE
    doesn't need the id lists)."""

    job_id: UUID
    status: str
    model_source: str
    model_ref: str
    items_total: int | None = None
    items_processed: int = 0
    items_done_count: int = 0
    entity_count: int = 0
    cost_spent_usd: Decimal = Decimal("0")
    max_spend_usd: Decimal | None = None
    error_message: str | None = None
    # W4a — the screen-③ results table: per-entity detail (entity_id →
    # {outcome, citations, flags, name}) + the live sub-step pointer.
    results: dict[str, Any] = Field(default_factory=dict)
    current_entity_id: str | None = None
    current_pass: str | None = None


def _to_status(job: WikiGenJob) -> WikiGenJobStatus:
    return WikiGenJobStatus(
        job_id=job.job_id, status=job.status, model_source=job.model_source,
        model_ref=job.model_ref, items_total=job.items_total,
        items_processed=job.items_processed, items_done_count=len(job.items_done),
        entity_count=len(job.entity_ids), cost_spent_usd=job.cost_spent_usd,
        max_spend_usd=job.max_spend_usd, error_message=job.error_message,
        results=job.results, current_entity_id=job.current_entity_id,
        current_pass=job.current_pass,
    )


async def _owned_job(
    repo: WikiGenJobsRepo, *, job_id: UUID, book_id: UUID, user_id: UUID
) -> WikiGenJob:
    """Load a job and assert it belongs to (book, user) — 404 otherwise so an id
    from another book/user is indistinguishable from a missing one."""
    job = await repo.get(job_id)
    if job is None or job.book_id != book_id or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


@router.get("/books/{book_id}/wiki/job", response_model=WikiGenJobStatus)
async def get_wiki_gen_job(book_id: UUID, user_id: UUID) -> WikiGenJobStatus:
    """The latest wiki-gen job for (book, user) — 404 when none exists. The FE
    polls this; it keeps returning the row after a terminal state (unlike the
    active-only per-book lock query)."""
    repo = WikiGenJobsRepo(get_knowledge_pool())
    job = await repo.get_latest_for_book(book_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no_job")
    return _to_status(job)


class WikiGenConfig(BaseModel):
    """Pre-flight cost basis for the FE estimate (D-WIKI-P2B-COST-ESTIMATE) — the
    flat per-article estimate the orchestrator's budget gate charges, so the shown
    estimate and the live ``cost_spent_usd`` agree. Token-precise pricing is the
    separate D-WIKI-M6-PRECISE-COST follow-up.

    W2 (gap-closure) also surfaces the CURRENT recipe versions here so the glossary
    public ``staleness/sweep`` proxy can run the recipe-drift sweep (stored
    build_inputs versions vs current) without knowing knowledge's config itself."""

    cost_per_article_usd: Decimal
    prompt_version: str
    pipeline_version: str


@router.get("/wiki/gen-config", response_model=WikiGenConfig)
async def get_wiki_gen_config() -> WikiGenConfig:
    """The flat per-article wiki-gen cost estimate + current recipe versions (global
    config; not book-scoped)."""
    return WikiGenConfig(
        cost_per_article_usd=Decimal(str(settings.wiki_gen_cost_per_article_usd)),
        prompt_version=settings.wiki_prompt_version,
        pipeline_version=settings.wiki_pipeline_version,
    )


class WikiGenJobActionRequest(BaseModel):
    user_id: UUID


@router.post("/books/{book_id}/wiki/job/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_wiki_gen_job(
    book_id: UUID, job_id: UUID, req: WikiGenJobActionRequest
) -> dict:
    """Resume a budget-paused job: flip paused→pending + re-enqueue (skip-done
    handles partial progress). 404 if the job isn't the owner's for this book;
    409 if it isn't paused."""
    repo = WikiGenJobsRepo(get_knowledge_pool())
    await _owned_job(repo, job_id=job_id, book_id=book_id, user_id=req.user_id)
    if not await repo.resume(job_id):
        raise HTTPException(status_code=409, detail="not_paused")
    await enqueue_wiki_gen(_redis(), str(job_id))
    return {"job_id": str(job_id), "status": "pending"}


@router.post("/books/{book_id}/wiki/job/{job_id}/cancel")
async def cancel_wiki_gen_job(
    book_id: UUID, job_id: UUID, req: WikiGenJobActionRequest
) -> dict:
    """Cancel a not-yet-running job (pending|paused), releasing the per-book lock.
    404 if not the owner's; 409 if it can't be cancelled (running/terminal —
    running-cancel is D-WIKI-M7B-RUNNING-CANCEL)."""
    repo = WikiGenJobsRepo(get_knowledge_pool())
    await _owned_job(repo, job_id=job_id, book_id=book_id, user_id=req.user_id)
    if not await repo.cancel(job_id):
        raise HTTPException(status_code=409, detail="not_cancellable")
    return {"job_id": str(job_id), "status": "cancelled"}
