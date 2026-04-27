"""K16.6a — Internal extraction endpoint for worker-ai.

POST /internal/extraction/extract-item

Runs the Pass 2 LLM extraction pipeline on a single item (chapter or
chat turn) and writes results to Neo4j. Called by worker-ai as part of
the extraction job loop.

Authentication: X-Internal-Token (service-to-service).
Trusts the caller's user_id — worker-ai reads it from extraction_jobs.
"""

from __future__ import annotations

import logging
import time
from typing import Literal
from uuid import UUID

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.glossary_client import get_glossary_client
from app.clients.llm_client import get_llm_client
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.db.repositories.job_logs import JobLogsRepo
from app.extraction.anchor_loader import Anchor, load_glossary_anchors
from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from app.extraction.pass2_orchestrator import (
    extract_pass2_chapter,
    extract_pass2_chat_turn,
)
from app.extraction.pass2_writer import write_pass2_extraction
from app.middleware.internal_auth import require_internal_token

# Phase 4a-δ — retryable map keyed on `ExtractionError.stage`. The
# gateway already retried transients before raising `provider_exhausted`
# at the SDK boundary, so a worker-level retry is the second attempt.
# `provider` (non-transient terminal) and `cancelled` are not retried.
_RETRYABLE_STAGES = {"provider_exhausted"}

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/extraction",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


# ── Request / Response models ────────────────────────────────────────

ItemType = Literal["chapter", "chat_turn"]


class ExtractItemRequest(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    item_type: ItemType
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    job_id: UUID

    # Model to use for LLM extraction
    model_source: Literal["user_model", "platform_model"] = "user_model"
    model_ref: str = Field(min_length=1, max_length=200)

    # Text content — exactly one of these should be populated
    chapter_text: str | None = None
    user_message: str | None = None
    assistant_message: str | None = None

    # Previously known entities for context enrichment
    known_entities: list[str] = Field(default_factory=list)


class ExtractItemResponse(BaseModel):
    source_id: str
    entities_merged: int = 0
    relations_created: int = 0
    events_merged: int = 0
    facts_merged: int = 0
    evidence_edges: int = 0
    duration_seconds: float = 0.0


class PersistPass2Request(BaseModel):
    """Phase 4b-β — request body for the persist-pass2 endpoint.

    Worker-ai (4b-γ) calls this AFTER running the Pass 2 LLM stage
    itself via ``loreweave_extraction.extract_pass2(llm_client, ...)``.
    The wire types match the library's candidate models exactly so
    `.model_dump()` on the worker side round-trips through JSON without
    field renames.

    The 4 candidate lists are all optional — the writer persists
    whatever's supplied. ``extraction_model`` tags evidence edges so
    operators can later trace which LLM produced which Pass 2 row.
    """

    user_id: UUID
    project_id: UUID | None = None
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    job_id: UUID
    extraction_model: str = Field(default="llm-v1", max_length=200)

    entities: list[LLMEntityCandidate] = Field(default_factory=list)
    relations: list[LLMRelationCandidate] = Field(default_factory=list)
    events: list[LLMEventCandidate] = Field(default_factory=list)
    facts: list[LLMFactCandidate] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────


_ANCHOR_CACHE_TTL_S = 60.0
_ANCHOR_CACHE_MAX = 256

# P-K13.0-01 — short-TTL cache for anchor pre-load.
#
# Every /extract-item call runs _load_anchors_for_extraction once.
# A 100-chapter extraction job makes 100 identical calls (same
# user_id, same project_id) within the job's runtime window,
# producing 100 glossary HTTP calls + 100×N MERGE round-trips to
# upsert the same anchor set. Caching the result for 60s collapses
# that to one real load + 99 cache hits for the common case.
#
# Key: (str(user_id), str(project_id_or_none))
# Value: list[Anchor] — only successful loads are cached. Empty
# lists from the early-out paths (project_id=None, no book_id) are
# ALSO cached because they're the correct answer; re-running the
# SELECT inside the TTL would be wasted work.
#
# **Side-effect caveat:** the uncached path runs
# `load_glossary_anchors` which MERGEs each anchor as a Neo4j
# `:Entity` node. On cache hit we skip that MERGE. Safe because the
# first call per 60s window does the upsert and later calls in the
# same window see the already-converged Neo4j state — MERGE is
# idempotent so we're not missing state-building work, just
# skipping redundant round-trips. If Neo4j is purged mid-job (rare,
# maintenance only), downstream extraction may miss anchors until
# the TTL expires or the worker restarts.
#
# Per-process. On worker restart the cache empties and the first
# call refills it. No manual invalidation — 60s is short enough
# that glossary edits show up quickly and no cleanup is required.
_anchor_cache: TTLCache[tuple[str, str], list[Anchor]] = TTLCache(
    maxsize=_ANCHOR_CACHE_MAX, ttl=_ANCHOR_CACHE_TTL_S,
)


async def _load_anchors_for_extraction(
    *, user_id: UUID, project_id: UUID | None,
) -> list[Anchor]:
    """K13.0 Pass 0: pre-load glossary anchors before Pass 2 runs.

    Returns an empty list (extraction proceeds without anchor bias) if:
      - project_id is None (chat-only, no book)
      - no knowledge_projects row matches (user_id, project_id)
      - project has no book_id linked (Mode 1 project)
      - glossary_client.list_entities fails (circuit open, 5xx, …)
      - any Neo4j hiccup during the upsert loop

    Per-entry failures inside load_glossary_anchors are already
    isolated there; this helper only handles the outer envelope.

    **P-K13.0-01:** results are cached per `(user_id, project_id)`
    with a 60s TTL so bulk extraction jobs don't re-run the glossary
    fetch + anchor MERGE loop on every item.
    """
    # Cache key uses stringified UUIDs so None project_id maps to "".
    cache_key = (str(user_id), str(project_id) if project_id else "")
    cached = _anchor_cache.get(cache_key)
    if cached is not None:
        return cached

    if project_id is None:
        _anchor_cache[cache_key] = []
        return []
    try:
        async with get_knowledge_pool().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT book_id FROM knowledge_projects "
                "WHERE project_id = $1 AND user_id = $2",
                project_id, user_id,
            )
        book_id = row["book_id"] if row else None
        if book_id is None:
            _anchor_cache[cache_key] = []
            return []
        async with neo4j_session() as anchor_session:
            anchors = await load_glossary_anchors(
                anchor_session,
                get_glossary_client(),
                user_id=str(user_id),
                project_id=str(project_id),
                book_id=book_id,
            )
        _anchor_cache[cache_key] = anchors
        return anchors
    except Exception:
        logger.warning(
            "K13.0: anchor pre-load failed for project=%s — "
            "extraction will run without anchor bias",
            project_id, exc_info=True,
        )
        # Don't cache failures — a transient glossary outage
        # shouldn't lock in empty anchors for 60s.
        return []


# ── Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/extract-item",
    response_model=ExtractItemResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_item(body: ExtractItemRequest) -> ExtractItemResponse:
    """Run Pass 2 extraction on a single item and write to Neo4j.

    Called by worker-ai for each item in an extraction job. The worker
    handles try_spend, advance_cursor, and pause/cancel — this endpoint
    is purely the extraction + write step.
    """
    if not settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured — extraction requires NEO4J_URI",
        )

    started = time.perf_counter()
    llm_client = get_llm_client()

    # C3 (D-K19b.8-02) — stage producer for the FE JobLogsPanel.
    # Inlined like `_try_spend` elsewhere rather than Depends() since
    # the rest of this router already resolves collaborators inline
    # (module-level neo4j_session, get_llm_client, etc.). Matches
    # the "internal router, no DI" convention. Best-effort: if the
    # pool isn't initialised (unit tests that only mock the extractor
    # helpers, or a pre-migration boot), the producer is silently
    # disabled — extraction still runs, JobLogsPanel just won't show
    # the stage events for this call.
    try:
        job_logs_repo: JobLogsRepo | None = JobLogsRepo(get_knowledge_pool())
    except Exception:
        logger.debug(
            "C3: knowledge pool unavailable — pass2 stage producer disabled",
            exc_info=True,
        )
        job_logs_repo = None

    # K13.0 — pre-load glossary anchors. Degrades to [] on any failure
    # so extraction still runs (without duplicate-reduction benefit).
    anchors = await _load_anchors_for_extraction(
        user_id=body.user_id, project_id=body.project_id,
    )

    try:
        async with neo4j_session() as session:
            if body.item_type == "chapter":
                if not body.chapter_text:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="chapter_text required for item_type=chapter",
                    )
                result = await extract_pass2_chapter(
                    session,
                    user_id=str(body.user_id),
                    project_id=str(body.project_id) if body.project_id else None,
                    source_type=body.source_type,
                    source_id=body.source_id,
                    job_id=str(body.job_id),
                    chapter_text=body.chapter_text,
                    known_entities=body.known_entities,
                    model_source=body.model_source,
                    model_ref=body.model_ref,
                    llm_client=llm_client,
                    anchors=anchors,
                    job_logs_repo=job_logs_repo,
                )
            else:  # "chat_turn" — Pydantic Literal rejects other values at 422
                if not body.user_message and not body.assistant_message:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="user_message or assistant_message required for item_type=chat_turn",
                    )
                result = await extract_pass2_chat_turn(
                    session,
                    user_id=str(body.user_id),
                    project_id=str(body.project_id) if body.project_id else None,
                    source_type=body.source_type,
                    source_id=body.source_id,
                    job_id=str(body.job_id),
                    user_message=body.user_message,
                    assistant_message=body.assistant_message,
                    known_entities=body.known_entities,
                    model_source=body.model_source,
                    model_ref=body.model_ref,
                    llm_client=llm_client,
                    anchors=anchors,
                    job_logs_repo=job_logs_repo,
                )
    except HTTPException:
        raise  # re-raise validation errors (422)
    except ExtractionError as exc:
        retryable = exc.stage in _RETRYABLE_STAGES
        logger.warning(
            "K16.6a: extraction error source_id=%s stage=%s retryable=%s: %s",
            body.source_id, exc.stage, retryable, exc,
        )
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
                if retryable
                else status.HTTP_422_UNPROCESSABLE_CONTENT
            ),
            detail={"retryable": retryable, "error": str(exc)},
        )

    elapsed = time.perf_counter() - started
    logger.info(
        "K16.6a: extract-item done source_id=%s type=%s "
        "entities=%d relations=%d events=%d facts=%d in %.1fs",
        body.source_id, body.item_type,
        result.entities_merged, result.relations_created,
        result.events_merged, result.facts_merged, elapsed,
    )

    return ExtractItemResponse(
        source_id=result.source_id,
        entities_merged=result.entities_merged,
        relations_created=result.relations_created,
        events_merged=result.events_merged,
        facts_merged=result.facts_merged,
        evidence_edges=result.evidence_edges,
        duration_seconds=round(elapsed, 2),
    )


# ── Phase 4b-β: persist-pass2 endpoint ───────────────────────────────


@router.post(
    "/persist-pass2",
    response_model=ExtractItemResponse,
    status_code=status.HTTP_200_OK,
)
async def persist_pass2(body: PersistPass2Request) -> ExtractItemResponse:
    """Persist pre-extracted Pass 2 candidates to Neo4j.

    Phase 4b-β: this endpoint is the new persistence boundary that
    worker-ai (4b-γ) will use after running the Pass 2 LLM stage
    itself via ``loreweave_extraction.extract_pass2(llm_client, ...)``.
    The legacy ``/extract-item`` endpoint stays for back-compat — it
    still runs LLM + persist in one HTTP call.

    Why this split:
      - ``/extract-item`` blocks the worker for the full LLM wall-time
        (capped at 120s today, often hit on chunked extraction).
      - ``/persist-pass2`` is a pure Neo4j-write endpoint — fast and
        bounded. The LLM wait moves to the worker process where it can
        be parallelized across chapters or interleaved with other work.

    Anchor pre-load reuses ``_load_anchors_for_extraction`` so Pass 1
    glossary anchors continue to anchor candidates the same way they
    did under ``/extract-item``.
    """
    if not settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured — extraction requires NEO4J_URI",
        )

    started = time.perf_counter()

    # K13.0 — same anchor pre-load as extract-item. Cached per
    # (user_id, project_id) for 60s so a 100-chapter job doesn't
    # re-fetch the glossary 100 times.
    anchors = await _load_anchors_for_extraction(
        user_id=body.user_id, project_id=body.project_id,
    )

    async with neo4j_session() as session:
        result = await write_pass2_extraction(
            session,
            user_id=str(body.user_id),
            project_id=str(body.project_id) if body.project_id else None,
            source_type=body.source_type,
            source_id=body.source_id,
            job_id=str(body.job_id),
            entities=body.entities,
            relations=body.relations,
            events=body.events,
            facts=body.facts,
            extraction_model=body.extraction_model,
            anchors=anchors,
        )

    elapsed = time.perf_counter() - started
    logger.info(
        "Phase 4b-β: persist-pass2 done source_id=%s "
        "entities=%d relations=%d events=%d facts=%d in %.1fs",
        body.source_id,
        result.entities_merged, result.relations_created,
        result.events_merged, result.facts_merged, elapsed,
    )

    # /review-impl MED#1 — emit pass2_write job_logs event so the
    # FE's JobLogsPanel keeps showing "extraction complete" entries
    # after worker-ai (4b-γ) migrates from extract-item to persist-pass2.
    # Best-effort: skip silently if the pool isn't initialised (unit
    # tests that only mock the writer) or the append errors. Same
    # pattern as pass2_orchestrator._emit_log.
    try:
        job_logs_repo = JobLogsRepo(get_knowledge_pool())
        await job_logs_repo.append(
            body.user_id, body.job_id, "info",
            f"Pass 2 write complete: "
            f"entities={result.entities_merged}, "
            f"relations={result.relations_created}, "
            f"events={result.events_merged}, "
            f"facts={result.facts_merged} "
            f"in {elapsed:.2f}s",
            {
                "event": "pass2_write",
                "source_type": body.source_type,
                "source_id": body.source_id,
                "entities_merged": result.entities_merged,
                "relations_created": result.relations_created,
                "events_merged": result.events_merged,
                "facts_merged": result.facts_merged,
                "evidence_edges": result.evidence_edges,
                "duration_ms": int(elapsed * 1000),
            },
        )
    except Exception:
        logger.warning(
            "Phase 4b-β: persist-pass2 stage log emit failed "
            "(non-fatal) source_id=%s",
            body.source_id, exc_info=True,
        )

    return ExtractItemResponse(
        source_id=result.source_id,
        entities_merged=result.entities_merged,
        relations_created=result.relations_created,
        events_merged=result.events_merged,
        facts_merged=result.facts_merged,
        evidence_edges=result.evidence_edges,
        duration_seconds=round(elapsed, 2),
    )


# ── C12c-a: glossary-sync-entity endpoint ────────────────────────────

# Thin wrapper around the K15.11 `sync_glossary_entity_to_neo4j`
# helper. Worker-ai calls this per-entity while iterating through a
# book's glossary during `scope='glossary_sync'` (or the glossary tail
# of `scope='all'`) extraction jobs. Kept separate from /extract-item
# because:
#   - no LLM call → no provider client, no model_ref
#   - no anchor pre-load → bypasses the 60s TTL cache
#   - writes a fully-trusted :Entity (confidence=1.0, source='glossary')
#     rather than running the quarantine pipeline

from app.extraction.glossary_sync import sync_glossary_entity_to_neo4j


class GlossarySyncEntityRequest(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    glossary_entity_id: UUID
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    short_description: str | None = None


class GlossarySyncEntityResponse(BaseModel):
    glossary_entity_id: str
    action: Literal["created", "updated"]
    canonical_name: str


@router.post(
    "/glossary-sync-entity",
    response_model=GlossarySyncEntityResponse,
    status_code=status.HTTP_200_OK,
)
async def glossary_sync_entity(
    body: GlossarySyncEntityRequest,
) -> GlossarySyncEntityResponse:
    """C12c-a — MERGE a glossary entity into Neo4j as a high-confidence
    :Entity node. Idempotent: repeat calls update the node in place.

    Returns the helper's native shape (glossary_entity_id / action /
    canonical_name) plus a 500 fallback on unexpected Neo4j errors
    (the helper itself doesn't catch them).
    """
    try:
        async with neo4j_session() as session:
            result = await sync_glossary_entity_to_neo4j(
                session,
                user_id=str(body.user_id),
                project_id=str(body.project_id) if body.project_id else None,
                glossary_entity_id=str(body.glossary_entity_id),
                name=body.name,
                kind=body.kind,
                aliases=list(body.aliases),
                short_description=body.short_description,
            )
    except Exception as exc:  # noqa: BLE001 — boundary handler
        # /review-impl LOW#4 — don't echo raw exception text across
        # the service boundary. logger.exception captures the full
        # traceback + message locally; the wire response stays opaque
        # so Neo4j internals (node ids, statement fragments) don't
        # land in worker-ai logs.
        logger.exception(
            "C12c-a: glossary_sync_entity failed for %s: %s",
            body.glossary_entity_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "neo4j_error",
                "message": "failed to merge glossary entity",
            },
        ) from exc

    action = result.get("action", "updated")
    if action not in ("created", "updated"):
        # Defensive: helper returns one of these two strings today.
        action = "updated"

    return GlossarySyncEntityResponse(
        glossary_entity_id=result["glossary_entity_id"],
        action=action,  # type: ignore[arg-type]
        canonical_name=result["canonical_name"],
    )
