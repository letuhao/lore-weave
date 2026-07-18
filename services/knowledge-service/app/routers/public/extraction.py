"""K16.2–K16.8 — Extraction lifecycle endpoints under /v1/knowledge/projects/{id}/extraction.

K16.2: cost estimation. K16.3: start. K16.4: pause/resume/cancel.
K16.5: job status. K16.8: delete graph.

Authentication: JWT via router-level + per-route dependency (same
pattern as projects.py — see the double-dependency note there).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from loreweave_jobs import emit_job_event
from pydantic import BaseModel, Field, field_validator

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingError, probe_embedding_dimension
from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
from app.clients.chapter_title_enricher import (
    enrich_jobs_with_current_chapter_titles,
)
from app.clients.glossary_client import GlossaryClient
from app.clients.model_name import resolve_model_name
from app.config import settings as app_settings
from app.pricing import cost_per_token
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.flywheel import get_flywheel_delta
from app.db.pool import get_knowledge_pool
from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.routers.internal_benchmark import BenchmarkStatusResponse, gate_failures_from_raw
from app.db.repositories.extraction_jobs import (
    DEFAULT_TARGETS,
    LIST_ALL_MAX_LIMIT,
    CursorDecodeError,
    ExtractionJob,
    ExtractionJobCreate,
    ExtractionJobsRepo,
)
from app.db.repositories.extraction_pending import ExtractionPendingRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_benchmark_runs_repo,
    get_book_client,
    get_extraction_jobs_repo,
    get_extraction_pending_repo,
    get_extraction_wake,
    get_glossary_client,
    get_projects_repo,
)
from app.jobs.budget import can_start_job, check_user_monthly_budget
from app.jobs.extraction_wake import ExtractionWakeFn
from app.jobs.state_machine import JobStatus, PauseReason, StateTransitionError, validate_transition
from app.logging_config import trace_id_var
from app.auth.grant_deps import (
    GrantLevel,
    Principals,
    require_job_grant,
    require_project_grant,
    require_project_principals,
)
from app.middleware.jwt_auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/knowledge/projects",
    tags=["extraction"],
    dependencies=[Depends(get_current_user)],
)

# ── Token-per-item estimates (KSA §5.5) ─────────────────────────────
# Prompt + response tokens for a single extraction pass. These are
# conservative upper-bound estimates for cost preview. The actual
# job uses atomic try_spend with real token counts.
_TOKENS_PER_CHAPTER = 2000
_TOKENS_PER_CHAT_TURN = 800
_TOKENS_PER_GLOSSARY_ENTITY = 300
# C13 — pinned-injection cost. Each pinned glossary entity adds ~50 prompt
# tokens (name + a short canon hint) to EVERY extraction window. With one
# window per chapter, the dominant pinned cost is
# `pinned_count × 50 × num_windows` — surfaced as its own estimate line so a
# user sees that pinning 30 entities across a 5000-chapter book is expensive.
_TOKENS_PER_PINNED_ENTITY = 50

# Per-token cost lookup now lives in `app.pricing` (T2-close-5 /
# D-K16.2-01 cleared). Unknown models still fall back to the legacy
# ~$2/M default there.

# Seconds per item estimate for duration preview.
_SECONDS_PER_ITEM = 2


# ── scope_range helpers ─────────────────────────────────────────────


def _extract_chapter_range(
    scope_range: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    """Pull `chapter_range = [from, to]` out of ``scope_range`` or return
    ``(None, None)`` if the caller didn't set one.

    Raises 422 on malformed entries. Used by both the estimate and
    start endpoints so the shape check is applied in exactly one place
    — without this helper, the start path accepted garbage while
    estimate rejected it (review-impl finding MED #2).

    **Runner note (D-K16.2-02b, CLEARED S2):** the worker-ai extraction runner
    NOW honours `chapter_range` — ``_enumerate_chapters`` filters
    ``lo <= sort_order <= hi`` from ``job.scope_range`` (services/worker-ai/app/
    runner.py), so the actual job processes the same chapter subset the estimate
    previews. The start path additionally rejects a range that matches NO published
    chapter (422, D-K19a.5-04 out-of-bounds guard) so a no-op job can't be created.
    """
    if not scope_range or "chapter_range" not in scope_range:
        return None, None
    raw = scope_range["chapter_range"]
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in raw)
        or any(v < 0 for v in raw)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="scope_range.chapter_range must be [int, int] with non-negative values",
        )
    # C12a /review-impl MED#1 — reject reversed range (from > to). The
    # C12a runner gate uses `lo <= sort_order <= hi` as a membership
    # test; with lo > hi it's vacuously false → silently skips every
    # chapter. Match the FE-side ``from ≤ to`` invariant so a direct-
    # API caller gets an explicit error instead of a no-op job.
    if int(raw[0]) > int(raw[1]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"scope_range.chapter_range from ({raw[0]}) must be "
                f"<= to ({raw[1]})"
            ),
        )
    return int(raw[0]), int(raw[1])


# ── Request / response models ───────────────────────────────────────

JobScope = Literal["chapters", "chat", "glossary_sync", "all", "chapters_pending"]  # CM3b: internal coalescing-drainer scope

# C12 — target taxonomy. Maps 1:1 to a Pass-2 pass. `summaries` is the
# summary enqueue (orchestrator-gated). The FE's "events·timeline" label
# is the `events` op; "lore/wiki" is the wiki-stub path (not an SDK op,
# handled elsewhere) — kept out of this build-target set.
ExtractionTarget = Literal["entities", "relations", "events", "facts", "summaries"]
# NOTE — the dependent auto-include (requesting any of {relations,events,
# facts} ⇒ `entities`) is applied at RUNTIME (SDK normalize_targets +
# decoupled trio resolver), NOT in the request layer. The stored array keeps
# the user's EXPLICIT intent so the worker's recovery/filter LOCK gate works.


class EstimateRequest(BaseModel):
    scope: JobScope
    # D-K16.2-02 — `{"chapter_range": [from, to]}` (inclusive,
    # sort_order-based ints). Forwarded to book-service so the preview
    # reflects the filtered chapter count. See `_extract_chapter_range`
    # for the runner-side gap (D-K16.2-02b) — chapter_range affects
    # preview only until the event-driven runner honours it too.
    scope_range: dict | None = None
    llm_model: str = Field(min_length=1, max_length=200)
    # C13 — how many glossary entities the user intends to pin. Drives the
    # pinned-injection cost line (pinned_count × ~50 tokens × num_windows). 0 ⇒
    # no pinned-injection cost (default — back-compat with pre-C13 callers).
    pinned_count: Annotated[int, Field(ge=0)] = 0


class StartJobRequest(BaseModel):
    scope: JobScope
    # Same shape as `EstimateRequest.scope_range`. Validated via
    # `_extract_chapter_range` at request time so the DB never stores
    # a malformed shape that the estimate path would have rejected.
    scope_range: dict[str, Any] | None = None
    llm_model: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=1, max_length=200)
    max_spend_usd: Annotated[Decimal, Field(ge=0)] | None = None
    # #9 — DEPRECATED / IGNORED. The create path now computes items_total server-side
    # from the real scope counts (chapters+chat+glossary), so a client-supplied value
    # (the old "1/100" placeholder) is never stored. Kept on the schema only so existing
    # callers that still send it don't 422; its value is discarded.
    items_total: Annotated[int, Field(ge=0)] | None = None
    # C12 — target-typed extraction. None / empty ⇒ ALL passes (back-compat).
    # A concrete list runs only those passes. Dependent targets are
    # auto-included by the validator below (don't error — silently force
    # `entities` in). Deduped + order-stable.
    targets: list[ExtractionTarget] | None = None
    # C12 — passthrough cap on parallel LLM calls. None ⇒ unbounded (current).
    concurrency_level: Annotated[int, Field(ge=1, le=64)] | None = None
    # C13 — glossary pinning. The glossary entity ids to force-inject into
    # EVERY extraction window's known_entities (name-prefix injection) so
    # sparse-but-critical entities are anchored regardless of chapter content.
    # None / empty ⇒ no pins (back-compat). Stored as pinned_entity_ids JSONB.
    pinned_glossary_entity_ids: list[str] | None = None
    # D-RE-OTHER-AGENTIC-EFFORT: the clamped graded reasoning effort (none|low|medium|high) for
    # the extraction LLM. Stored on the job; worker-ai honors it via D-KG-WORKER-GRADED-EFFORT.
    # Default 'none' ⇒ back-compat (no thinking) for callers that don't set it.
    reasoning_effort: str = "none"

    @field_validator("targets")
    @classmethod
    def _normalise_targets(
        cls, v: list[str] | None,
    ) -> list[str] | None:
        """Dedupe + canonicalise the requested target set. None / empty pass
        through unchanged (⇒ all passes = back-compat).

        IMPORTANT — does NOT auto-include `entities` here. The dependent
        auto-include ({relations,events,facts} ⇒ entities) is applied at
        RUNTIME by the SDK (`normalize_targets`) + the decoupled trio
        resolver, NOT baked into the stored array. This is load-bearing for
        the LOCK "recovery/precision-filter auto-disable when entities ∉
        targets": the worker keys that gate off the user's EXPLICIT request,
        which would be lost if we stored an entities-injected array (a
        relations-only build would then read as if entities were asked for
        and wrongly keep recovery/filter enabled). So: validate + dedupe
        only; entities is added downstream exactly where it's needed (as a
        mandatory anchor pass) without polluting the stored intent."""
        if not v:
            return v
        present = set(v)
        # Canonical order = the DEFAULT_TARGETS order, filtered to present.
        return [t for t in DEFAULT_TARGETS if t in present]


class EstimateItemCounts(BaseModel):
    chapters: int = 0
    chat_turns: int = 0
    glossary_entities: int = 0

    @property
    def total(self) -> int:
        return self.chapters + self.chat_turns + self.glossary_entities


async def _count_scope_items(
    scope: str,
    scope_range: dict[str, Any] | None,
    project: Any,
    user_id: UUID,
    project_id: UUID,
    *,
    book_client: BookClient | None = None,
    pending_repo: ExtractionPendingRepo | None = None,
    glossary_client: GlossaryClient | None = None,
) -> EstimateItemCounts:
    """Count the items an extraction job will actually process for a scope, server-side.

    Shared by the cost ESTIMATE and the job CREATE path so the stored ``items_total``
    is the REAL denominator (chapters + chat_turns + glossary_entities) — never a
    client-supplied placeholder (#9: the "1/100" progress bug, where the FE's optional
    ``items_total`` was trusted verbatim). The same published-scoped chapter count the
    runner enumerates is used, so the progress bar's denominator matches the work done.

    Each client is optional: a public handler injects them (so test ``dependency_overrides``
    apply); an internal/retry caller that doesn't passes None and we fall back to the
    per-worker singleton accessor.
    """
    chapters = chat_turns = glossary_entities = 0
    chapter_from, chapter_to = _extract_chapter_range(scope_range)

    if scope in ("chapters", "all") and project.book_id is not None:
        bc = book_client if book_client is not None else await get_book_client()
        # WS-0.6: count what the rebuild will actually EXTRACT — the chapters in the
        # knowledge graph — not the chapters that happen to be published. Keyed on
        # publish, this preview would report "0 chapters" for a user who indexed 50
        # drafts, and then the job would run and (correctly) extract them: the estimate
        # and the enumeration MUST use the same gate.
        count = await bc.count_chapters(
            project.book_id, from_sort=chapter_from, to_sort=chapter_to,
            kg_indexed=True,
        )
        chapters = count if count is not None else 0

    if scope in ("chat", "all"):
        pr = pending_repo if pending_repo is not None else await get_extraction_pending_repo()
        chat_turns = await pr.count_pending(user_id, project_id)

    if scope in ("glossary_sync", "all") and project.book_id is not None:
        gc = glossary_client if glossary_client is not None else await get_glossary_client()
        count = await gc.count_entities(project.book_id)
        glossary_entities = count if count is not None else 0

    return EstimateItemCounts(
        chapters=chapters, chat_turns=chat_turns, glossary_entities=glossary_entities,
    )


class EstimateResponse(BaseModel):
    items_total: int
    items: EstimateItemCounts
    estimated_tokens: int
    # C13 — the pinned-injection slice of `estimated_tokens`, surfaced on its
    # own so the FE can show "pinned context: N tokens" as a distinct line. It
    # is `pinned_count × _TOKENS_PER_PINNED_ENTITY × num_windows` and is already
    # folded into `estimated_tokens` (and thus the cost). 0 when nothing pinned.
    estimated_pinned_tokens: int = 0
    estimated_cost_usd_low: Decimal
    estimated_cost_usd_high: Decimal
    estimated_duration_seconds: int


# ── Endpoint ─────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/extraction/estimate",
    response_model=EstimateResponse,
    status_code=status.HTTP_200_OK,
)
async def estimate_extraction_cost(
    project_id: UUID,
    body: EstimateRequest,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    pending_repo: ExtractionPendingRepo = Depends(get_extraction_pending_repo),
    book_client: BookClient = Depends(get_book_client),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> EstimateResponse:
    """Preview cost and item counts for a proposed extraction job.

    Does NOT create a job or spend any budget. The frontend shows this
    in the "Build Knowledge Graph" confirmation dialog (KSA §5.5).
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    scope = body.scope

    # Chapter count gates to editorial_status='published' (CM3c) so the estimate
    # matches what the gated whole-book rebuild actually extracts (drafts skipped) —
    # the SAME server-side count the CREATE path now stores as items_total (#9), so
    # preview and progress-denominator can never diverge.
    counts = await _count_scope_items(
        scope, body.scope_range, project, user_id, project_id,
        book_client=book_client, pending_repo=pending_repo, glossary_client=glossary_client,
    )
    chapters = counts.chapters
    chat_turns = counts.chat_turns
    glossary_entities = counts.glossary_entities
    items_total = counts.total
    # C13 — pinned-injection cost. The pinned names are prepended to EVERY
    # extraction window's known_entities, and there is one window per chapter +
    # one per chat turn (the two LLM-extraction item types; glossary_sync is a
    # pure Neo4j MERGE with no window). So num_windows = chapters + chat_turns.
    # This is the dominant driver for a large book — surfaced as its own line.
    num_windows = chapters + chat_turns
    estimated_pinned_tokens = (
        body.pinned_count * _TOKENS_PER_PINNED_ENTITY * num_windows
    )
    estimated_tokens = (
        chapters * _TOKENS_PER_CHAPTER
        + chat_turns * _TOKENS_PER_CHAT_TURN
        + glossary_entities * _TOKENS_PER_GLOSSARY_ENTITY
        + estimated_pinned_tokens
    )

    base_cost = Decimal(estimated_tokens) * cost_per_token(body.llm_model)
    cost_low = (base_cost * Decimal("0.7")).quantize(Decimal("0.01"))
    cost_high = (base_cost * Decimal("1.3")).quantize(Decimal("0.01"))

    duration = items_total * _SECONDS_PER_ITEM

    return EstimateResponse(
        items_total=items_total,
        items=EstimateItemCounts(
            chapters=chapters,
            chat_turns=chat_turns,
            glossary_entities=glossary_entities,
        ),
        estimated_tokens=estimated_tokens,
        estimated_pinned_tokens=estimated_pinned_tokens,
        estimated_cost_usd_low=cost_low,
        estimated_cost_usd_high=cost_high,
        estimated_duration_seconds=duration,
    )


# ── Shared: create + start job transaction ───────────────────────────


async def _create_and_start_job(
    user_id: UUID,
    project_id: UUID,
    validated: ExtractionJobCreate,
    projects_repo: ProjectsRepo,
    trace_id: str,
) -> UUID:
    """Atomically create a job, update project state, and transition
    to running. Used by both K16.3 (start) and K16.9 (rebuild).

    Returns the new job_id. Raises 409 on concurrent start
    (unique partial index), 404 if project vanishes mid-transaction.
    """
    # P4 usage emit — resolve the human model NAMEs (best-effort) OUTSIDE the tx
    # (network I/O; never hold a tx open across it, H1) so the 'running' lifecycle
    # event carries model + a whitelisted params dict for the Jobs GUI. extraction
    # models are BYOK user_models. None on any resolve failure (GUI is null-safe).
    model_name = await resolve_model_name("user_model", str(validated.llm_model))
    embedding_name = await resolve_model_name("user_model", str(validated.embedding_model))
    job_params = {
        "model": model_name,
        "model_ref": str(validated.llm_model),
        "embedding_model": embedding_name,
        "scope": validated.scope,
        "scope_range": validated.scope_range,
        "targets": list(validated.targets) if validated.targets is not None else None,
        "concurrency": validated.concurrency_level,
        "max_spend_usd": (
            float(validated.max_spend_usd) if validated.max_spend_usd is not None else None
        ),
    }
    pool = get_knowledge_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                job_row = await conn.fetchrow(
                    """
                    INSERT INTO extraction_jobs
                      (user_id, project_id, scope, scope_range, llm_model,
                       embedding_model, max_spend_usd, items_total, campaign_id,
                       billing_user_id, billing_embedding_model, billing_llm_model,
                       targets, concurrency_level, pinned_entity_ids,
                       mcp_key_id, spend_cap_usd)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14, $15::jsonb, $16, $17)
                    RETURNING job_id
                    """,
                    user_id,
                    project_id,
                    validated.scope,
                    json.dumps(validated.scope_range) if validated.scope_range else None,
                    validated.llm_model,
                    validated.embedding_model,
                    validated.max_spend_usd,
                    validated.items_total,
                    # E0-3 Phase 2b (LOW-1) — this inline INSERT previously dropped
                    # campaign_id AND would drop billing_*; both are now persisted
                    # so the start/rebuild path carries BYOK billing (else a
                    # collaborator's extraction silently bills the owner) and S4a
                    # campaign attribution.
                    validated.campaign_id,
                    validated.billing_user_id,
                    validated.billing_embedding_model,
                    validated.billing_llm_model,
                    # C12 — None ⇒ explicit all-five default (== column DEFAULT)
                    # so the rebuild path (which omits targets) and any other
                    # caller stores a concrete set; the runner never sees NULL.
                    list(validated.targets) if validated.targets is not None
                    else list(DEFAULT_TARGETS),
                    validated.concurrency_level,
                    # C13 — pinned glossary entity ids as a JSONB array (NULL ⇒
                    # no pins, back-compat). The worker reads this to fetch the
                    # pinned names and prepend them into every window.
                    json.dumps(validated.pinned_entity_ids)
                    if validated.pinned_entity_ids else None,
                    # D-PMCP-WORKER-CARRIER: public-MCP key + cap (float8 column) so
                    # worker-ai re-sets the attribution contextvar from the row.
                    validated.mcp_key_id,
                    validated.spend_cap_usd,
                )
                job_id = job_row["job_id"]

                updated_project = await projects_repo.set_extraction_state(
                    user_id, project_id,
                    extraction_enabled=True,
                    extraction_status="building",
                    embedding_model=validated.embedding_model,
                    conn=conn,
                )
                if updated_project is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="project vanished during transaction",
                    )

                validate_transition("pending", "running", trace_id=trace_id)
                await conn.execute(
                    """
                    UPDATE extraction_jobs
                    SET status = 'running', started_at = now(), updated_at = now()
                    WHERE job_id = $1 AND user_id = $2
                    """,
                    job_id, user_id,
                )
                # Unified Job Control Plane P1 — this start path is an inline
                # INSERT(pending)+UPDATE(running) (NOT repo.create/update_status), so
                # emit the initial 'running' lifecycle event here in the SAME tx (else
                # the projection never sees the job appear until its terminal event).
                await emit_job_event(
                    conn, service="knowledge", job_id=str(job_id),
                    owner_user_id=str(user_id), kind="extraction", status="running",
                    model=model_name, cost_usd=0.0, params=job_params,
                )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project already has an active extraction job (concurrent start)",
        )
    return job_id


# ── K16.3 — Start extraction job ────────────────────────────────────


@router.post(
    "/{project_id}/extraction/start",
    response_model=ExtractionJob,
    status_code=status.HTTP_201_CREATED,
)
async def start_extraction_job(
    project_id: UUID,
    body: StartJobRequest,
    background_tasks: BackgroundTasks,
    # D-E0-3-CALLER-PAYS-EXTRACTION Phase 2b: re-opened to EDIT collaborators
    # under BYOK caller-pays. Phase 1 made this OWNER-only to close the breach
    # where an edit-collaborator's extraction ran on the OWNER's key. Now a
    # collaborator extracts on THEIR OWN same-model key: require_project_principals
    # returns (owner, caller) — the core partitions graph/budget/storage-tag by
    # the owner but bills the embedding+LLM provider calls to the caller (their
    # billing_user_id + same-model refs), with a dimension guard ensuring the
    # caller's embedding model shares the project's vector space.
    principals: Principals = Depends(require_project_principals(GrantLevel.EDIT)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    benchmark_repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
    book_client: BookClient = Depends(get_book_client),
    # #9 — injected so the core can compute items_total server-side (and so test
    # dependency_overrides apply); the core falls back to the singletons for the
    # internal-dispatch callers that don't pass them.
    pending_repo: ExtractionPendingRepo = Depends(get_extraction_pending_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
    extraction_wake: ExtractionWakeFn = Depends(get_extraction_wake),
) -> ExtractionJob:
    """Public route handler. Delegates to the core.

    S4a: `campaign_id` is an INTERNAL-only attribution tag — it is deliberately
    NOT a parameter here, so the public surface cannot accept it. A user therefore
    cannot tag their own job to another user's campaign (which would inflate that
    campaign's spend and trip its budget pause). Only the internal dispatch
    endpoint (campaign-service, ownership pre-verified) supplies it via the core.
    """
    job = await _start_extraction_job_core(
        project_id, body, principals.owner, projects_repo, jobs_repo, benchmark_repo,
        caller=principals.caller,
        book_client=book_client,
        pending_repo=pending_repo,
        glossary_client=glossary_client,
        extraction_wake=extraction_wake,
    )
    # D-KG-PASSAGES-NOT-INGESTED — the user is indexing the book, so the embedding
    # config is present; (re)ingest the published chapters' :Passage nodes in the
    # background so semantic memory/story search isn't left empty by "the chapters
    # were published before this project had embedding config". Best-effort +
    # idempotent — never blocks or fails the extraction start.
    proj = await projects_repo.get(principals.owner, project_id)
    if proj is not None and proj.book_id and proj.embedding_model and proj.embedding_dimension:
        # D-BACKFILL-NO-SCOPE-LIMIT — bound the passage backfill to the chapters this
        # job actually extracts (its scope_range), so a scoped extraction of a large
        # book ingests passages ONLY for the extracted slice, not the whole book. A
        # whole-book / chat / glossary scope leaves chapter_range None (full book).
        _lo, _hi = _extract_chapter_range(body.scope_range) if body.scope == "chapters" else (None, None)
        _bf_range = (_lo, _hi) if _lo is not None and _hi is not None else None
        background_tasks.add_task(
            _auto_backfill_passages,
            project_id=project_id, user_id=principals.owner, book_id=proj.book_id,
            embedding_model=proj.embedding_model, embedding_dim=proj.embedding_dimension,
            chapter_range=_bf_range,
        )
    return job


async def _auto_backfill_passages(
    *,
    project_id: UUID,
    user_id: UUID,
    book_id: UUID,
    embedding_model: str,
    embedding_dim: int,
    chapter_range: tuple[int, int] | None = None,
) -> None:
    """Best-effort background passage backfill fired on extraction start
    (D-KG-PASSAGES-NOT-INGESTED). Swallows ALL errors — extraction must never be
    affected by it. Skips cleanly in Track-1 (no Neo4j). ``chapter_range`` bounds the
    backfill to the extraction job's chapter slice (D-BACKFILL-NO-SCOPE-LIMIT)."""
    try:
        from app.clients.book_client import get_book_client as _get_bc
        from app.clients.embedding_client import get_embedding_client
        from app.config import settings as _settings
        from app.extraction.passage_backfill import backfill_project_passages

        if not _settings.neo4j_uri:
            return
        res = await backfill_project_passages(
            project_id=project_id, user_id=user_id, book_id=book_id,
            embedding_model=embedding_model, embedding_dim=embedding_dim,
            book_client=_get_bc(), embedding_client=get_embedding_client(),
            chapter_range=chapter_range,
        )
        logger.info(
            "auto passage backfill on extraction start project=%s: %s", project_id, res,
        )
    except Exception:
        logger.warning(
            "auto passage backfill failed project=%s — non-fatal", project_id,
            exc_info=True,
        )


async def _start_extraction_job_core(
    project_id: UUID,
    body: StartJobRequest,
    user_id: UUID,
    projects_repo: ProjectsRepo,
    jobs_repo: ExtractionJobsRepo,
    benchmark_repo: BenchmarkRunsRepo,
    *,
    campaign_id: UUID | None = None,
    caller: UUID | None = None,
    book_client: BookClient | None = None,
    pending_repo: ExtractionPendingRepo | None = None,
    glossary_client: GlossaryClient | None = None,
    extraction_wake: ExtractionWakeFn | None = None,
    mcp_key_id: str | None = None,
    spend_cap_usd: float | None = None,
) -> ExtractionJob:
    """Create and start an extraction job for a project.

    E0-3 Phase 2b — BYOK dual identity. ``user_id`` is the project OWNER (graph
    partition, project budget, canonical embedding tag). ``caller`` is the
    authenticated requester; when ``caller != user_id`` (a book collaborator),
    the embedding + LLM provider calls are billed to the caller (their key +
    monthly budget) via the job's ``billing_*`` columns, and ``body.embedding_model``
    is the CALLER's same-model ref — dimension-guarded against the project's
    vector space (409 on mismatch). ``caller is None`` or ``== user_id`` is the
    owner path (legacy single identity, ``billing_* = NULL``). The campaign
    dispatch path passes no caller → owner path.

    Atomically: creates the job row, updates the project's extraction
    state to 'building', and transitions the job to 'running' — all
    in a single DB transaction. Returns 409 if another active job
    already exists for this project.

    K17.9 benchmark gate: every call must have a passing
    `project_embedding_benchmark_runs` row for the chosen
    `embedding_model`, or the call is rejected with 409. This
    prevents a user from enabling Mode 3 with an embedding model
    that can't find their own entities — a silent quality
    regression that the benchmark is designed to catch.

    Worker pickup (FD-22): worker-ai's poll loop is the source-of-truth
    (it claims + transitions jobs atomically). After the job is confirmed
    running we emit a best-effort Redis **wake** (``extraction.wake``) so the
    worker picks it up immediately instead of waiting for its next poll; a
    failed/absent wake just falls back to that poll (≤ poll_interval_s).
    """
    # 0. Validate scope_range.chapter_range shape (review-impl MED #2).
    # Raises 422 on malformed payloads so the DB never stores a shape
    # the estimate path would have rejected.
    chap_from, chap_to = _extract_chapter_range(body.scope_range)

    # 1. Verify project exists and belongs to user
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # 1b. Out-of-bounds chapter-range guard (D-K19a.5-04). The runner enforces
    # `lo <= sort_order <= hi` (worker-ai `_enumerate_chapters`), so a range that
    # matches NO published chapter would silently complete a 0-item job. Reject up
    # front — using the SAME published-scoped count the estimate shows — so the
    # caller gets explicit feedback instead of a no-op job. Only on a chapter-scoped
    # job with a range set + a real book.
    if (
        chap_from is not None
        and body.scope in ("chapters", "all")
        and project.book_id is not None
    ):
        # Use the injected client (public route) or fall back to the singleton
        # (internal dispatch / retry callers). get_book_client is async (returns
        # the per-worker singleton).
        bc = book_client if book_client is not None else await get_book_client()
        # WS-0.6: this admission guard must mirror the re-keyed runner enumeration
        # exactly — they both gate `scope in ("chapters","all")`. If the guard counted
        # published chapters while the runner enumerates kg-indexed ones, a user whose
        # indexed drafts are all unpublished would be REJECTED with "no chapters in
        # range" for a job that would have extracted them fine.
        in_range = await bc.count_chapters(
            project.book_id, from_sort=chap_from, to_sort=chap_to,
            kg_indexed=True,
        )
        if not in_range:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"scope_range.chapter_range [{chap_from}, {chap_to}] matches no "
                    "published chapters in this book"
                ),
            )

    # 1.4. E0-3 Phase 2b — BYOK dual-identity resolution. Default = owner path
    # (single identity, billing NULL, everything resolves under user_id). On the
    # collaborator path (caller != owner) the provider calls bill the caller; the
    # stored embedding_model tag + benchmark stay the project's canonical model.
    is_collab = caller is not None and caller != user_id
    billing_user_id: UUID | None = None
    billing_embedding_model: str | None = None
    billing_llm_model: str | None = None
    # The embedding_model value stored on the job row (= the search-filter tag).
    # Owner: body's (== project's). Collaborator: forced to the project's canonical
    # model, NOT the caller's ref (which generates compatible vectors but must be
    # tagged with the project's UUID to stay searchable). Also the benchmark key.
    storage_embedding_model = body.embedding_model
    if is_collab:
        # The collaborator MUST extract under the SAME embedding model (same
        # vector space) as the project, supplied as THEIR OWN provider-registry
        # ref. Guard: their ref must resolve AND match the project's dimension.
        if not project.embedding_model or not project.embedding_dimension:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "project_embedding_unconfigured",
                    "message": (
                        "the project has no embedding model configured; the "
                        "owner must run extraction first"
                    ),
                },
            )
        try:
            caller_dim = await probe_embedding_dimension(caller, body.embedding_model)
        except EmbeddingError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "embedding_model_unresolved",
                    "message": (
                        "your embedding model ref could not be resolved under "
                        "your provider credentials; register the project's "
                        "embedding model under your own key"
                    ),
                    "required_dimension": project.embedding_dimension,
                },
            ) from exc
        if caller_dim != project.embedding_dimension:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "embedding_model_mismatch",
                    "message": (
                        "your embedding model's dimension does not match the "
                        "project's vector space; register the same embedding "
                        "model the project uses under your own key"
                    ),
                    "required_dimension": project.embedding_dimension,
                    "your_dimension": caller_dim,
                },
            )
        billing_user_id = caller
        billing_embedding_model = body.embedding_model  # caller's ref (generation)
        billing_llm_model = body.llm_model              # caller's ref (generation)
        storage_embedding_model = project.embedding_model  # project's canonical tag

    # 1.5. C12c-a /review-impl MED#1 — guard scope='glossary_sync' (or
    # scope='all' explicitly expecting glossary) against projects
    # without a linked book. The estimate endpoint at line 230 already
    # skips glossary counting when book_id is null; the start endpoint
    # must match or it creates a no-op job the worker silently
    # completes. Only glossary_sync hard-requires a book — scope='all'
    # still works for chapters+chat without one (the glossary tail is
    # the only part that needs book_id, and the worker guards that).
    if body.scope == "glossary_sync" and project.book_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "glossary_sync_requires_book",
                "message": (
                    "scope='glossary_sync' requires a project with a "
                    "linked book; create or attach a book first"
                ),
            },
        )

    # 2. Fast-path check for active job (avoids transaction overhead).
    # Uses list_active which already filters status IN ('pending','running','paused').
    active_jobs = await jobs_repo.list_active(user_id)
    for j in active_jobs:
        if j.project_id == project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"project already has an active extraction job ({j.job_id}, status={j.status})",
            )

    # 2.5. K17.9 benchmark gate. Rejects when no run exists for the
    # chosen model OR when the latest run didn't pass thresholds.
    # Error messages are user-neutral (no CLI instructions) — the FE
    # picker surfaces a targeted CTA per `error_code`: the no-run
    # branch drives a "Run benchmark" button, the failed branch drives
    # a "See report" link. Keeping ops commands out of the public API
    # response avoids confusing end users if the 409 surfaces in a
    # toast before the picker's badge logic catches it.
    # E0-3 Phase 2b — the benchmark gate is OWNER + MODEL-scoped (R1,
    # D-JOURNEY-KG-BENCHMARK-UX): it validates the embedding MODEL's quality, which
    # is a per-model property, not per-project. A passing run for this model on ANY
    # of the owner's projects (incl. the hidden benchmark sandbox the run actually
    # executes on) satisfies it — so the run never has to (and never can) happen on
    # this content-bearing build project. A collaborator inherits it via the
    # dimension match above. `storage_embedding_model` is the project's model on the
    # collaborator path and body's (== project's) for the owner.
    latest_benchmark = await benchmark_repo.get_latest_for_model(
        user_id, storage_embedding_model,
    )
    if latest_benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "benchmark_missing",
                "message": (
                    f"no passing benchmark run for embedding_model "
                    f"{storage_embedding_model!r}; run the golden-set "
                    "benchmark for this model before enabling extraction"
                ),
                "embedding_model": storage_embedding_model,
            },
        )
    if not latest_benchmark.passed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "benchmark_failed",
                "message": (
                    "the most recent benchmark run for this embedding "
                    "model did not pass the quality thresholds; "
                    "extraction would produce low-quality results"
                ),
                "embedding_model": storage_embedding_model,
                "run_id": latest_benchmark.run_id,
                "recall_at_3": latest_benchmark.recall_at_3,
            },
        )

    # 2.6. D-K16.11-01: advisory monthly-budget pre-check. When the user
    # set a per-job `max_spend_usd`, use it as the estimated-cost proxy
    # — it's the ceiling they chose, and the check asks "would this job
    # (at its self-imposed cap) push me over my monthly budget?". When
    # `max_spend_usd` is None, both helpers see `estimated_cost=0` and
    # return allowed=True — the per-job `try_spend` is still the atomic
    # money guard regardless.
    pool = get_knowledge_pool()
    estimated_cost = body.max_spend_usd if body.max_spend_usd is not None else Decimal("0")

    project_check = await can_start_job(pool, user_id, project_id, estimated_cost)
    if not project_check.allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "monthly_budget_exceeded",
                "message": project_check.reason,
                "monthly_spent": str(project_check.monthly_spent),
                "monthly_budget": (
                    str(project_check.monthly_budget)
                    if project_check.monthly_budget is not None
                    else None
                ),
            },
        )

    # E0-3 Phase 2b — the project-budget check above is the OWNER's cap on their
    # project (unchanged). The USER monthly-budget is the CALLER's wallet — the
    # collaborator's own monthly budget gates and is debited, because their key
    # pays. Owner path: billing_user_id is None → falls back to user_id (owner).
    budget_user_id = billing_user_id or user_id
    user_check = await check_user_monthly_budget(pool, budget_user_id, estimated_cost)
    if not user_check.allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "user_budget_exceeded",
                "message": user_check.reason,
                "monthly_spent": str(user_check.monthly_spent),
                "monthly_budget": (
                    str(user_check.monthly_budget)
                    if user_check.monthly_budget is not None
                    else None
                ),
            },
        )

    # 2.7. #9 — compute the REAL progress denominator server-side (chapters + chat +
    # glossary for this scope), IGNORING any client-supplied body.items_total (the old
    # "1/100" placeholder). Best-effort: a transient count failure stores NULL → the FE
    # renders an indeterminate bar, which is strictly better than a wrong number or
    # blocking the job start. Done OUTSIDE the tx (network I/O; never hold a tx open
    # across it — H1).
    server_items_total: int | None = None
    try:
        server_items_total = (
            await _count_scope_items(
                body.scope, body.scope_range, project, user_id, project_id,
                book_client=book_client,
                pending_repo=pending_repo,
                glossary_client=glossary_client,
            )
        ).total
    except Exception:  # noqa: BLE001 — the count is advisory; never block job start
        logger.warning(
            "#9: failed to compute items_total project_id=%s scope=%s; storing NULL",
            project_id, body.scope, exc_info=True,
        )

    # 3. Validate + create job atomically.
    trace_id = trace_id_var.get()
    validated = ExtractionJobCreate(
        project_id=project_id,
        scope=body.scope,
        llm_model=body.llm_model,
        # E0-3 Phase 2b — storage tag (= search filter): the project's canonical
        # model on the collaborator path, body's (== project's) for the owner.
        embedding_model=storage_embedding_model,
        max_spend_usd=body.max_spend_usd,
        scope_range=body.scope_range,
        # #9 — server-computed denominator, NOT body.items_total (deprecated/ignored).
        items_total=server_items_total,
        campaign_id=campaign_id,  # S4a: internal-only (None for public callers)
        # E0-3 Phase 2b — caller's BYOK billing identity (all None on owner path).
        billing_user_id=billing_user_id,
        billing_embedding_model=billing_embedding_model,
        billing_llm_model=billing_llm_model,
        # C12 — target-typed extraction (None ⇒ all passes; the validator
        # already auto-included `entities` for dependent targets).
        targets=body.targets,
        concurrency_level=body.concurrency_level,
        # C13 — pinned glossary entity ids → stored as pinned_entity_ids JSONB.
        pinned_entity_ids=body.pinned_glossary_entity_ids,
        # D-RE-OTHER-AGENTIC-EFFORT: the clamped reasoning effort persisted on the job row.
        reasoning_effort=body.reasoning_effort,
        # D-PMCP-WORKER-CARRIER: public-MCP attribution (set only by the kg confirm
        # replay; None for first-party/HTTP callers — the public route never accepts it).
        mcp_key_id=mcp_key_id,
        spend_cap_usd=spend_cap_usd,
    )

    job_id = await _create_and_start_job(
        user_id, project_id, validated, projects_repo, trace_id,
    )

    # 4. Re-read the final job state outside the transaction
    job = await jobs_repo.get(user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="job created but not found on re-read",
        )

    logger.info(
        "K16.3: extraction job started job_id=%s project_id=%s scope=%s trace_id=%s",
        job_id, project_id, body.scope, trace_id,
    )

    # FD-22: best-effort wake so worker-ai picks the job up now, not on its next
    # poll. The job is already running, so the wake is pure optimization and must
    # never fail the 201. The redis fn swallows its own faults; this outer guard
    # is defense-in-depth so even a misbehaving wake fn can't break job-start.
    try:
        if extraction_wake is not None:
            await extraction_wake(job_id=job_id, project_id=project_id)
    except Exception:  # noqa: BLE001 — wake is non-fatal; poll loop is the fallback
        logger.warning(
            "FD-22: extraction wake raised (non-fatal) job_id=%s — poll fallback",
            job_id, exc_info=True,
        )

    return job


# ── K16.4 — Pause / Resume / Cancel ─────────────────────────────────


def _validate_or_409(
    current: JobStatus, new: JobStatus, *, trace_id: str, pause_reason: PauseReason | None = None,
) -> None:
    """Validate a state transition, raising 409 on invalid."""
    try:
        validate_transition(
            current, new, trace_id=trace_id, pause_reason=pause_reason,
        )
    except StateTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


async def _get_active_job_for_project(
    user_id: UUID,
    project_id: UUID,
    jobs_repo: ExtractionJobsRepo,
    projects_repo: ProjectsRepo,
) -> ExtractionJob:
    """Shared helper: verify project ownership and find the active job.

    Raises 404 if the project doesn't exist or has no active job.
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    # D-RAWSEARCH/B8: project-scoped active-job lookup (was a cross-project
    # list_active(user_id) + in-memory filter). The unique index limits one
    # active job per project, so the scoped query returns ≤1 row.
    active = await jobs_repo.list_active_for_project(user_id, project_id)
    if active:
        return active[0]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="no active extraction job for this project",
    )


@router.post(
    "/{project_id}/extraction/pause",
    response_model=ExtractionJob,
)
async def pause_extraction_job(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> ExtractionJob:
    """Pause a running extraction job (user-initiated)."""
    job = await _get_active_job_for_project(
        user_id, project_id, jobs_repo, projects_repo,
    )
    trace_id = trace_id_var.get()
    _validate_or_409(
        job.status, "paused", trace_id=trace_id, pause_reason="user",
    )
    updated = await jobs_repo.update_status(user_id, job.job_id, "paused")
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job status changed concurrently",
        )
    # Mirror job state to project so the frontend can show paused
    # without a separate job-status fetch.
    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=True,
        extraction_status="paused",
    )
    logger.info(
        "K16.4: job paused job_id=%s trace_id=%s", job.job_id, trace_id,
    )
    return updated


@router.post(
    "/{project_id}/extraction/resume",
    response_model=ExtractionJob,
)
async def resume_extraction_job(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> ExtractionJob:
    """Resume a paused extraction job."""
    job = await _get_active_job_for_project(
        user_id, project_id, jobs_repo, projects_repo,
    )
    trace_id = trace_id_var.get()
    _validate_or_409(
        job.status, "running", trace_id=trace_id,
    )
    updated = await jobs_repo.update_status(user_id, job.job_id, "running")
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job status changed concurrently",
        )
    # Mirror job state back to project.
    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=True,
        extraction_status="building",
    )
    logger.info(
        "K16.4: job resumed job_id=%s trace_id=%s", job.job_id, trace_id,
    )
    return updated


@router.post(
    "/{project_id}/extraction/cancel",
    response_model=ExtractionJob,
)
async def cancel_extraction_job(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> ExtractionJob:
    """Cancel an extraction job. Preserves partial graph.

    Transitions project.extraction_status to 'disabled' per K16.4 spec.
    """
    job = await _get_active_job_for_project(
        user_id, project_id, jobs_repo, projects_repo,
    )
    trace_id = trace_id_var.get()
    _validate_or_409(
        job.status, "cancelled", trace_id=trace_id,
    )
    updated = await jobs_repo.update_status(user_id, job.job_id, "cancelled")
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job status changed concurrently",
        )
    # Update project extraction status — partial graph is preserved.
    # NOTE: this is NOT atomic with the job status update above. If the
    # process crashes between the two, the project stays 'building'
    # pointing at a cancelled job. The job status is the source of truth;
    # the project status is advisory. K16.6 worker should reconcile
    # project state on job completion/cancellation.
    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=False,
        extraction_status="disabled",
    )
    logger.info(
        "K16.4: job cancelled job_id=%s trace_id=%s", job.job_id, trace_id,
    )
    return updated


# ── K16.8 — Delete graph ──────────────────────────────────────────────

# Neo4j labels to delete per project. Relationships attached to these
# nodes are auto-deleted by Neo4j's DETACH DELETE.
_GRAPH_LABELS = ["Entity", "Event", "Fact", "ExtractionSource"]


async def _delete_project_graph(user_id: UUID, project_id: UUID) -> int:
    """Delete all Neo4j nodes for a project. Returns total nodes deleted.

    Shared by K16.8 (delete), K16.9 (rebuild), K16.10 (change model).
    Caller must check neo4j_uri is set before calling.
    NOTE: unbatched DETACH DELETE — see D-K11.9-01.
    """
    deleted_total = 0
    async with neo4j_session() as session:
        for label in _GRAPH_LABELS:
            result = await session.run(
                f"MATCH (n:{label}) "
                "WHERE n.user_id = $user_id AND n.project_id = $project_id "
                "DETACH DELETE n "
                "RETURN count(n) AS deleted",
                user_id=str(user_id),
                project_id=str(project_id),
            )
            record = await result.single()
            deleted_total += record["deleted"] if record else 0
    return deleted_total


@router.delete(
    "/{project_id}/extraction/graph",
    status_code=status.HTTP_200_OK,
)
async def delete_extraction_graph(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> dict:
    """Delete all Neo4j graph data for a project. Keeps raw data.

    Deletes :Entity, :Event, :Fact, :ExtractionSource nodes and all
    their relationships (RELATES_TO, EVIDENCED_BY, etc.) for this
    project. Sets project.extraction_status = 'disabled'.

    Returns 404 if project doesn't exist. Returns 409 if an extraction
    job is currently active (must cancel first).
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # Block delete if an active job exists
    active = await jobs_repo.list_active(user_id)
    for j in active:
        if j.project_id == project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot delete graph while job {j.job_id} is active (status={j.status}); cancel it first",
            )

    if not app_settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured",
        )

    deleted_total = await _delete_project_graph(user_id, project_id)

    # Update project state
    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=False,
        extraction_status="disabled",
    )

    trace_id = trace_id_var.get()
    logger.info(
        "K16.8: graph deleted project_id=%s nodes=%d trace_id=%s",
        project_id, deleted_total, trace_id,
    )

    return {
        "project_id": str(project_id),
        "nodes_deleted": deleted_total,
        "extraction_status": "disabled",
    }


# ── K19a.6 — Disable extraction without deleting the graph ──────────


@router.post(
    "/{project_id}/extraction/disable",
    status_code=status.HTTP_200_OK,
)
async def disable_extraction(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.MANAGE)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> dict:
    """Disable extraction WITHOUT deleting the Neo4j graph.

    Flips ``extraction_enabled=false`` and ``extraction_status='disabled'``
    while preserving all :Entity/:Fact/:Event/:Passage/:ExtractionSource
    nodes. Contrast with:

    - ``DELETE /extraction/graph``: deletes graph + disables (K16.8)
    - ``PUT /embedding-model?confirm=true``: deletes graph + disables +
      switches model (K16.10)

    The preserved graph is still queryable from chat context / wiki
    flows — a disabled project is effectively a frozen-in-time knowledge
    base that won't ingest new content. Re-enabling requires starting a
    new extraction job (which will run against the chosen scope on top
    of the existing graph, treating it as incremental).

    Returns 404 if project doesn't exist or is owned by another user.
    Returns 409 if an active extraction job is running (must cancel first).
    Idempotent: re-calling on an already-disabled project returns the
    current state without touching the DB.
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # Block if an active job exists — mirrors delete-graph / change-model.
    # Cancelling a running job leaves the project in 'disabled' already,
    # so the user shouldn't hit this branch after a normal flow.
    active = await jobs_repo.list_active(user_id)
    for j in active:
        if j.project_id == project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"cannot disable extraction while job {j.job_id} is "
                    f"active (status={j.status}); cancel it first"
                ),
            )

    # Idempotent short-circuit — no-op for an already-disabled project
    # avoids an unnecessary UPDATE and makes the endpoint safe to retry.
    if not project.extraction_enabled:
        return {
            "project_id": str(project_id),
            "extraction_status": project.extraction_status,
            "graph_preserved": True,
            "message": "already disabled",
        }

    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=False,
        extraction_status="disabled",
    )

    trace_id = trace_id_var.get()
    logger.info(
        "K19a.6: extraction disabled (graph preserved) project_id=%s trace_id=%s",
        project_id, trace_id,
    )

    return {
        "project_id": str(project_id),
        "extraction_status": "disabled",
        "graph_preserved": True,
    }


# ── K16.9 — Rebuild (delete graph + start new job) ──────────────────


class RebuildRequest(BaseModel):
    llm_model: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=1, max_length=200)
    max_spend_usd: Annotated[Decimal, Field(ge=0)] | None = None
    # bug #42 — accumulate vs wipe. "replace" (default, back-compat) DELETEs the whole
    # graph then rebuilds scope=all (the destructive path, ?confirm=true gated). "update"
    # does NOT delete — it re-extracts on top of the existing graph via the idempotent
    # MERGE-upsert writes, so a writer can re-generate a specific chapter after an edit, or
    # add new chapters, without losing the rest. `scope`/`scope_range` apply to "update"
    # only (a "replace" always rebuilds everything); `scope="chapters"` +
    # `scope_range={"chapter_range":[from,to]}` is the per-chapter incremental case.
    mode: Literal["replace", "update"] = "replace"
    scope: JobScope = "all"
    scope_range: dict[str, Any] | None = None


@router.post(
    "/{project_id}/extraction/rebuild",
    status_code=status.HTTP_201_CREATED,
)
async def rebuild_extraction(
    project_id: UUID,
    body: RebuildRequest,
    confirm: bool = False,
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    # #9 — count sources for the server-computed items_total denominator.
    book_client: BookClient = Depends(get_book_client),
    pending_repo: ExtractionPendingRepo = Depends(get_extraction_pending_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> ExtractionJob | dict:
    """Rebuild the graph — destructively (``mode="replace"``) or incrementally
    (``mode="update"``, bug #42).

    ``mode="replace"`` (default): deletes the existing graph then starts a full
    ``scope=all`` rebuild. Destructive — without ``?confirm=true`` it returns a
    warning preview with live node counts (``action_required='confirm'``) and
    deletes NOTHING (bug #14); with ``?confirm=true`` it deletes then rebuilds.

    ``mode="update"`` (bug #42): NON-destructive — deletes nothing and needs no
    confirm. Starts an extraction over ``scope``/``scope_range`` (default
    ``scope=all``) that re-extracts ON TOP of the existing graph; the writes are
    idempotent ``MERGE`` upserts (entities/facts/events keyed on a content hash),
    so re-running a chapter accumulates + refreshes rather than duplicating. Use
    ``scope="chapters"`` + ``scope_range={"chapter_range":[from,to]}`` to refresh
    just the chapters a writer edited/added. NOTE: an update adds/refreshes but
    does not RETRACT entities deleted from edited text (MERGE can't remove); a
    full retract path is a separate follow-up.

    The replace delete runs first; if the start fails, the graph is gone but
    the project is in 'disabled' state (user can retry). True cross-DB
    atomicity (Neo4j + Postgres) is not possible without 2PC.
    """
    is_replace = body.mode == "replace"
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # Block if active job exists
    active = await jobs_repo.list_active(user_id)
    for j in active:
        if j.project_id == project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot rebuild while job {j.job_id} is active (status={j.status}); cancel it first",
            )

    if not app_settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured",
        )

    # bug #42 — an "update" rebuild is non-destructive: the destructive ?confirm
    # gate AND the delete are skipped entirely. A "replace" keeps the bug #14
    # behaviour below. The incremental scope/range apply to "update" only.
    eff_scope: JobScope = "all" if is_replace else body.scope
    eff_range = None if is_replace else body.scope_range

    if is_replace:
        # K-DATASAFE (bug #14) — destructive guard: a replace rebuild DELETES the
        # entire graph, so require an explicit ?confirm=true. Without it, return a
        # warning preview carrying the live node counts so the FE can show "this
        # deletes N entities" and demand a typed confirmation (mirrors
        # change_embedding_model). Defense-in-depth: holds even if a caller bypasses
        # the FE confirm dialog.
        if not confirm:
            _params = {"user_id": str(user_id), "project_id": str(project_id)}
            async with neo4j_session() as session:
                _rec = await (await session.run(_GRAPH_STATS_CYPHER, _params)).single()
            return {
                "warning": (
                    "Rebuilding permanently DELETES this project's entire knowledge "
                    "graph and rebuilds it from scratch. This cannot be undone. "
                    "Pass ?confirm=true to proceed."
                ),
                "entity_count": int(_rec["entity_count"] or 0) if _rec else 0,
                "fact_count": int(_rec["fact_count"] or 0) if _rec else 0,
                "event_count": int(_rec["event_count"] or 0) if _rec else 0,
                "action_required": "confirm",
            }

        # Step 1: Delete existing graph (replace only)
        await _delete_project_graph(user_id, project_id)
    else:
        # Validate the incremental range shape up front (mirrors StartJobRequest),
        # so a malformed chapter_range 422s at request time rather than being
        # swallowed by the best-effort count below and surfacing later in the worker.
        _extract_chapter_range(eff_range)

    # Step 2: Start the new job (replace ⇒ scope=all; update ⇒ the caller's scope)
    trace_id = trace_id_var.get()
    # #9 — server-computed progress denominator.
    # Best-effort: a count failure → NULL (indeterminate bar), never blocks the rebuild.
    rebuild_items_total: int | None = None
    try:
        rebuild_items_total = (
            await _count_scope_items(
                eff_scope, eff_range, project, user_id, project_id,
                book_client=book_client,
                pending_repo=pending_repo,
                glossary_client=glossary_client,
            )
        ).total
    except Exception:  # noqa: BLE001 — advisory count; never block the rebuild
        logger.warning(
            "#9: failed to compute items_total for rebuild project_id=%s; storing NULL",
            project_id, exc_info=True,
        )
    validated = ExtractionJobCreate(
        project_id=project_id,
        scope=eff_scope,
        scope_range=eff_range,
        llm_model=body.llm_model,
        embedding_model=body.embedding_model,
        max_spend_usd=body.max_spend_usd,
        items_total=rebuild_items_total,
    )

    job_id = await _create_and_start_job(
        user_id, project_id, validated, projects_repo, trace_id,
    )

    job = await jobs_repo.get(user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="job created but not found on re-read",
        )

    logger.info(
        "K16.9: rebuild started job_id=%s project_id=%s trace_id=%s",
        job_id, project_id, trace_id,
    )
    return job


# ── K16.10 — Change embedding model ─────────────────────────────────


class ChangeEmbeddingModelRequest(BaseModel):
    embedding_model: str = Field(min_length=1, max_length=200)


@router.put(
    "/{project_id}/embedding-model",
    status_code=status.HTTP_200_OK,
)
async def change_embedding_model(
    project_id: UUID,
    body: ChangeEmbeddingModelRequest,
    confirm: bool = False,
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> dict:
    """Change a project's embedding model.

    Without ``?confirm=true``: returns a warning that the change
    requires deleting the existing graph (destructive).

    With ``?confirm=true``: deletes the graph, updates the embedding
    model, and sets extraction_status='disabled'. The user must
    explicitly start a new extraction job afterwards.
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # Block if active job exists
    active = await jobs_repo.list_active(user_id)
    for j in active:
        if j.project_id == project_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot change model while job {j.job_id} is active; cancel it first",
            )

    current_model = project.embedding_model or "(none)"
    new_model = body.embedding_model

    # Same-model no-op guard
    if current_model == new_model:
        return {
            "message": "model unchanged",
            "current_model": current_model,
        }

    if not confirm:
        return {
            "warning": "Changing the embedding model requires deleting the existing knowledge graph. "
                       "The new model also needs its own passing embedding benchmark — you'll have "
                       "to re-run it before you can build the graph again. Pass ?confirm=true to proceed.",
            "current_model": current_model,
            "new_model": new_model,
            "action_required": "confirm",
        }

    # Confirmed — delete graph + update model
    if not app_settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured",
        )

    # D-EMB-MODEL-REF-03 — probe the new model's vector dimension BEFORE
    # the destructive graph delete. `new_model` is a provider-registry
    # `user_model` UUID; the project stores `embedding_dimension`
    # alongside it. A probe failure (provider unreachable, non-embedding
    # model) aborts with 422 — the graph is left intact.
    try:
        new_dim = await probe_embedding_dimension(user_id, new_model)
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"embedding model probe failed: {exc}",
        )
    if new_dim not in SUPPORTED_PASSAGE_DIMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"embedding model has dimension {new_dim}, which has no "
                f":Passage vector index (supported: {sorted(SUPPORTED_PASSAGE_DIMS)})"
            ),
        )

    deleted_total = await _delete_project_graph(user_id, project_id)

    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=new_model,
        embedding_dimension=new_dim,
    )

    # D-KG-PASSAGE-BACKFILL — the embedding model is now set, so passages become
    # ingestable. Backfill any already-PUBLISHED chapters whose `chapter.published`
    # event fired BEFORE this project/model existed (the natural publish-then-setup
    # flow), so wiki/enrichment have grounding without a manual re-publish. The graph
    # delete above also dropped any stale-dimension passages, so a model CHANGE
    # re-ingests at the new dimension here. Best-effort: never fail the model set.
    passages_backfilled = 0
    if project.book_id is not None:
        try:
            from app.clients.book_client import get_book_client
            from app.clients.embedding_client import get_embedding_client
            from app.db.neo4j import neo4j_session
            from app.extraction.passage_ingester import (
                backfill_published_passages,
                backfill_source_lang,
            )

            async with neo4j_session() as session:
                bf = await backfill_published_passages(
                    session,
                    get_book_client(),
                    get_embedding_client(),
                    user_id=user_id,
                    project_id=project_id,
                    book_id=project.book_id,
                    embedding_model=new_model,
                    embedding_dim=new_dim,
                    # KG-ML M1 (C10) — meter the backfill re-embed spend.
                    pool=get_knowledge_pool(),
                    # D-BACKFILL-NO-SCOPE-LIMIT — this backfill runs SYNCHRONOUSLY in the
                    # request; cap it so a large book can't run away embedding every
                    # published chapter inline (0 ⇒ never skip).
                    max_chapters=(app_settings.kg_backfill_max_inline_chapters or None),
                )
                # KG-ML M1 (DD1) — tag-only pass for any passage NOT re-embedded
                # above (e.g. draft-indexed chunks): stamp declared source_lang
                # without re-embedding (bills zero). Idempotent + best-effort.
                await backfill_source_lang(
                    session,
                    get_book_client(),
                    user_id=user_id,
                    book_id=project.book_id,
                )
            passages_backfilled = bf.passages_created
        except Exception:  # noqa: BLE001 — best-effort; the model set already succeeded
            logger.warning(
                "K16.10: passage backfill failed for project=%s — non-fatal",
                project_id, exc_info=True,
            )

    trace_id = trace_id_var.get()
    logger.info(
        "K16.10: embedding model changed project_id=%s %s→%s dim=%d nodes_deleted=%d "
        "passages_backfilled=%d trace_id=%s",
        project_id, current_model, new_model, new_dim, deleted_total,
        passages_backfilled, trace_id,
    )

    return {
        "project_id": str(project_id),
        "previous_model": current_model,
        "new_model": new_model,
        "embedding_dimension": new_dim,
        "nodes_deleted": deleted_total,
        "passages_backfilled": passages_backfilled,
        "extraction_status": "disabled",
    }


# ── K16.5 — Job status + project job list ────────────────────────────

# Separate router for job-level endpoints (not under /projects/{id}).
jobs_router = APIRouter(
    prefix="/v1/knowledge/extraction",
    tags=["extraction"],
    dependencies=[Depends(get_current_user)],
)


def _etag(job: ExtractionJob) -> str:
    """Weak ETag from updated_at timestamp + denormalized fields
    that can drift independently of the job row itself.

    ``updated_at`` bumps on every progress update (advance_cursor), so
    the FE gets 304 during polling when the job hasn't moved. But C6
    (D-K19b.3-01) denormalizes ``current_chapter_title`` in from
    book-service at serve-time — a chapter rename in book-service
    would NOT bump ``extraction_jobs.updated_at``. Hashing the title
    into the etag means FE revalidates when the title changes too.

    /review-impl M1 fix — prior version used only ``updated_at`` and
    would serve 304 with stale chapter title for up to staleTime.
    Uses md5 (not Python's built-in ``hash()``) because PYTHONHASHSEED
    defaults to random per-process → two workers would generate
    different etags for the same state and break the contract.
    md5 here is a non-cryptographic fingerprint, not security-load-
    bearing — 8 hex chars (32 bits) is plenty of collision resistance
    for an etag component.
    """
    import hashlib

    title_component = job.current_chapter_title or ""
    title_hash = hashlib.md5(
        title_component.encode("utf-8"), usedforsecurity=False,
    ).hexdigest()[:8]
    return (
        f'W/"{int(job.updated_at.timestamp() * 1000)}-{title_hash}"'
    )


class ExtractionJobsPage(BaseModel):
    """C11 (D-K19b.1-01) envelope for ``GET /extraction/jobs``. Paired
    with ``next_cursor`` so the FE can advance to more history pages
    without a server-side offset."""

    items: list[ExtractionJob]
    # ``null`` when the last page was returned (fewer than ``limit``
    # rows OR exactly ``limit`` rows but none remain). FE treats null
    # as "hide Load more".
    next_cursor: str | None


@jobs_router.get(
    "/jobs",
    response_model=ExtractionJobsPage,
)
async def list_all_user_jobs(
    status_group: Literal["active", "history"] = Query(
        ...,
        description=(
            "active = pending|running|paused (2s-poll surface); "
            "history = complete|failed|cancelled (slower-poll surface)."
        ),
    ),
    limit: int = Query(50, ge=1, le=LIST_ALL_MAX_LIMIT),
    cursor: str | None = Query(
        None,
        min_length=1,
        max_length=500,
        description=(
            "C11 (D-K19b.1-01) opaque pagination cursor. Copy from the "
            "previous response's ``next_cursor`` to fetch the next page. "
            "Omit for the first page. 422 on malformed cursor."
        ),
    ),
    user_id: UUID = Depends(get_current_user),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    book_client: BookClient = Depends(get_book_client),
) -> ExtractionJobsPage:
    """K19b.1 + C11 — user-scoped cross-project job list, grouped by
    status, with cursor pagination.

    Separate from the per-project ``/projects/{id}/extraction/jobs``:
    that one returns history for a single project, while this one
    powers the Jobs tab's single-page view across all projects. The
    binary `status_group` maps 1:1 to K19b.2's layout sections
    (Running/Paused in active, Complete/Failed/Cancelled in history)
    so the FE can render without client-side filtering.

    C11 (D-K19b.1-01 + D-K19b.2-01): ``cursor`` is an opaque
    base64-JSON the FE copies from the previous response's
    ``next_cursor``. Active group is typically small enough that its
    ``next_cursor`` is always ``null`` in practice; the envelope is
    still used for API consistency across both groups.
    """
    try:
        jobs, next_cursor = await jobs_repo.list_all_for_user(
            user_id, status_group=status_group, limit=limit, cursor=cursor,
        )
    except CursorDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"malformed cursor: {exc}",
        )
    # C6 (D-K19b.3-01) — resolve current_cursor.last_chapter_id titles.
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    return ExtractionJobsPage(items=jobs, next_cursor=next_cursor)


@jobs_router.get(
    "/jobs/{job_id}",
    response_model=ExtractionJob,  # OpenAPI schema only — bypassed when returning Response directly
)
async def get_extraction_job(
    job_id: UUID,
    user_id: UUID = Depends(require_job_grant(GrantLevel.VIEW)),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    book_client: BookClient = Depends(get_book_client),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    """Get detailed status of a specific extraction job.

    Supports If-None-Match for etag-based conditional GET (KSA §6.3).
    Returns 304 if the job hasn't changed since the client's last fetch.
    Cross-user access returns 404 (not 403) per KSA §6.4.
    """
    job = await jobs_repo.get(user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    # C6 (D-K19b.3-01) — resolve current_cursor.last_chapter_id title
    # BEFORE computing the etag. Keeping the enrichment inside the
    # etag window means the ETag reflects the FULL wire shape: a
    # chapter title change on the BOOK side bumps the ETag and the
    # FE's If-None-Match revalidates.
    await enrich_jobs_with_current_chapter_titles([job], book_client)
    etag = _etag(job)
    if if_none_match and if_none_match.strip() == etag:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED)
    return Response(
        content=job.model_dump_json(),
        media_type="application/json",
        headers={"ETag": etag},
    )


# ── C7 raise-cap (KN-7) — PATCH job concurrency in-flight ───────────


class UpdateConcurrencyRequest(BaseModel):
    # Mirrors the create-time bound (StartJobRequest.concurrency_level:
    # ge=1, le=64). The worker re-reads this every poll cycle, so a raise
    # takes effect on the next chapter window without a job restart.
    concurrency_level: Annotated[int, Field(ge=1, le=64)]


@jobs_router.patch(
    "/jobs/{job_id}/concurrency",
    response_model=ExtractionJob,
)
async def update_job_concurrency(
    job_id: UUID,
    body: UpdateConcurrencyRequest,
    # MANAGE mirrors pause/resume/cancel — a collaborator who can manage
    # the project's jobs can also retune the cap. `require_job_grant`
    # returns the project OWNER, which is the row's `user_id` scope.
    owner_id: UUID = Depends(require_job_grant(GrantLevel.MANAGE)),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> ExtractionJob:
    """C7 raise-cap (KN-7): change a running/paused job's parallel-LLM
    concurrency cap IN-FLIGHT. Bounds are enforced by the request model
    (1–64). 404 if the job doesn't exist / isn't accessible; 409 if it
    exists but is in a terminal state (the cap can only be retuned while
    the job is still active)."""
    updated = await jobs_repo.set_concurrency_level(
        owner_id, job_id, body.concurrency_level,
    )
    if updated is not None:
        return updated
    # 0 rows: disambiguate "not found / not accessible" (404) from
    # "exists but terminal" (409) so the FE can message correctly.
    existing = await jobs_repo.get(owner_id, job_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"cannot change concurrency on a {existing.status} job; "
            "only running or paused jobs can be retuned"
        ),
    )


@router.get(
    "/{project_id}/extraction/jobs",
    response_model=list[ExtractionJob],
)
async def list_extraction_jobs(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    book_client: BookClient = Depends(get_book_client),
) -> list[ExtractionJob]:
    """List all extraction jobs for a project (history), newest first."""
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    jobs = await jobs_repo.list_for_project(user_id, project_id)
    # C6 (D-K19b.3-01) — resolve current_cursor.last_chapter_id titles.
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    return jobs


# ── T4.1 Flywheel — net-new delta for the latest completed extraction ──


class FlywheelItemResponse(BaseModel):
    kind: Literal["entity", "event", "relation"]
    id: str
    name: str


class FlywheelDeltaResponse(BaseModel):
    """The canon growth from the most-recent completed extraction job.

    ``has_delta`` is False when no extraction has completed yet (FE renders a
    neutral empty state, not an error). Counts are exact; ``new_items`` is a
    capped named sample with deep-link ids per kind.
    """

    has_delta: bool
    job_id: UUID | None = None
    completed_at: datetime | None = None
    entities_added: int = 0
    relations_added: int = 0
    events_added: int = 0
    new_items: list[FlywheelItemResponse] = Field(default_factory=list)


@router.get(
    "/{project_id}/flywheel",
    response_model=FlywheelDeltaResponse,
)
async def get_flywheel(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> FlywheelDeltaResponse:
    """Net-new entities/relations/events added by the latest COMPLETED
    extraction job for this project (the composition Flywheel panel).

    Reads the ``created_job_id`` stamp (Pass-2 writer, ON CREATE) — so re-runs
    never double-count and re-mentions of existing canon don't inflate the
    delta. Cross-user / nonexistent project → 404 (no existence leak).
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    jobs = await jobs_repo.list_for_project(user_id, project_id)  # newest first
    latest = next((j for j in jobs if j.status == "complete"), None)
    if latest is None:
        return FlywheelDeltaResponse(has_delta=False)

    async with neo4j_session() as session:
        delta = await get_flywheel_delta(
            session, job_id=str(latest.job_id), user_id=str(user_id),
        )
    return FlywheelDeltaResponse(
        has_delta=True,
        job_id=latest.job_id,
        completed_at=latest.completed_at,
        entities_added=delta.entities_added,
        relations_added=delta.relations_added,
        events_added=delta.events_added,
        new_items=[
            FlywheelItemResponse(kind=i.kind, id=i.id, name=i.name)
            for i in delta.new_items
        ],
    )


# ── T2-close-1b-FE — Public benchmark-status ────────────────────────


@router.get(
    "/{project_id}/benchmark-status",
    response_model=BenchmarkStatusResponse,
)
async def get_project_benchmark_status(
    project_id: UUID,
    embedding_model: str | None = None,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    benchmark_repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
) -> BenchmarkStatusResponse:
    """Public (JWT-scoped) read of the latest K17.9 benchmark run for
    a project. Returns the same shape as the internal endpoint so the
    FE picker can render a pass/fail/missing badge when the user
    selects an embedding model.

    Cross-user / nonexistent project → 404 (no existence-leak). Uses
    the same repo method the extraction-start gate uses, so the badge
    never disagrees with the gate's decision.

    `has_run=False` is a valid 200 response (FE renders a neutral
    "no benchmark yet" state, not an error).
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    # D-JOURNEY-KG-BENCHMARK-UX — the badge MUST agree with the extraction-start
    # gate, which is MODEL-scoped: benchmarks run on a hidden per-(user, model)
    # SANDBOX project, so a passing run lives under the sandbox's project_id, NOT
    # this content project. The old project-scoped get_latest never saw the sandbox
    # run, so the badge stayed "no benchmark yet" and the Build button stayed
    # disabled even after a passing benchmark (the "ran it, FE won't update" bug).
    # Use the same model-scoped lookup the gate uses when a model is given; fall
    # back to the project-scoped "has the user ever benchmarked?" read otherwise.
    if embedding_model:
        row = await benchmark_repo.get_latest_for_model(user_id, embedding_model)
    else:
        row = await benchmark_repo.get_latest(user_id, project_id, embedding_model)
    if row is None:
        return BenchmarkStatusResponse(has_run=False)
    return BenchmarkStatusResponse(
        has_run=True,
        passed=row.passed,
        run_id=row.run_id,
        embedding_model=row.embedding_model,
        recall_at_3=row.recall_at_3,
        mrr=row.mrr,
        created_at=row.created_at,
        gate_failures=gate_failures_from_raw(row.raw_report),
    )


# ── C12b-a — Public benchmark-run (on-demand POST) ──────────────────


class BenchmarkRunRequest(BaseModel):
    """Body for ``POST /{project_id}/benchmark-run``.

    ``runs`` controls how many passes the harness averages over.
    Default 3 matches the CLI default (L-CH-09 methodology). Upper
    bound 5 caps the sync request duration; higher run counts are a
    CLI-only operator concern.
    """

    runs: int = Field(
        default=3, ge=1, le=5,
        description="Number of benchmark passes to average over.",
    )


class BenchmarkRunResponse(BaseModel):
    """Returned on successful POST. Mirrors the projection of
    ``BenchmarkReport`` that the FE needs to render a result card; the
    full ``raw_report`` (per-query breakdown) stays in
    ``project_embedding_benchmark_runs`` and is reachable via
    ``GET /benchmark-status`` → ``benchmark_repo.get_latest`` on the
    internal surface."""

    run_id: str
    embedding_model: str
    passed: bool
    recall_at_3: float
    mrr: float
    avg_score_positive: float
    negative_control_max_score: float
    stddev_recall: float
    stddev_mrr: float
    runs: int
    # R2 — named failing gates (empty == passed). `insufficient_runs` means the
    # run was inconclusive (too few passes), NOT that the model is low-quality;
    # the FE keys its copy off this instead of guessing from `passed` alone.
    gate_failures: list[str] = []


@router.post(
    "/{project_id}/benchmark-run",
    response_model=BenchmarkRunResponse,
    status_code=status.HTTP_200_OK,
)
async def run_project_benchmark_endpoint(
    project_id: UUID,
    body: BenchmarkRunRequest | None = None,
    # D-E0-3-CALLER-PAYS-EXTRACTION (secure-closure): OWNER-ONLY (was EDIT). The
    # benchmark spends embedding-provider calls on the project's model; under
    # resolve-to-owner a collaborator's run billed the OWNER's key. Owner-only
    # closes it; a collaborator inherits the owner's passing benchmark via the
    # vector-space (dimension) match in the caller-pays follow-up.
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> BenchmarkRunResponse:
    """C12b-a — run the K17.9 benchmark against a dedicated project.

    Pre-flight (409 with ``error_code``):
      - ``no_embedding_model`` — project has no ``embedding_model`` set
      - ``unknown_embedding_model`` — model not in the dim map
      - ``not_benchmark_project`` — project already has real
        (chapter/chat/glossary) passages. K17.9 assumes a dedicated
        benchmark project per ``eval/fixture_loader.py``.
      - ``benchmark_already_running`` — per-project sentinel is held

    Runtime failure (502 with ``error_code``):
      - ``embedding_provider_flake`` — fixture load embedded fewer
        entities than the golden set (usually a flaky BYOK provider).
        We refuse to persist a run against an incomplete fixture —
        the low recall would look like a retrieval regression.

    Cross-user / missing project → 404 (no existence-leak, KSA §6.4).
    ``runs`` is capped to 1..5 by the request body Pydantic validation.

    The endpoint is synchronous (typical runtime 15-60s). The FE
    should disable the button while in-flight; we don't background
    the work because a benchmark that fails mid-run without an obvious
    owning task is worse UX than a long-running request.
    """
    # Local imports keep the module-load surface of extraction.py
    # minimal — the benchmark runner pulls in the eval harness, which
    # we don't want to import unless this endpoint is actually called.
    from app.benchmark.runner import (
        BenchmarkAlreadyRunningError,
        FixtureLoadIncompleteError,
        NoEmbeddingModelError,
        NotBenchmarkProjectError,
        UnknownEmbeddingModelError,
        run_project_benchmark,
    )
    from app.clients.embedding_client import get_embedding_client

    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    # R1 (D-JOURNEY-KG-BENCHMARK-UX) — the benchmark validates the embedding
    # MODEL, so it runs on a hidden per-(user, model) SANDBOX, never on this
    # content-bearing build project. That removes the not_benchmark_project
    # dead-end (the sandbox is always empty) and keeps the ~10 synthetic fixture
    # passages out of the real project's vector space. The model-scoped gate then
    # finds the passing run for any project using this model.
    if not project.embedding_model or not project.embedding_dimension:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "no_embedding_model"},
        )
    sandbox = await projects_repo.get_or_create_benchmark_sandbox(
        user_id, project.embedding_model, project.embedding_dimension,
    )

    req = body or BenchmarkRunRequest()
    pool = get_knowledge_pool()
    embedding_client = get_embedding_client()

    try:
        result = await run_project_benchmark(
            user_id=user_id,
            project_id=sandbox.project_id,
            runs=req.runs,
            pool=pool,
            projects_repo=projects_repo,
            embedding_client=embedding_client,
        )
    except NoEmbeddingModelError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "no_embedding_model"},
        )
    except UnknownEmbeddingModelError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "unknown_embedding_model"},
        )
    except NotBenchmarkProjectError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "not_benchmark_project"},
        )
    except BenchmarkAlreadyRunningError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "benchmark_already_running"},
        )
    except FixtureLoadIncompleteError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "embedding_provider_flake"},
        )

    return BenchmarkRunResponse(
        run_id=result.run_id,
        embedding_model=result.embedding_model,
        passed=result.passed,
        recall_at_3=result.recall_at_3,
        mrr=result.mrr,
        avg_score_positive=result.avg_score_positive,
        negative_control_max_score=result.negative_control_max_score,
        stddev_recall=result.stddev_recall,
        stddev_mrr=result.stddev_mrr,
        runs=result.runs,
        gate_failures=list(result.gate_failures),
    )


# ── K19a.4 — Graph stats (supports the FE ProjectStateCard) ──────────


class GraphStatsResponse(BaseModel):
    project_id: UUID
    entity_count: int = 0
    fact_count: int = 0
    event_count: int = 0
    passage_count: int = 0
    last_extracted_at: Any = None  # datetime | None; serialises to ISO-8601


_GRAPH_STATS_CYPHER = """
CALL {
  MATCH (e:Entity {user_id: $user_id, project_id: $project_id})
  RETURN count(e) AS entity_count, 0 AS fact_count,
         0 AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (f:Fact {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, count(f) AS fact_count,
         0 AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (ev:Event {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, 0 AS fact_count,
         count(ev) AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (p:Passage {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, 0 AS fact_count,
         0 AS event_count, count(p) AS passage_count
}
RETURN sum(entity_count) AS entity_count, sum(fact_count) AS fact_count,
       sum(event_count) AS event_count, sum(passage_count) AS passage_count
"""


@router.get(
    "/{project_id}/graph-stats",
    response_model=GraphStatsResponse,
)
async def get_project_graph_stats(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> GraphStatsResponse:
    """K19a.4 — count :Entity/:Fact/:Event/:Passage nodes scoped to the
    (user, project) pair for the Track 3 ProjectStateCard stats line.

    Returns zeros + `last_extracted_at=null` when the project has no
    extraction history (graph is empty); callers render a "Ready"-style
    state anyway because `extraction_enabled + status=complete` is the
    authoritative signal. Cross-user access → 404.
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    params = {"user_id": str(user_id), "project_id": str(project_id)}
    async with neo4j_session() as session:
        result = await session.run(_GRAPH_STATS_CYPHER, params)
        record = await result.single()
    if record is None:
        return GraphStatsResponse(
            project_id=project_id,
            last_extracted_at=project.last_extracted_at,
        )
    return GraphStatsResponse(
        project_id=project_id,
        entity_count=int(record["entity_count"] or 0),
        fact_count=int(record["fact_count"] or 0),
        event_count=int(record["event_count"] or 0),
        passage_count=int(record["passage_count"] or 0),
        last_extracted_at=project.last_extracted_at,
    )
