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
    _WRITER_AUTOCREATE_CONFIG,
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


class HierarchyPathsPayload(BaseModel):
    """P3 D-P3-EXTRACTION-CALLER-WIRE-UP — wire shape of HierarchyPaths.

    Worker-ai resolves these from book-service's parts/chapters/scenes
    rows (or synthesises them for legacy chapters with no part_id).
    Mirrors `app.extraction.hierarchy_writer.HierarchyPaths` dataclass.
    """
    book_id: str = Field(min_length=1)
    book_path: str = Field(min_length=1)
    book_title: str | None = None
    part_id: str = Field(min_length=1)
    part_path: str = Field(min_length=1)
    part_index: int = Field(ge=1)
    part_title: str | None = None
    chapter_id: str = Field(min_length=1)
    chapter_path: str = Field(min_length=1)
    chapter_index: int = Field(ge=1)
    chapter_title: str | None = None
    # Scenes: list of [scene_id, scene_path, scene_index] tuples.
    scenes: list[tuple[str, str, int]] = Field(default_factory=list)


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

    P3 D-P3-EXTRACTION-CALLER-WIRE-UP — when ALL of `hierarchy_paths`,
    `embedding_model_uuid`, and `embedding_dimension` are supplied, the
    endpoint also MERGEs the Book→Part→Chapter→Scene hierarchy in the
    same Tx and enqueues a `summary.chapter` message. When
    `is_last_chapter_of_book=True`, additionally enqueues `summary.part`
    × N (one per `book_parts` entry) and `summary.book`. All P3 fields
    optional → legacy callers that omit them get the original behaviour
    unchanged.
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

    # P3 — caller supplies these to opt into hierarchy writes + summary enqueue.
    hierarchy_paths: HierarchyPathsPayload | None = None
    # book_parts only consumed when is_last_chapter_of_book=True. Each
    # entry: [part_id, part_path, part_index_as_string].
    book_parts: list[tuple[str, str, str]] = Field(default_factory=list)
    is_last_chapter_of_book: bool = False
    embedding_model_uuid: str | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    # B2 follow-up — per-project Pass2-writer Tier-B autocreate. None = use the
    # KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED env default (back-compat /
    # callers that don't resolve a per-project config). True/False = explicit
    # per-project override. NOTE: worker-ai always sends a resolved bool, so on
    # the worker path per-project config supersedes the env knob (and config_hash
    # stays accurate). The env knob still applies for callers that omit this.
    writer_autocreate: bool | None = None

    # CM5 — authorship provenance stamped on every node this persist writes.
    # Closed vocab aligned with enrichment H0. Default 'human_authored' (chapter
    # extraction); composition sends 'ai_assisted' for AI-generated prose. The
    # node accumulates the deduped set of origins (`provenances`).
    provenance: Literal["human_authored", "ai_assisted", "enrichment"] = "human_authored"


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

    # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — build the HierarchyPaths dataclass
    # for the writer when the caller opted into hierarchy mode. We do this
    # OUTSIDE the session so the dataclass construction can fail fast on
    # bad payloads without leaking a session.
    from app.extraction.hierarchy_writer import HierarchyPaths
    hierarchy_paths = None
    if body.hierarchy_paths is not None:
        hp = body.hierarchy_paths
        hierarchy_paths = HierarchyPaths(
            book_id=hp.book_id,
            book_path=hp.book_path,
            book_title=hp.book_title,
            part_id=hp.part_id,
            part_path=hp.part_path,
            part_index=hp.part_index,
            part_title=hp.part_title,
            chapter_id=hp.chapter_id,
            chapter_path=hp.chapter_path,
            chapter_index=hp.chapter_index,
            chapter_title=hp.chapter_title,
            scenes=list(hp.scenes),
        )

    # B2 follow-up — Pass2-writer Tier-B autocreate. Per-project override (sent
    # by worker-ai) wins; else the env default. Previously this endpoint never
    # passed the autocreate kwargs, so autocreate was DORMANT on the worker path
    # regardless of the env knob — this wires it (default env=off → unchanged).
    autocreate_enabled = (
        body.writer_autocreate
        if body.writer_autocreate is not None
        else _WRITER_AUTOCREATE_CONFIG["autocreate_enabled"]
    )

    async with neo4j_session() as session:
        # Canon Model CM3b (B6): retract THIS source's prior evidence BEFORE
        # re-writing. Re-extracting a chapter (e.g. re-publish) must drop facts
        # that disappeared from the new revision instead of leaving stale canon;
        # the writer below re-adds evidence for facts still present. First-time
        # extraction → 0 edges removed (no-op). Safe because the worker persists
        # ONCE per chapter (one source_id per call), not per-chunk.
        from app.db.neo4j_repos.provenance import remove_evidence_for_source
        await remove_evidence_for_source(
            session, user_id=str(body.user_id), source_id=body.source_id,
        )
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
            hierarchy_paths=hierarchy_paths,  # P3 D2a — Tx-bound hierarchy MERGE
            autocreate_enabled=autocreate_enabled,
            autocreate_max=_WRITER_AUTOCREATE_CONFIG["autocreate_max"],
            provenance=body.provenance,  # CM5
        )

    elapsed = time.perf_counter() - started

    # P3 — async summary enqueue. Fires only when caller wired all the P3
    # deps. Best-effort wrapper per `feedback_cross_store_best_effort_writes`
    # — Postgres + Neo4j writes already succeeded; an enqueue failure
    # mustn't 500 the caller (a later extraction or manual re-run can
    # re-enqueue). Logged for ops.
    if (
        hierarchy_paths is not None
        and body.embedding_model_uuid is not None
        and body.embedding_dimension is not None
    ):
        from app.extraction.pass2_orchestrator import (
            enqueue_chapter_and_maybe_book_summaries,
        )
        try:
            await enqueue_chapter_and_maybe_book_summaries(
                summary_enqueue=_get_summary_enqueue(),
                hierarchy_paths=hierarchy_paths,
                user_id=str(body.user_id),
                project_id=str(body.project_id) if body.project_id else "",
                job_id=str(body.job_id),
                model_ref=body.extraction_model,
                embedding_model_uuid=body.embedding_model_uuid,
                embedding_dimension=body.embedding_dimension,
                is_last_chapter_of_book=body.is_last_chapter_of_book,
                book_parts=list(body.book_parts),
            )
            logger.info(
                "P3: enqueued summaries for chapter source_id=%s "
                "(is_last=%s, book_parts=%d)",
                body.source_id, body.is_last_chapter_of_book,
                len(body.book_parts),
            )
        except Exception:
            logger.warning(
                "P3: summary enqueue failed source_id=%s (non-fatal)",
                body.source_id, exc_info=True,
            )
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


# ═══════════════════════════════════════════════════════════════════════
# P2 (hierarchical extraction T3) — cache invalidation endpoint (D5)
# Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D5
# ═══════════════════════════════════════════════════════════════════════


_VALID_INVALIDATE_OPS = {"entity", "relation", "event", "fact"}


class InvalidateCacheResponse(BaseModel):
    book_id: UUID
    invalidated_ops: list[str]
    deleted_leaves: int
    deleted_raw: int


@router.post(
    "/invalidate-cache/{book_id}",
    response_model=InvalidateCacheResponse,
    summary="P2 — invalidate extraction_leaves cache for one book",
    description=(
        "Explicit invalidation per PO choice 2. Triggered by parse_version "
        "bumps (P3 re-parse), extractor_version drift (prompt edits), or "
        "FE 'Rebuild Graph' button. Uses two-step CTE Tx (H2 fix) for "
        "accurate deleted_raw count — CASCADE delete doesn't surface via "
        "RETURNING."
    ),
)
async def invalidate_cache(
    book_id: UUID,
    op: str | None = None,
) -> InvalidateCacheResponse:
    # Validate optional op filter.
    if op is not None and op not in _VALID_INVALIDATE_OPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"op must be one of {sorted(_VALID_INVALIDATE_OPS)} or omitted",
        )
    target_ops = [op] if op else sorted(_VALID_INVALIDATE_OPS)

    from app.db.repositories.extraction_leaves import ExtractionLeavesRepo

    pool = get_knowledge_pool()
    repo = ExtractionLeavesRepo(pool)
    deleted_leaves, deleted_raw = await repo.delete_by_book(
        book_id=book_id, ops=target_ops,
    )

    logger.info(
        "p2 invalidate-cache book_id=%s ops=%s deleted_leaves=%d deleted_raw=%d",
        book_id, target_ops, deleted_leaves, deleted_raw,
    )
    return InvalidateCacheResponse(
        book_id=book_id,
        invalidated_ops=target_ops,
        deleted_leaves=deleted_leaves,
        deleted_raw=deleted_raw,
    )


# ── Q4b-feed: run-sample fetch for the online LLM judge ──────────────


class RunSampleResponse(BaseModel):
    """Wire shape of one `extraction_run_samples` row.

    `items` is the minimal judge-shape projection keyed by category
    ({entity:[{name,kind}], relation:[{subject,predicate,object,polarity}],
    event:[{summary,participants}]}). learning-service's eval-runner feeds
    `items` + `source_text` straight into `run_online_judge`.
    """
    run_id: str
    project_id: str | None = None
    book_id: str | None = None
    config_hash: str | None = None
    items: dict[str, list[dict]]
    source_text: str


@router.get(
    "/runs/{run_id}/sample",
    response_model=RunSampleResponse,
    summary="Q4b-feed — fetch the items+source sample for one extraction run",
    description=(
        "Returns the run-attributable extracted items + chapter source for "
        "an opted-in run (save_raw_extraction). 404 when no sample exists — "
        "the run's project didn't opt in, the run wasn't a SUCCEEDED chapter, "
        "or the 7-day TTL pruned it. Behind X-Internal-Token; called by "
        "learning-service's eval-runner for sampled runs."
    ),
)
async def get_run_sample(run_id: UUID) -> RunSampleResponse:
    from app.db.repositories.extraction_run_samples import (
        ExtractionRunSamplesRepo,
    )

    repo = ExtractionRunSamplesRepo(get_knowledge_pool())
    sample = await repo.fetch_sample(run_id)
    if sample is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no sample for this run (non-opted, not succeeded, or pruned)",
        )
    return RunSampleResponse(
        run_id=str(sample.run_id),
        project_id=str(sample.project_id) if sample.project_id else None,
        book_id=str(sample.book_id) if sample.book_id else None,
        config_hash=sample.config_hash,
        items=sample.items,
        source_text=sample.source_text,
    )


# ── P3 D-P3-WORKER-AI-CONSUMER-WIRING — summarize-message dispatch ────


class SummarizeMessageRequest(BaseModel):
    """Wire shape of `SummarizeMessage` from `app.jobs.summary_enqueue`.

    Fields mirror `SummarizeMessage.from_redis_fields`; worker-ai posts
    these after XREADGROUP without needing to import the dataclass.
    """
    level: Literal["chapter", "part", "book"]
    node_path: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    project_id: str = ""  # may be empty for legacy paths
    job_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    embedding_model_uuid: str = Field(min_length=1)
    embedding_dimension: int = Field(ge=1)
    retry_at_epoch: float = 0.0
    retried_n: int = 0


class SummarizeMessageResponse(BaseModel):
    """Mirror of `SummaryProcessResult`."""
    level: str
    node_id: str
    cache_hit: bool
    race_winner: bool
    re_enqueued: bool
    skipped_retry_exhausted: bool
    summary_id: str | None


# Module-level singleton — Redis client is reusable across all
# summarize-message dispatches and we want one connection pool.
_summary_enqueue_singleton = None


def _get_summary_enqueue():
    """Lazy-build the redis-backed enqueue function.

    Per `make_redis_summary_enqueue` — opens a long-lived async Redis
    connection on first use; subsequent calls reuse the same client.
    Used by `process_summarize_message` for M4 re-enqueue when D9
    defensive checks fail.
    """
    global _summary_enqueue_singleton
    if _summary_enqueue_singleton is None:
        from app.jobs.summary_enqueue import make_redis_summary_enqueue
        _summary_enqueue_singleton = make_redis_summary_enqueue(settings.redis_url)
    return _summary_enqueue_singleton


class _EmbeddingAdapter:
    """Bridges the real EmbeddingClient to the `embed(text, model_uuid)`
    shape `process_summarize_message` expects.

    `EmbeddingClient.embed` returns an `EmbeddingResult` (batched API).
    The summary processor calls one embed per summary and wants the
    vector list directly — this adapter unwraps and returns
    `embeddings[0]`.
    """

    def __init__(self, real, *, user_id: UUID) -> None:
        self._real = real
        self._user_id = user_id

    async def embed(self, *, text: str, model_uuid: str) -> list[float]:
        result = await self._real.embed(
            user_id=self._user_id,
            model_source="user_model",
            model_ref=model_uuid,
            texts=[text],
        )
        if not result.embeddings or not result.embeddings[0]:
            raise RuntimeError("embedding probe returned empty vector")
        return result.embeddings[0]


@router.post(
    "/summarize-message",
    response_model=SummarizeMessageResponse,
    summary="P3 — process one extraction.summarize stream message",
    description=(
        "Dispatch entrypoint for worker-ai's Redis Stream consumer "
        "(D-P3-WORKER-AI-CONSUMER-WIRING). Worker-ai XREADGROUPs "
        "`extraction.summarize`, posts the message body here, then "
        "XACKs on 200. Body shape mirrors "
        "`app.jobs.summary_enqueue.SummarizeMessage`."
    ),
)
async def process_summarize_message_endpoint(
    req: SummarizeMessageRequest,
) -> SummarizeMessageResponse:
    """Worker-ai consumer entrypoint.

    Builds `SummaryProcessorDeps` from the existing knowledge-service
    singletons (pool, neo4j session, llm_client, embedding_client +
    adapter) and delegates to `process_summarize_message`. The async
    `process_summarize_message` does all the heavy lifting (cache
    check, D9 defensive, LLM call, embed, Postgres + Neo4j writes,
    M4 re-enqueue).
    """
    from app.clients.embedding_client import get_embedding_client
    from app.clients.llm_client import get_llm_client
    from app.jobs.summary_enqueue import SummarizeMessage
    from app.jobs.summary_processor import (
        SummaryProcessorDeps,
        process_summarize_message,
    )

    msg = SummarizeMessage(
        level=req.level,
        node_path=req.node_path,
        node_id=req.node_id,
        book_id=req.book_id,
        user_id=req.user_id,
        project_id=req.project_id,
        job_id=req.job_id,
        model_ref=req.model_ref,
        embedding_model_uuid=req.embedding_model_uuid,
        embedding_dimension=req.embedding_dimension,
        retry_at_epoch=req.retry_at_epoch,
        retried_n=req.retried_n,
    )

    try:
        pool = get_knowledge_pool()
    except Exception as exc:
        logger.error("summarize-message: knowledge pool unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="knowledge storage is unavailable",
        ) from exc

    # Open a fresh Neo4j session per dispatch — `process_summarize_message`
    # does multiple session.run calls but treats them as a single logical
    # work unit; a per-call session matches the existing /persist-pass2
    # pattern and avoids leaking sessions across worker-ai requests.
    async with neo4j_session() as session:
        deps = SummaryProcessorDeps(
            knowledge_pool=pool,
            neo4j_session=session,
            llm_client=get_llm_client(),
            embedding_client=_EmbeddingAdapter(
                get_embedding_client(), user_id=UUID(req.user_id),
            ),
            summary_enqueue=_get_summary_enqueue(),
        )
        result = await process_summarize_message(msg, deps)

    return SummarizeMessageResponse(
        level=result.level,
        node_id=result.node_id,
        cache_hit=result.cache_hit,
        race_winner=result.race_winner,
        re_enqueued=result.re_enqueued,
        skipped_retry_exhausted=result.skipped_retry_exhausted,
        summary_id=str(result.summary_id) if result.summary_id else None,
    )
