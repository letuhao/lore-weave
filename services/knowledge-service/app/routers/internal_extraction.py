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
import os
import time
from typing import Literal
from uuid import UUID

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.default_model import resolve_user_default_model
from app.clients.glossary_client import get_glossary_client
from app.clients.llm_client import get_llm_client
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.deps import get_projects_repo
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.job_logs import JobLogsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.triage import TriageRepo
from app.extraction.model_roles import resolve_role_model
from loreweave_extraction import EntityRecoveryConfig
from app.ontology.extraction_projection import (
    build_extraction_schema,
    resolved_to_extraction_dict,
)
from app.extraction.anchor_loader import Anchor, load_glossary_anchors
from loreweave_extraction.schema_projection import ExtractionSchema
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
from app.extraction import coref_detect
from app.extraction.glossary_writeback import (
    WRITEBACK_CONFIG,
    should_writeback,
    writeback_discovered_entities,
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

    # FD-4 (066 fix): the chapter's reading-order ordinal (book-service
    # sort_order), threaded SEPARATELY from hierarchy_paths so a flat book
    # (chapters, no part) still gets a dense event_order for events/status.
    # ge=0 (not ge=1 like the part-gated HierarchyPathsPayload.chapter_index):
    # this field rides on EVERY part-less persist, so a hypothetical 0-based
    # sort_order must NOT 422 the whole persist — event_order=0*stride+idx is a
    # perfectly valid dense base (review-impl LOW#1).
    chapter_index: int | None = Field(default=None, ge=0)
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

    # E0-3 Phase 2a-2 — BYOK billing identity for the SUMMARY pipeline this
    # persist enqueues (the summary LLM + embed bill the collaborator). Empty ⇒
    # owner-triggered (legacy). The stored embedding_model_uuid tag stays the
    # project's; only the summary GENERATION refs/user swap to billing.
    billing_user_id: str = ""
    billing_llm_model: str = ""
    billing_embedding_model: str = ""

    # C12 — target-typed extraction. The job's chosen Pass-2 pass subset,
    # forwarded by worker-ai so this endpoint can gate the summary enqueue
    # on `summaries ∈ targets`. None ⇒ all passes (enqueue summaries as
    # before — back-compat for every caller that omits the field).
    targets: list[str] | None = None


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


# ── L7 activation — per-project resolved-schema cache for the write boundary ──
#
# /persist-pass2 resolves the project's effective KG schema and passes it to the
# Pass-2 writer so M3 schema_version stamping + the closed-edge guard + triage
# park go live. The resolve is a bounded Postgres read; a 100-chapter job would
# otherwise re-resolve per chapter. Cache the PROJECTED ExtractionSchema per
# (user_id, project_id) with a 30s TTL — long enough to collapse a bulk job's
# repeats, short enough that an adopt/sync is picked up almost immediately
# (matches OntologyResolver's own 30s design intent). Only successful resolves
# are cached; a transient failure degrades to "no schema this call" and is
# re-tried next call (not locked in for 30s). Per-process; empties on restart.
_SCHEMA_CACHE_TTL_S = 30.0
_SCHEMA_CACHE_MAX = 256
_schema_cache: TTLCache[tuple[str, str], ExtractionSchema] = TTLCache(
    maxsize=_SCHEMA_CACHE_MAX, ttl=_SCHEMA_CACHE_TTL_S,
)


async def _resolve_schema_for_persist(
    *, user_id: UUID, project_id: UUID | None,
) -> ExtractionSchema | None:
    """L7 activation — resolve the project's effective schema (AUTHORITATIVE) for
    the write boundary: the closed-edge guard + triage park + ``schema_version``
    stamp.

    Returns ``None`` for chat/global (no project) or on any resolution failure —
    extraction still persists, just without the stamp/guard this call (fail-soft,
    exactly like the anchor pre-load). Cached per ``(user_id, project_id)`` for
    30s.

    NOT advisory: carries the schema's real ``allow_free_edges`` so the writer is
    the SOLE closed-set enforce+park point. (The SDK extraction-prompt path uses
    ``advisory=True`` separately, so it injects vocab as a hint but never
    pre-drops — which would otherwise rob this park of the off-schema edge.)
    """
    if project_id is None:
        return None
    cache_key = (str(user_id), str(project_id))
    cached = _schema_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        repo = GraphSchemasRepo(get_knowledge_pool())
        resolved = await repo.resolve_for_project(str(project_id))
        schema = build_extraction_schema(resolved, advisory=False)
    except Exception:
        logger.warning(
            "L7: schema resolve failed for project=%s — persist will not stamp/"
            "enforce schema this call",
            project_id, exc_info=True,
        )
        return None  # don't cache failures
    _schema_cache[cache_key] = schema
    return schema


async def _resolve_schemas_for_extract_item(
    *, user_id: UUID, project_id: UUID | None,
) -> tuple[ExtractionSchema | None, ExtractionSchema | None]:
    """L7B (D-KG-L7B-EXTRACT-ITEM) — resolve the L7 schema SPLIT for the
    combined extract-then-write ``/extract-item`` path.

    Returns ``(advisory, authoritative)``:

      * **advisory** (``allow_free_edges`` forced True) → fed to the SDK
        extraction prompt as a vocab *hint* so it never pre-drops an off-vocab
        predicate (which would rob the write boundary's triage park of the edge);
      * **authoritative** (real ``allow_free_edges``) → handed to
        ``write_pass2_extraction`` so the closed-edge guard + ``schema_version``
        stamp + off-schema triage park go live there.

    Same posture split ``/persist-pass2`` (authoritative) + ``/resolve-schema``
    (advisory) use, but resolved ONCE here because this endpoint runs both the
    SDK extraction AND the write in a single in-process pipeline.

    Returns ``(None, None)`` for chat/global (no project) or on any resolution
    failure — extraction still persists, just with the static prompt + no
    stamp/guard this call (fail-soft, exactly like the anchor pre-load and
    ``_resolve_schema_for_persist``). The general fallback = today's behavior.
    """
    if project_id is None:
        return (None, None)
    try:
        repo = GraphSchemasRepo(get_knowledge_pool())
        resolved = await repo.resolve_for_project(str(project_id))
        advisory = build_extraction_schema(resolved, advisory=True)
        authoritative = build_extraction_schema(resolved, advisory=False)
    except Exception:
        logger.warning(
            "L7B: schema resolve failed for project=%s — extract-item will use "
            "the static prompt + no stamp/guard this call",
            project_id, exc_info=True,
        )
        return (None, None)
    return (advisory, authoritative)


_ER_ENV_REF = "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF"
_ER_ENV_SOURCE = "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE"
_ER_ENV_MAX_BATCH = "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MAX_BATCH"


async def _resolve_entity_recovery_config(
    *, user_id: str, project_id: str | None,
    job_model_source: str, job_model_ref: str,
) -> EntityRecoveryConfig | None:
    """KN model-roles — resolve THIS job's entity-recovery config per-project.

    Enablement (opt-in — recovery is an optional refinement, NOT on-by-default):
      * `extraction_config.entity_recovery.enabled == True` → on (per-project)
      * else the legacy env floor (`KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF`
        set) → on (back-compat)
      * else → OFF (returns None → byte-identical to pre-KN behavior when nothing
        is configured).

    When ON, the MODEL resolves via the precedence chain (resolve_role_model):
    role override (`entity_recovery.model_ref`) → project default (THIS job's
    extraction model — already the resolved `llm_model`) → user-global default
    (`chat` capability) → env floor. Fail-soft: any read failure degrades to the
    env config / off (never blocks extraction).
    """
    env_ref = (os.environ.get(_ER_ENV_REF, "") or "").strip()
    extraction_config: dict = {}
    if project_id:
        try:
            repo = ProjectsRepo(get_knowledge_pool())
            proj = await repo.get(UUID(user_id), UUID(project_id))
            extraction_config = (proj.extraction_config or {}) if proj else {}
        except Exception:
            logger.debug(
                "entity_recovery: extraction_config read failed (advisory)",
                exc_info=True,
            )
    er_cfg = extraction_config.get("entity_recovery") or {}
    enabled = er_cfg.get("enabled") if isinstance(er_cfg, dict) else None
    if enabled is False:
        return None
    env_source = os.environ.get(_ER_ENV_SOURCE) or "user_model"

    if enabled is True:
        # Per-project OPT-IN → the precedence chain (role override → project
        # default → user-global → env floor). Project default = the persisted
        # `extraction_config.llm_model` (the FE "Default LLM" picker) when set,
        # else THIS job's extraction model (so recovery matches extraction by
        # default rather than diverging to a different model).
        user_default = await resolve_user_default_model(user_id)
        synthetic = dict(extraction_config)
        if not synthetic.get("llm_model"):
            synthetic["llm_model"] = job_model_ref
            synthetic["llm_model_source"] = job_model_source
        resolved = resolve_role_model(
            synthetic, "entity_recovery",
            user_default_ref=user_default,
            env_source=env_source,
            env_ref=(env_ref or None),
        )
    elif env_ref:
        # Legacy env-only floor (NOT opted-in per-project) → use the env model
        # EXACTLY as before, without substituting the job's extraction model.
        from app.extraction.model_roles import RoleModel
        resolved = RoleModel(env_source, env_ref)
    else:
        return None  # not opted-in per-project, no env floor → off
    if resolved is None:
        return None

    # max batch: per-project override → env → default 5.
    raw_batch = er_cfg.get("max_items_per_batch") if isinstance(er_cfg, dict) else None
    if raw_batch is None:
        raw_batch = (os.environ.get(_ER_ENV_MAX_BATCH, "5") or "5").strip()
    try:
        max_batch = max(1, int(raw_batch))
    except (ValueError, TypeError):
        max_batch = 5
    return EntityRecoveryConfig(
        model_ref=resolved.model_ref,
        model_source=resolved.model_source,  # type: ignore[arg-type]
        max_items_per_batch=max_batch,
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

    # L7B (D-KG-L7B-EXTRACT-ITEM) — resolve the L7 schema SPLIT internally so
    # this endpoint gets the same ontology customization /persist-pass2 has,
    # WITHOUT changing the cross-service contract (composition-service C27 sends
    # no schema field). The advisory schema feeds the SDK extraction prompt as a
    # vocab hint; the authoritative schema + triage_repo go to the writer for the
    # closed-edge guard + off-schema park + schema_version stamp. Both None
    # (chat/global or resolve failure) → general fallback (today's behavior).
    advisory_schema, write_schema = await _resolve_schemas_for_extract_item(
        user_id=body.user_id, project_id=body.project_id,
    )
    # Best-effort like the JobLogsRepo producer above: if the pool isn't
    # initialised (unit tests that only mock the extractor helpers), triage_repo
    # stays None — the writer only parks inside the closed-edge guard (which needs
    # a resolved authoritative schema), so None never changes behavior for a
    # free-edge/None schema.
    try:
        triage_repo: TriageRepo | None = TriageRepo(get_knowledge_pool())
    except Exception:
        triage_repo = None

    # KN model-roles — resolve THIS job's entity-recovery config (per-project
    # opt-in + model precedence). None ⇒ off / env floor (byte-identical today).
    entity_recovery_override = await _resolve_entity_recovery_config(
        user_id=str(body.user_id),
        project_id=str(body.project_id) if body.project_id else None,
        job_model_source=body.model_source,
        job_model_ref=body.model_ref,
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
                    schema=advisory_schema,  # L7B — advisory vocab hint for SDK
                    write_schema=write_schema,  # L7B — authoritative write guard
                    triage_repo=triage_repo,  # L7B — park off-schema edges
                    entity_recovery_override=entity_recovery_override,  # KN model-roles
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
                    schema=advisory_schema,  # L7B — advisory vocab hint for SDK
                    write_schema=write_schema,  # L7B — authoritative write guard
                    triage_repo=triage_repo,  # L7B — park off-schema edges
                    entity_recovery_override=entity_recovery_override,  # KN model-roles
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

    project_id_str = str(body.project_id) if body.project_id else None

    # PP-5 (spec 08 R7) — resolve WORK mode: an assistant/diary project's facts must not carry durable
    # behavioral-TRAIT (`preference`) claims about real colleagues. One cheap PG read per persist (this
    # is per-extraction-item, not a hot per-token path); default False (novel/global) on any miss so the
    # fiction path is unchanged. The writer coerces preference→statement when this is True.
    #
    # DEFENSE-IN-DEPTH (review H2): the PRIMARY R7 guarantee is upstream — `queue_diary_facts` writes
    # every distilled diary fact as `fact_type='statement'` (never a preference), and per-turn chat
    # extraction is gated OFF for `is_assistant` projects (`may_extract_chat_turn`), so a diary fact
    # never reaches this writer today. PP-5 here is a fail-safe for the future case where an assistant
    # project's CHAPTERS are chapter-extracted, or per-turn work-capture is ever enabled — so a
    # `preference` can never slip in via this path either. It defaults False (fail-open is acceptable
    # BECAUSE the primary guard is elsewhere; failing closed here would over-coerce every novel's
    # preferences on a transient DB blip).
    work_mode = False
    if body.project_id is not None:
        try:
            work_mode = bool(await get_knowledge_pool().fetchval(
                "SELECT is_assistant FROM knowledge_projects WHERE project_id=$1", body.project_id,
            ))
        except Exception:  # noqa: BLE001 — a resolution failure must not fail the extraction; fail to novel-mode.
            logger.warning("persist_pass2: PP-5 is_assistant resolve failed; defaulting work_mode=False", exc_info=True)

    # L7 activation — resolve the project's effective KG schema for the write
    # boundary. None (chat/global, or resolve failure) → today's behavior (no
    # stamp/guard). When present, the writer stamps schema_version on every edge
    # (M3) and, for a project that CLOSES its edge set, drops + parks off-schema
    # edges to triage. The TriageRepo is always wired (cheap); the writer only
    # parks inside the closed-edge guard, so a free-edge/None schema never parks.
    schema = await _resolve_schema_for_persist(
        user_id=body.user_id, project_id=body.project_id,
    )
    # Best-effort like the JobLogsRepo producer below: if the pool isn't
    # initialised (unit tests that only mock the writer), triage_repo=None — the
    # writer only parks inside the closed-edge guard (which needs a resolved
    # schema), so None never changes behavior for a free-edge/None schema.
    try:
        triage_repo: TriageRepo | None = TriageRepo(get_knowledge_pool())
    except Exception:
        triage_repo = None

    async with neo4j_session() as session:
        # Canon Model CM3b (B6): retract THIS source's prior evidence BEFORE
        # re-writing. Re-extracting a chapter (e.g. re-publish) must drop facts
        # that disappeared from the new revision instead of leaving stale canon;
        # the writer below re-adds evidence for facts still present. First-time
        # extraction → 0 edges removed (no-op). Safe because the worker persists
        # ONCE per chapter (one source_id per call), not per-chunk.
        #
        # CM3b-RETRACT-FIX: use the NATURAL-KEY retract. The prior call passed
        # the raw `source_id` to `remove_evidence_for_source`, which matches the
        # HASHED ExtractionSource id — so it removed ZERO edges and the retract
        # was a silent no-op (canon drifted on every re-publish). The natural-key
        # helper hashes (user, project, source_type, source_id) the same way
        # `upsert_extraction_source` did at write time.
        from app.db.neo4j_repos.provenance import (
            cleanup_zero_evidence_nodes,
            remove_evidence_for_natural_key,
        )
        removed = await remove_evidence_for_natural_key(
            session,
            user_id=str(body.user_id),
            project_id=project_id_str,
            source_type=body.source_type,
            source_id=body.source_id,
        )
        result = await write_pass2_extraction(
            session,
            user_id=str(body.user_id),
            project_id=project_id_str,
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
            chapter_index=body.chapter_index,  # FD-4 (066) — event_order for flat books
            autocreate_enabled=autocreate_enabled,
            autocreate_max=_WRITER_AUTOCREATE_CONFIG["autocreate_max"],
            provenance=body.provenance,  # CM5
            schema=schema,  # L7 — schema_version stamp + closed-edge guard
            triage_repo=triage_repo,  # L7/C4 — park off-schema edge drops
            work_mode=work_mode,  # PP-5 — coerce preference→statement in an assistant/diary project
        )
        # CM3b-RETRACT-FIX: after re-writing, sweep nodes whose evidence the
        # retract dropped to zero (disappeared from the new revision) — this
        # completes retract-before-reextract. Gated on `removed > 0` so a
        # first-time extraction (nothing retracted) skips the O(project) sweep,
        # and so the cleanup only runs on genuine re-extractions. Safe per the
        # one-active-job-per-project invariant (K17.9): the write above already
        # re-added evidence for every surviving node, so only truly-orphaned
        # nodes are at zero here.
        if removed > 0:
            swept = await cleanup_zero_evidence_nodes(
                session, user_id=str(body.user_id), project_id=project_id_str,
            )
            if swept.total:
                logger.info(
                    "CM3b-RETRACT-FIX: persist-pass2 swept zero-evidence orphans "
                    "source_id=%s entities=%d events=%d facts=%d",
                    body.source_id, swept.entities, swept.events, swept.facts,
                )
            # F3 (§12.3.3 step B.3.5, A3) — re-stitch the story-time interval
            # chains after the retract. A swept fact/relation leaves its
            # predecessor's valid_to_ordinal dangling at the now-deleted
            # instance's valid_from_ordinal (an as-of read between them would
            # return nothing). Re-running the ordinal-aware chain-maintenance over
            # the survivors re-extends each predecessor to the next surviving
            # instance, so retract auto-restitches and never leaves a dangling
            # close. Gated on removed > 0 (same as the sweep) so it stays off the
            # first-extract hot path. Best-effort: a re-stitch failure must not
            # 500 a successful write — the repair job is the INV-FACTS backstop.
            try:
                from app.db.neo4j_repos.temporal import (
                    restitch_chains_after_retract,
                )
                restitched = await restitch_chains_after_retract(
                    session,
                    user_id=str(body.user_id),
                    project_id=project_id_str,
                )
                if restitched:
                    logger.info(
                        "F3-RESTITCH: persist-pass2 re-derived %d story-time "
                        "interval(s) after retract source_id=%s",
                        restitched, body.source_id,
                    )
            except Exception:
                logger.warning(
                    "F3-RESTITCH: chain re-stitch after retract failed "
                    "(non-fatal) source_id=%s",
                    body.source_id, exc_info=True,
                )

    elapsed = time.perf_counter() - started

    # P3 — async summary enqueue. Fires only when caller wired all the P3
    # deps. Best-effort wrapper per `feedback_cross_store_best_effort_writes`
    # — Postgres + Neo4j writes already succeeded; an enqueue failure
    # mustn't 500 the caller (a later extraction or manual re-run can
    # re-enqueue). Logged for ops.
    # C12 — gate the summary enqueue on `summaries ∈ targets`. None ⇒ all ⇒
    # enqueue (back-compat). A target list WITHOUT `summaries` skips it.
    summaries_requested = body.targets is None or "summaries" in body.targets
    if (
        summaries_requested
        and hierarchy_paths is not None
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
                billing_user_id=body.billing_user_id,
                billing_llm_model=body.billing_llm_model,
                billing_embedding_model=body.billing_embedding_model,
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
    elif summaries_requested:
        # D-KG-SUMMARIES-TARGET-NOOP — de-silence: summaries were requested but
        # a P3 dep was missing so NO summary enqueued. Previously invisible;
        # now diagnosable ([[silent-success-is-a-bug-not-environment]]). The
        # caller (worker-ai) also logs, but this covers direct callers.
        logger.warning(
            "P3: summary enqueue SKIPPED source_id=%s: "
            "hierarchy_paths=%s embedding_model_uuid=%s embedding_dimension=%s "
            "— no chapter summary generated",
            body.source_id,
            hierarchy_paths is not None,
            body.embedding_model_uuid is not None,
            body.embedding_dimension is not None,
        )
    logger.info(
        "Phase 4b-β: persist-pass2 done source_id=%s "
        "entities=%d relations=%d events=%d facts=%d statuses=%d in %.1fs",
        body.source_id,
        result.entities_merged, result.relations_created,
        result.events_merged, result.facts_merged,
        result.statuses_merged, elapsed,
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
                "statuses_merged": result.statuses_merged,  # A2-S1b
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

    # Mui #1 — KG→glossary writeback. Propose discovered, unanchored,
    # sufficiently-confident entities back to the glossary SSOT as
    # ai-suggested drafts for human review. Best-effort: the canon writes
    # (Neo4j + Postgres) already succeeded above, so a writeback failure
    # must not 500 the worker (the next job re-proposes; glossary dedups by
    # name + tombstone). Default OFF; enabled per-env per ADJ-1.
    #
    # Fires ONCE per extraction job, at the last chapter of the book — NOT
    # per chapter. find_gap_candidates scans the whole project, so running it
    # on every persist-pass2 would re-propose the entire gap list each chapter
    # (an entity_updated event storm; the "lãng phí" this loop exists to kill).
    # `is_last_chapter_of_book` is the same end-of-book signal the P3 summary
    # enqueue above uses. (review-impl HIGH-1 2026-06-07.)
    if should_writeback(
        enabled=WRITEBACK_CONFIG["enabled"],
        project_id=body.project_id,
        is_last_chapter_of_book=body.is_last_chapter_of_book,
    ):
        try:
            async with get_knowledge_pool().acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT book_id FROM knowledge_projects "
                    "WHERE project_id = $1 AND user_id = $2",
                    body.project_id, body.user_id,
                )
            wb_book_id = row["book_id"] if row else None
            if wb_book_id is not None:
                async with neo4j_session() as wb_session:
                    proposed = await writeback_discovered_entities(
                        wb_session,
                        get_glossary_client(),
                        user_id=str(body.user_id),
                        project_id=str(body.project_id),
                        book_id=wb_book_id,
                    )
                logger.info(
                    "mui#1 writeback: proposed %d entities to glossary "
                    "book=%s (source_id=%s)",
                    proposed, wb_book_id, body.source_id,
                )
        except Exception:
            logger.warning(
                "mui#1 writeback failed source_id=%s (non-fatal)",
                body.source_id, exc_info=True,
            )

    # mui #1c K-detect — opt-in auto coref pass at end-of-book (default OFF;
    # PO-locked 2026-06-07). Same end-of-book gate as writeback so a detect
    # pass runs once per job, not per chapter. Best-effort: proposes merge
    # candidates to glossary for human review; never merges, never 500s.
    if (
        settings.coref_auto_on_extraction
        and body.is_last_chapter_of_book
        and body.project_id is not None
    ):
        try:
            async with get_knowledge_pool().acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT book_id FROM knowledge_projects "
                    "WHERE project_id = $1 AND user_id = $2",
                    body.project_id, body.user_id,
                )
            cd_book_id = row["book_id"] if row else None
            if cd_book_id is not None:
                uid, pid = str(body.user_id), str(body.project_id)
                async with neo4j_session() as cd_session:
                    kinds = await coref_detect.load_anchored_kinds(
                        cd_session, user_id=uid, project_id=pid
                    )
                    if kinds:
                        cd_result = await coref_detect.detect_and_propose(
                            session=cd_session,
                            glossary=get_glossary_client(),
                            llm=get_llm_client(),
                            user_id=uid,
                            project_id=pid,
                            book_id=cd_book_id,
                            kinds=kinds,
                            score_floor=settings.coref_score_floor,
                            name_weight=settings.coref_name_weight,
                            struct_weight=settings.coref_struct_weight,
                            max_pairs=settings.coref_max_pairs,
                            max_bucket=settings.coref_max_bucket,
                            max_candidates_per_kind=settings.coref_max_candidates_per_kind,
                            min_mentions=settings.coref_min_mentions,
                            llm_verify=settings.coref_llm_verify,
                            judge_model=settings.coref_judge_model,
                            judge_user=settings.coref_judge_user,
                            judge_model_source=settings.coref_judge_model_source,
                        )
                        logger.info(
                            "mui#1c auto coref: %d clusters, %d proposed book=%s",
                            cd_result.clusters_found, cd_result.proposed, cd_book_id,
                        )
        except Exception:
            logger.warning(
                "mui#1c auto coref failed source_id=%s (non-fatal)",
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


# ── L7 activation (Milestone B) — resolve the advisory extraction schema ──────


class ResolveSchemaRequest(BaseModel):
    user_id: UUID
    project_id: UUID | None = None


class ResolveSchemaResponse(BaseModel):
    """The ADVISORY extraction-prompt projection of a project's resolved KG schema.

    `allow_free_edges` is forced True so worker-ai's SDK injects the vocab as a
    prompt *hint* but never pre-drops an off-vocab predicate — the write boundary
    (/persist-pass2, Milestone A) resolves the AUTHORITATIVE schema server-side and
    stays the sole closed-set enforce+park point (the R3 pre-drop reconciliation).

    `has_schema=False` ⇒ no project / resolve failure ⇒ worker-ai passes
    `schema=None` (today's static prompt behavior)."""

    has_schema: bool
    entity_kinds: list[str] = []
    edge_predicates: list[str] = []
    event_kinds: list[str] = []
    fact_types: list[str] = []
    allow_free_edges: bool = True
    label: str = ""
    schema_version: int | None = None


@router.post(
    "/resolve-schema",
    response_model=ResolveSchemaResponse,
    status_code=status.HTTP_200_OK,
    summary="L7 — resolve a project's advisory extraction-schema projection",
    description=(
        "Worker-ai calls this ONCE per job at start to get the project's KG vocab "
        "for the extraction prompt. Returns the ADVISORY projection "
        "(allow_free_edges forced True → hint, never pre-drop); /persist-pass2 is "
        "the authoritative enforce+park point. Behind X-Internal-Token. Degrades "
        "to has_schema=False (no project / resolve error) → static prompt."
    ),
)
async def resolve_extraction_schema(
    body: ResolveSchemaRequest,
) -> ResolveSchemaResponse:
    if body.project_id is None:
        return ResolveSchemaResponse(has_schema=False)
    try:
        repo = GraphSchemasRepo(get_knowledge_pool())
        resolved = await repo.resolve_for_project(str(body.project_id))
        d = resolved_to_extraction_dict(resolved, advisory=True)
    except Exception:
        logger.warning(
            "L7: resolve-schema failed for project=%s — worker-ai will use the "
            "static prompt this job",
            body.project_id, exc_info=True,
        )
        return ResolveSchemaResponse(has_schema=False)
    return ResolveSchemaResponse(
        has_schema=True,
        entity_kinds=d["entity_kinds"],
        edge_predicates=d["edge_predicates"],
        event_kinds=d["event_kinds"],
        fact_types=d["fact_types"],
        allow_free_edges=d["allow_free_edges"],
        label=d["label"],
        schema_version=d["schema_version"],
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
    # E0-3 Phase 2a-2 — BYOK caller-pays. Empty ⇒ owner-triggered (legacy). When
    # set, the summary LLM + embed resolve under the caller; the stored
    # embedding_model_uuid tag stays the project's.
    billing_user_id: str = ""
    billing_llm_model: str = ""
    billing_embedding_model: str = ""


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
        billing_user_id=req.billing_user_id,
        billing_llm_model=req.billing_llm_model,
        billing_embedding_model=req.billing_embedding_model,
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
            # E0-3 2a-2: bind the embed provider call to the billing user when a
            # collaborator triggered the extraction (gated on billing_user_id —
            # the identity, not a ref alone). summary_processor passes the
            # billing embedding ref as model_uuid; the two stay coherent.
            embedding_client=_EmbeddingAdapter(
                get_embedding_client(),
                user_id=UUID(req.billing_user_id or req.user_id),
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


# ── D-W8-MOTIF-BEAT-EXTRACTOR — motif-beat sequences (Option A) ────────
#
# Server side of composition-service's frozen `get_motif_beat_sequences`
# client (app/clients/knowledge_client.py). The miner (narrative-pattern-
# library W8) consumes ORDERED beat sequences as its PrefixSpan input.
#
# Option A: derive the sequences from the EXISTING extracted `:Event`
# timeline (event_order axis) — deterministic, no new LLM call. Each event
# → a {beat, thread, tension, role_mentions} step; one sequence per book.
# The LLM-quality `motif_beat` map-extractor (spec §12.4) is the follow-up
# (D-W8-MOTIF-BEAT-LLM-EXTRACTOR); until then this rides the event data and
# the composition client degrades on [] for any book without events.


class MotifBeatsRequest(BaseModel):
    """Frozen wire shape — mirrors knowledge_client.get_motif_beat_sequences:
    `{user_id, book_id?, corpus?, language?, extractor_version?}`."""

    user_id: UUID
    book_id: UUID | None = None
    corpus: bool = False
    language: str | None = None
    # The composition client sends its `motif_mine_extractor_version`
    # ("motif_beat@v1") so a future cache/version axis can key on it. Option A
    # is deterministic over event data, so we accept + echo it but don't branch
    # on it yet (the LLM extractor follow-up will).
    extractor_version: str | None = None


class MotifBeatStep(BaseModel):
    """One ordered beat step. Frozen field names — the composition miner reads
    exactly these keys (knowledge_client.py L218/L266)."""

    beat: str
    thread: str
    # ADDITIVE (D-W10-ARC-CONFORMANCE-THREAD-TAG): the classifier-assigned narrative thread
    # (combat/romance/…), "" until tagged. `thread` stays the chapter axis; this is orthogonal.
    narrative_thread: str = ""
    # ADDITIVE (D-W10-ARC-CONFORMANCE-SUCCESSION): the realized arc-placement motif code, "" until tagged.
    realized_motif_code: str = ""
    tension: int
    role_mentions: list[str] = Field(default_factory=list)


class MotifBeatsResponse(BaseModel):
    """A LIST of beat sequences, one per book/chapter container, each an
    `event_order`-ordered list of steps. Empty/absent corpus → `[]` (the
    composition client degrades cleanly on the empty list)."""

    sequences: list[list[MotifBeatStep]] = Field(default_factory=list)


@router.post(
    "/motif-beats",
    response_model=MotifBeatsResponse,
    status_code=status.HTTP_200_OK,
    summary="W8 — derive ordered motif-beat sequences from the event timeline",
    description=(
        "Option A motif-beat source for the composition-side miner. Returns "
        "`event_order`-ordered `{beat, thread, tension, role_mentions}` "
        "sequences (one per book), derived deterministically from the extracted "
        ":Event timeline — no LLM call. Scoped to `user_id` (a cross-user book → "
        "[]). Behind X-Internal-Token. An empty/absent corpus → `{sequences: []}`."
    ),
)
async def motif_beats(body: MotifBeatsRequest) -> MotifBeatsResponse:
    """Derive motif-beat sequences for the composition miner (W8).

    Needs Neo4j (the :Event timeline lives there). With Neo4j unconfigured we
    return an empty list rather than 503 — the composition client treats any
    non-success as the deferred-extractor degrade path, and `{sequences: []}`
    is the cleaner, contract-shaped equivalent (mining reports
    `mined: 0` instead of erroring)."""
    if not settings.neo4j_uri:
        logger.info("motif-beats: Neo4j not configured — returning empty sequences")
        return MotifBeatsResponse(sequences=[])

    from app.extraction.motif_beat import derive_motif_beat_sequences

    raw_sequences = await derive_motif_beat_sequences(
        user_id=body.user_id,
        book_id=body.book_id,
        corpus=body.corpus,
        language=body.language,
    )
    # raw_sequences is list[list[dict]] in the frozen shape; Pydantic validates
    # each step into MotifBeatStep (a field-name mismatch would 422 here, which
    # is the contract guard we want).
    return MotifBeatsResponse(sequences=raw_sequences)  # type: ignore[arg-type]


# ── D-W10-ARC-CONFORMANCE-THREAD-TAG — narrative-thread classifier ─────


def _neutralize_event_dicts(events: list, *, project_id: str) -> list[dict]:
    """Build the classifier event dicts with extracted prose neutralized
    (D-EXTRACTOR-PROMPT-INJECTION). The tag classifiers embed each event's title/summary/
    participants into an LLM prompt; this passes them through the knowledge-service injection
    defense first so a planted instruction in the source text is tagged, not obeyed. Output is
    still vocab/id-validated downstream, so this is defense-in-depth, not the only guard."""
    from app.extraction.injection_defense import neutralize_injection

    def _clean(text: str) -> str:
        return neutralize_injection(text or "", project_id=project_id)[0]

    out = []
    for e in events:
        out.append({
            "id": e.id,
            "title": _clean(e.title),
            "summary": _clean(e.summary),
            "participants": [_clean(p) for p in (e.participants or [])],
        })
    return out


def _neutralize_motif_vocab(motifs: list[dict]) -> list[dict]:
    """Neutralize the catalog-vocab name/summary before they enter the classifier prompt
    (D-EXTRACTOR-PROMPT-INJECTION). UNLIKE the arc placements tag-motifs uses (the caller's
    OWN authored motifs), the tag-beats mining catalog includes OTHER users' PUBLIC motifs
    (list_for_caller scope='all'), whose name/summary are attacker-controllable free text — so
    a planted instruction in a public motif must be tagged, not obeyed, when another tenant
    mines. The `code` is NOT touched: it is the controlled answer-key (validated against the
    same vocab downstream), never free prose. Defense-in-depth — output is still code-validated."""
    from app.extraction.injection_defense import neutralize_injection

    def _clean(text) -> str:
        return neutralize_injection(str(text or ""), project_id="motif-catalog")[0]

    out = []
    for m in motifs:
        if not m.get("code"):
            continue
        out.append({"code": m["code"], "name": _clean(m.get("name")),
                    "summary": _clean(m.get("summary"))})
    return out


class TagThreadsRequest(BaseModel):
    """Tag a book's :Event timeline with narrative-thread labels from the caller's
    vocabulary (the arc template's threads). model_source/model_ref resolve the BYOK
    classify model (provider-gateway invariant — composition resolves it, passes it here)."""

    user_id: UUID
    book_id: UUID
    threads: list[dict] = Field(default_factory=list)   # [{key, label?}]
    model_source: str
    model_ref: str


class TagThreadsResponse(BaseModel):
    tagged: int = 0                       # events whose narrative_thread was written
    events_seen: int = 0                  # events considered
    threads_assigned: dict[str, int] = Field(default_factory=dict)  # thread_key → count


@router.post(
    "/tag-threads",
    response_model=TagThreadsResponse,
    status_code=status.HTTP_200_OK,
    summary="Tag :Event nodes with narrative-thread labels (deep arc-conformance)",
    description=(
        "Classifies each :Event (title+summary+participants) into one of the caller's "
        "thread keys via an LLM (operation=chat → provider-registry), persisting "
        ":Event.narrative_thread so motif-beats emits real threads. ADVISORY / "
        "uncalibrated; degrades to a partial/empty tag on any LLM failure. X-Internal-Token."
    ),
)
async def tag_threads(body: TagThreadsRequest) -> TagThreadsResponse:
    if not settings.neo4j_uri:
        logger.info("tag-threads: Neo4j not configured — no-op")
        return TagThreadsResponse()

    from app.db.neo4j_repos.events import list_events_in_order, set_narrative_threads
    from app.extraction.motif_beat import _list_user_book_projects
    from app.extraction.thread_tag import classify_event_threads

    valid = [t for t in body.threads if t.get("key")]
    if not valid:
        return TagThreadsResponse()

    llm = get_llm_client()
    containers = await _list_user_book_projects(body.user_id, body.book_id, corpus=False)
    seen = 0
    tagged = 0
    counts: dict[str, int] = {}
    async with neo4j_session() as session:
        for project_id, _book_id in containers:
            events = await list_events_in_order(
                session, user_id=str(body.user_id), project_id=str(project_id), limit=2000)
            if not events:
                continue
            seen += len(events)
            ev_dicts = _neutralize_event_dicts(events, project_id=str(project_id))
            assignments = await classify_event_threads(
                llm, user_id=str(body.user_id), model_source=body.model_source,
                model_ref=body.model_ref, events=ev_dicts, threads=valid)
            # Pass the full considered scope so a stale tag on an event the classifier no
            # longer picks is cleared, not left to pollute deep conformance (retag-stale).
            tagged += await set_narrative_threads(
                session, user_id=str(body.user_id), assignments=assignments,
                event_ids={e["id"] for e in ev_dicts})
            for th in assignments.values():
                counts[th] = counts.get(th, 0) + 1
    return TagThreadsResponse(tagged=tagged, events_seen=seen, threads_assigned=counts)


# ── D-W10-ARC-CONFORMANCE-SUCCESSION — realized-motif classifier ───────


class TagMotifsRequest(BaseModel):
    """Tag a book's :Event timeline with the arc-placement motif each event realizes (by
    code). model_source/model_ref resolve the BYOK classify model (provider-gateway invariant)."""

    user_id: UUID
    book_id: UUID
    motifs: list[dict] = Field(default_factory=list)   # [{code, name?, summary?}]
    model_source: str
    model_ref: str


class TagMotifsResponse(BaseModel):
    tagged: int = 0
    events_seen: int = 0
    motifs_assigned: dict[str, int] = Field(default_factory=dict)   # motif_code → count


@router.post(
    "/tag-motifs",
    response_model=TagMotifsResponse,
    status_code=status.HTTP_200_OK,
    summary="Tag :Event nodes with the arc-placement motif they realize (deep succession)",
    description=(
        "Classifies each :Event (title+summary+participants) into one of the arc's placement "
        "motif codes via an LLM (operation=chat → provider-registry), persisting "
        ":Event.realized_motif_code so motif-beats emits the realized motif order. ADVISORY / "
        "uncalibrated; degrades to a partial/empty tag on any LLM failure. X-Internal-Token."
    ),
)
async def tag_motifs(body: TagMotifsRequest) -> TagMotifsResponse:
    if not settings.neo4j_uri:
        logger.info("tag-motifs: Neo4j not configured — no-op")
        return TagMotifsResponse()

    from app.db.neo4j_repos.events import list_events_in_order, set_realized_motifs
    from app.extraction.motif_beat import _list_user_book_projects
    from app.extraction.motif_tag import classify_event_motifs

    valid = [m for m in body.motifs if m.get("code")]
    if not valid:
        return TagMotifsResponse()

    llm = get_llm_client()
    containers = await _list_user_book_projects(body.user_id, body.book_id, corpus=False)
    seen = 0
    tagged = 0
    counts: dict[str, int] = {}
    async with neo4j_session() as session:
        for project_id, _book_id in containers:
            events = await list_events_in_order(
                session, user_id=str(body.user_id), project_id=str(project_id), limit=2000)
            if not events:
                continue
            seen += len(events)
            ev_dicts = _neutralize_event_dicts(events, project_id=str(project_id))
            assignments = await classify_event_motifs(
                llm, user_id=str(body.user_id), model_source=body.model_source,
                model_ref=body.model_ref, events=ev_dicts, motifs=valid)
            # Clear a stale realized_motif_code on any considered event left unassigned.
            tagged += await set_realized_motifs(
                session, user_id=str(body.user_id), assignments=assignments,
                event_ids={e["id"] for e in ev_dicts})
            for code in assignments.values():
                counts[code] = counts.get(code, 0) + 1
    return TagMotifsResponse(tagged=tagged, events_seen=seen, motifs_assigned=counts)


# ── D-W8-MOTIF-BEAT-LLM-EXTRACTOR — catalog-motif classifier (mining source) ────


class TagBeatsRequest(BaseModel):
    """Tag a book's (or the whole corpus's) :Event timeline with the catalog motif each event
    most embodies (by code), classified against the user's VISIBLE motif catalog — NOT an arc.
    Persists :Event.mined_motif_code so a subsequent motif-beats read emits GENERIC beat/thread
    axes (namespace:local) and corpus PrefixSpan mines reusable motif-sequences. model_source/
    model_ref resolve the BYOK classify model (provider-gateway invariant — composition resolves
    the user's pick and passes it here; NO platform model literal)."""

    user_id: UUID
    book_id: UUID | None = None
    corpus: bool = False
    motifs: list[dict] = Field(default_factory=list)   # [{code, name?, summary?}] — the catalog
    model_source: str
    model_ref: str


class TagBeatsResponse(BaseModel):
    tagged: int = 0
    events_seen: int = 0
    motifs_assigned: dict[str, int] = Field(default_factory=dict)   # motif_code → count


@router.post(
    "/tag-beats",
    response_model=TagBeatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Tag :Event nodes with the catalog motif they embody (W8 mining source)",
    description=(
        "Classifies each :Event (title+summary+participants) into one code of the user's "
        "VISIBLE motif catalog via an LLM (operation=chat → provider-registry), persisting "
        ":Event.mined_motif_code so motif-beats emits generic beat/thread axes for corpus "
        "mining. Scope is one book (book_id) or the whole corpus (corpus=true). ADVISORY / "
        "uncalibrated; degrades to a partial/empty tag on any LLM failure. X-Internal-Token."
    ),
)
async def tag_beats(body: TagBeatsRequest) -> TagBeatsResponse:
    if not settings.neo4j_uri:
        logger.info("tag-beats: Neo4j not configured — no-op")
        return TagBeatsResponse()

    from app.db.neo4j_repos.events import list_events_in_order, set_mined_motif_codes
    from app.extraction.motif_beat import _list_user_book_projects
    # Reuse the realized-motif classifier engine verbatim — same task shape (classify each
    # event into one code of a provided vocab); only the vocab source (catalog vs arc) and the
    # persisted property differ. No duplicate prompt/parse logic.
    from app.extraction.motif_tag import classify_event_motifs

    # Neutralize the catalog vocab — it may carry OTHER tenants' public-motif free text
    # (cross-tenant prompt-injection surface; the events are already neutralized below).
    valid = _neutralize_motif_vocab(body.motifs)
    if not valid:
        return TagBeatsResponse()

    llm = get_llm_client()
    containers = await _list_user_book_projects(body.user_id, body.book_id, corpus=body.corpus)
    seen = 0
    tagged = 0
    counts: dict[str, int] = {}
    async with neo4j_session() as session:
        for project_id, _book_id in containers:
            events = await list_events_in_order(
                session, user_id=str(body.user_id), project_id=str(project_id), limit=2000)
            if not events:
                continue
            seen += len(events)
            ev_dicts = _neutralize_event_dicts(events, project_id=str(project_id))
            assignments = await classify_event_motifs(
                llm, user_id=str(body.user_id), model_source=body.model_source,
                model_ref=body.model_ref, events=ev_dicts, motifs=valid)
            # Clear a stale mined_motif_code on any considered event left unassigned (re-mine
            # after the catalog changed must not leave orphaned generic labels).
            tagged += await set_mined_motif_codes(
                session, user_id=str(body.user_id), assignments=assignments,
                event_ids={e["id"] for e in ev_dicts})
            for code in assignments.values():
                counts[code] = counts.get(code, 0) + 1
    return TagBeatsResponse(tagged=tagged, events_seen=seen, motifs_assigned=counts)


# ── D-W10-ARC-CONFORMANCE-SUCCESSION F2 — causal-edge inference ────────


class CausalEdgesRequest(BaseModel):
    user_id: UUID
    book_id: UUID
    model_source: str
    model_ref: str
    # infer only over the motif-tagged subset (the arc-relevant beats) by default — bounds cost.
    tagged_only: bool = True


class CausalEdgesResponse(BaseModel):
    edges_written: int = 0
    events_considered: int = 0


@router.post(
    "/causal-edges",
    response_model=CausalEdgesResponse,
    status_code=status.HTTP_200_OK,
    summary="Infer (:Event)-[:CAUSES]->(:Event) edges (deep succession causal-verify)",
    description=(
        "Infers direct causal links over the ordered :Event timeline (LLM, operation=chat → "
        "provider-registry), MERGEing :CAUSES edges so deep arc-conformance can flip a legal "
        "succession transition causally-verified. By default runs over the motif-tagged subset "
        "(bounds cost). ADVISORY / uncalibrated; degrades to fewer/no edges. X-Internal-Token."
    ),
)
async def causal_edges(body: CausalEdgesRequest) -> CausalEdgesResponse:
    if not settings.neo4j_uri:
        logger.info("causal-edges: Neo4j not configured — no-op")
        return CausalEdgesResponse()

    from app.db.neo4j_repos.events import list_events_in_order, merge_causal_edges
    from app.extraction.causal_edges import infer_causal_edges
    from app.extraction.motif_beat import _list_user_book_projects

    llm = get_llm_client()
    containers = await _list_user_book_projects(body.user_id, body.book_id, corpus=False)
    considered = 0
    written = 0
    async with neo4j_session() as session:
        for project_id, _book_id in containers:
            events = await list_events_in_order(
                session, user_id=str(body.user_id), project_id=str(project_id), limit=2000)
            if body.tagged_only:
                events = [e for e in events if e.realized_motif_code]
            if len(events) < 2:
                continue
            considered += len(events)
            ev_dicts = _neutralize_event_dicts(events, project_id=str(project_id))
            pairs = await infer_causal_edges(
                llm, user_id=str(body.user_id), model_source=body.model_source,
                model_ref=body.model_ref, events=ev_dicts)
            if pairs:
                written += await merge_causal_edges(
                    session, user_id=str(body.user_id), pairs=pairs)
    return CausalEdgesResponse(edges_written=written, events_considered=considered)


class CausalMotifPairsRequest(BaseModel):
    user_id: UUID
    book_id: UUID


class CausalMotifPairsResponse(BaseModel):
    pairs: list[list[str]] = Field(default_factory=list)   # [[cause_code, effect_code]]


@router.post(
    "/causal-motif-pairs",
    response_model=CausalMotifPairsResponse,
    status_code=status.HTTP_200_OK,
    summary="Read realized CAUSES edges in motif-code space (deep succession causal-verify)",
    description=(
        "The realized :CAUSES edges projected to (cause_motif_code, effect_motif_code) over "
        "events whose both endpoints are motif-tagged — the causal_code_pairs deep "
        "arc-conformance flips a transition causally-verified with. X-Internal-Token."
    ),
)
async def causal_motif_pairs(body: CausalMotifPairsRequest) -> CausalMotifPairsResponse:
    if not settings.neo4j_uri:
        return CausalMotifPairsResponse()

    from app.db.neo4j_repos.events import get_causal_motif_pairs
    from app.extraction.motif_beat import _list_user_book_projects

    containers = await _list_user_book_projects(body.user_id, body.book_id, corpus=False)
    seen: set[tuple[str, str]] = set()
    async with neo4j_session() as session:
        for project_id, _book_id in containers:
            for c, e in await get_causal_motif_pairs(
                    session, user_id=str(body.user_id), project_id=str(project_id)):
                seen.add((c, e))
    return CausalMotifPairsResponse(pairs=[[c, e] for c, e in sorted(seen)])


# ── K17 (cycle 12b) — entity-embedding backfill ───────────────────────

# One batch's worth of candidates per producer call; the loop drains.
_EMBED_BACKFILL_BATCH = 200
# Safety net: bounds the drain loop even if the producer pathologically keeps
# reporting a full batch (e.g. a future bug). At 200/iter this caps a single
# request at 40k entities — far above any real project.
_EMBED_BACKFILL_MAX_ITER = 200


class EmbedBackfillRequest(BaseModel):
    user_id: UUID
    project_id: UUID
    # Per-request safety cap on how many entities to embed (cost guard).
    max_entities: int = Field(default=2000, ge=1, le=20000)


class EmbedBackfillResponse(BaseModel):
    embedded: int
    skipped: int
    iterations: int
    drained: bool
    reason: str | None = None


@router.post(
    "/embed-entities-backfill",
    response_model=EmbedBackfillResponse,
    summary="K17 — (re)embed a project's anchored entities for semantic glossary search",
    description=(
        "Drains `find_entities_needing_embedding` for the project's current "
        "embedding model: stamps `:Entity.embedding_{dim}` so "
        "/internal/context/glossary-semantic returns tier=semantic. Idempotent "
        "(already-embedded entities are not re-found) and cost-bounded "
        "(`max_entities`). Degrades cleanly (no embedding model / no book → 0 "
        "embedded, reason set). Behind X-Internal-Token."
    ),
)
async def embed_entities_backfill(
    body: EmbedBackfillRequest,
    projects_repo=Depends(get_projects_repo),
) -> EmbedBackfillResponse:
    from app.clients.embedding_client import get_embedding_client
    from app.extraction.entity_embedder import embed_project_entities

    project = await projects_repo.get(body.user_id, body.project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found",
        )
    if not project.embedding_model or not project.embedding_dimension:
        return EmbedBackfillResponse(
            embedded=0, skipped=0, iterations=0, drained=True,
            reason="project has no embedding model configured",
        )
    if project.book_id is None:
        return EmbedBackfillResponse(
            embedded=0, skipped=0, iterations=0, drained=True,
            reason="project has no book",
        )

    embedding_client = get_embedding_client()
    glossary_client = get_glossary_client()
    embedded = skipped = iterations = 0
    drained = False

    async with neo4j_session() as session:
        while iterations < _EMBED_BACKFILL_MAX_ITER and embedded < body.max_entities:
            res = await embed_project_entities(
                session,
                embedding_client,
                glossary_client,
                user_id=body.user_id,
                project_id=body.project_id,
                book_id=project.book_id,
                embedding_model=project.embedding_model,
                embedding_dim=project.embedding_dimension,
                limit=_EMBED_BACKFILL_BATCH,
            )
            embedded += res.embedded
            skipped += res.skipped
            iterations += 1
            if res.candidates < _EMBED_BACKFILL_BATCH:
                # Fewer candidates than a full batch → the queue is drained.
                drained = True
                break
            if res.embedded == 0:
                # A FULL batch of candidates but none embedded — the remaining
                # entities are permanently un-embeddable (empty text / dim
                # mismatch) or the provider just failed. Re-running would
                # re-find the same set, so stop to avoid an infinite loop
                # (the find query returns "still needs embedding" rows).
                break

    return EmbedBackfillResponse(
        embedded=embedded, skipped=skipped, iterations=iterations, drained=drained,
    )
