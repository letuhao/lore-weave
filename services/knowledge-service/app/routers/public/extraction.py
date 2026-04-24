"""K16.2–K16.8 — Extraction lifecycle endpoints under /v1/knowledge/projects/{id}/extraction.

K16.2: cost estimation. K16.3: start. K16.4: pause/resume/cancel.
K16.5: job status. K16.8: delete graph.

Authentication: JWT via router-level + per-route dependency (same
pattern as projects.py — see the double-dependency note there).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient
from app.clients.chapter_title_enricher import (
    enrich_jobs_with_current_chapter_titles,
)
from app.clients.glossary_client import GlossaryClient
from app.config import settings as app_settings
from app.pricing import cost_per_token
from app.db.neo4j import neo4j_session
from app.db.pool import get_knowledge_pool
from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.routers.internal_benchmark import BenchmarkStatusResponse
from app.db.repositories.extraction_jobs import (
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
    get_glossary_client,
    get_projects_repo,
)
from app.jobs.budget import can_start_job, check_user_monthly_budget
from app.jobs.state_machine import JobStatus, PauseReason, StateTransitionError, validate_transition
from app.logging_config import trace_id_var
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

    **Runner note (D-K16.2-02b):** the knowledge-service extraction
    path is event-driven (chapter.saved → passage_ingester), so the
    runner does not yet honour `chapter_range` — only the preview
    count does. A future cycle must either:

      (a) apply chapter_range as a filter inside the chapter.saved
          event handler, OR
      (b) switch the job model from event-reactive to batch-iterative
          and drive chapter fetch from this range.

    Until then, the estimate may under-report what the job will
    actually process. `max_spend_usd` (K10.4 atomic try_spend) remains
    the real financial guard.
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

JobScope = Literal["chapters", "chat", "glossary_sync", "all"]


class EstimateRequest(BaseModel):
    scope: JobScope
    # D-K16.2-02 — `{"chapter_range": [from, to]}` (inclusive,
    # sort_order-based ints). Forwarded to book-service so the preview
    # reflects the filtered chapter count. See `_extract_chapter_range`
    # for the runner-side gap (D-K16.2-02b) — chapter_range affects
    # preview only until the event-driven runner honours it too.
    scope_range: dict | None = None
    llm_model: str = Field(min_length=1, max_length=200)


class StartJobRequest(BaseModel):
    scope: JobScope
    # Same shape as `EstimateRequest.scope_range`. Validated via
    # `_extract_chapter_range` at request time so the DB never stores
    # a malformed shape that the estimate path would have rejected.
    scope_range: dict[str, Any] | None = None
    llm_model: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=1, max_length=200)
    max_spend_usd: Annotated[Decimal, Field(ge=0)] | None = None
    items_total: Annotated[int, Field(ge=0)] | None = None


class EstimateItemCounts(BaseModel):
    chapters: int = 0
    chat_turns: int = 0
    glossary_entities: int = 0


class EstimateResponse(BaseModel):
    items_total: int
    items: EstimateItemCounts
    estimated_tokens: int
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
    user_id: UUID = Depends(get_current_user),
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

    chapters = 0
    chat_turns = 0
    glossary_entities = 0

    scope = body.scope

    chapter_from, chapter_to = _extract_chapter_range(body.scope_range)

    # Chapter count — via book-service internal API
    if scope in ("chapters", "all") and project.book_id is not None:
        count = await book_client.count_chapters(
            project.book_id,
            from_sort=chapter_from,
            to_sort=chapter_to,
        )
        chapters = count if count is not None else 0

    # Pending chat turns — from extraction_pending queue
    if scope in ("chat", "all"):
        chat_turns = await pending_repo.count_pending(user_id, project_id)

    # Glossary entity count — via glossary-service internal API
    if scope in ("glossary_sync", "all") and project.book_id is not None:
        count = await glossary_client.count_entities(project.book_id)
        glossary_entities = count if count is not None else 0

    items_total = chapters + chat_turns + glossary_entities
    estimated_tokens = (
        chapters * _TOKENS_PER_CHAPTER
        + chat_turns * _TOKENS_PER_CHAT_TURN
        + glossary_entities * _TOKENS_PER_GLOSSARY_ENTITY
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
    pool = get_knowledge_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                job_row = await conn.fetchrow(
                    """
                    INSERT INTO extraction_jobs
                      (user_id, project_id, scope, scope_range, llm_model,
                       embedding_model, max_spend_usd, items_total)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
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
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    benchmark_repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
) -> ExtractionJob:
    """Create and start an extraction job for a project.

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

    Worker notification (Redis) is deferred to K16.6 — the worker
    polls for pending/running jobs.
    """
    # 0. Validate scope_range.chapter_range shape (review-impl MED #2).
    # Raises 422 on malformed payloads so the DB never stores a shape
    # the estimate path would have rejected.
    _extract_chapter_range(body.scope_range)

    # 1. Verify project exists and belongs to user
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
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
    latest_benchmark = await benchmark_repo.get_latest(
        user_id, project_id, embedding_model=body.embedding_model,
    )
    if latest_benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "benchmark_missing",
                "message": (
                    f"no passing benchmark run for embedding_model "
                    f"{body.embedding_model!r}; run the golden-set "
                    "benchmark for this model before enabling extraction"
                ),
                "embedding_model": body.embedding_model,
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
                "embedding_model": body.embedding_model,
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

    user_check = await check_user_monthly_budget(pool, user_id, estimated_cost)
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

    # 3. Validate + create job atomically.
    trace_id = trace_id_var.get()
    validated = ExtractionJobCreate(
        project_id=project_id,
        scope=body.scope,
        llm_model=body.llm_model,
        embedding_model=body.embedding_model,
        max_spend_usd=body.max_spend_usd,
        scope_range=body.scope_range,
        items_total=body.items_total,
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
    # TODO: add a project-scoped active-job lookup if this becomes a
    # performance concern. list_active fetches all active jobs across
    # all projects; fine at hobby scale (unique index limits one per project).
    active = await jobs_repo.list_active(user_id)
    for j in active:
        if j.project_id == project_id:
            return j
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
    user_id: UUID = Depends(get_current_user),
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
    user_id: UUID = Depends(get_current_user),
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
    user_id: UUID = Depends(get_current_user),
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
    user_id: UUID = Depends(get_current_user),
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
    user_id: UUID = Depends(get_current_user),
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


@router.post(
    "/{project_id}/extraction/rebuild",
    response_model=ExtractionJob,
    status_code=status.HTTP_201_CREATED,
)
async def rebuild_extraction(
    project_id: UUID,
    body: RebuildRequest,
    user_id: UUID = Depends(get_current_user),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> ExtractionJob:
    """Delete the existing graph and start a full extraction rebuild.

    Combines K16.8 (delete graph) + K16.3 (start job with scope=all).
    The delete runs first; if the start fails, the graph is gone but
    the project is in 'disabled' state (user can retry). True cross-DB
    atomicity (Neo4j + Postgres) is not possible without 2PC.
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
                detail=f"cannot rebuild while job {j.job_id} is active (status={j.status}); cancel it first",
            )

    if not app_settings.neo4j_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j not configured",
        )

    # Step 1: Delete existing graph
    await _delete_project_graph(user_id, project_id)

    # Step 2: Start new job with scope=all via shared helper
    trace_id = trace_id_var.get()
    validated = ExtractionJobCreate(
        project_id=project_id,
        scope="all",
        llm_model=body.llm_model,
        embedding_model=body.embedding_model,
        max_spend_usd=body.max_spend_usd,
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
    user_id: UUID = Depends(get_current_user),
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
                       "Pass ?confirm=true to proceed.",
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

    deleted_total = await _delete_project_graph(user_id, project_id)

    await projects_repo.set_extraction_state(
        user_id, project_id,
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=new_model,
    )

    trace_id = trace_id_var.get()
    logger.info(
        "K16.10: embedding model changed project_id=%s %s→%s nodes_deleted=%d trace_id=%s",
        project_id, current_model, new_model, deleted_total, trace_id,
    )

    return {
        "project_id": str(project_id),
        "previous_model": current_model,
        "new_model": new_model,
        "nodes_deleted": deleted_total,
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
    user_id: UUID = Depends(get_current_user),
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


@router.get(
    "/{project_id}/extraction/jobs",
    response_model=list[ExtractionJob],
)
async def list_extraction_jobs(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
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


# ── T2-close-1b-FE — Public benchmark-status ────────────────────────


@router.get(
    "/{project_id}/benchmark-status",
    response_model=BenchmarkStatusResponse,
)
async def get_project_benchmark_status(
    project_id: UUID,
    embedding_model: str | None = None,
    user_id: UUID = Depends(get_current_user),
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
  RETURN 0, count(f), 0, 0
  UNION ALL
  MATCH (ev:Event {user_id: $user_id, project_id: $project_id})
  RETURN 0, 0, count(ev), 0
  UNION ALL
  MATCH (p:Passage {user_id: $user_id, project_id: $project_id})
  RETURN 0, 0, 0, count(p)
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
    user_id: UUID = Depends(get_current_user),
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
