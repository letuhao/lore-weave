"""K16.2–K16.3 — Extraction lifecycle endpoints under /v1/knowledge/projects/{id}/extraction.

K16.2: cost estimation. K16.3: start extraction job.
K16.4–K16.10 will add pause/resume/cancel/delete/rebuild.

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
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.db.pool import get_knowledge_pool
from app.db.repositories.extraction_jobs import (
    ExtractionJob,
    ExtractionJobCreate,
    ExtractionJobsRepo,
)
from app.db.repositories.extraction_pending import ExtractionPendingRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_book_client,
    get_extraction_jobs_repo,
    get_extraction_pending_repo,
    get_glossary_client,
    get_projects_repo,
)
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

# Rough per-token cost for preview. This is a placeholder until
# provider-registry exposes model pricing (D-K16.2-01).
_DEFAULT_COST_PER_TOKEN = Decimal("0.000002")  # ~$2/M tokens

# Seconds per item estimate for duration preview.
_SECONDS_PER_ITEM = 2


# ── Request / response models ───────────────────────────────────────

JobScope = Literal["chapters", "chat", "glossary_sync", "all"]


class EstimateRequest(BaseModel):
    scope: JobScope
    scope_range: dict | None = None
    llm_model: str = Field(min_length=1, max_length=200)


class StartJobRequest(BaseModel):
    scope: JobScope
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

    # TODO(K16.2): scope_range is accepted but not yet forwarded to
    # data sources. Book-service's internal chapters endpoint does not
    # support range filtering yet. Tracked as D-K16.2-02 in
    # SESSION_PATCH. The field is kept on the request model so the
    # frontend can start sending it without a contract change when
    # filtering lands.

    # Chapter count — via book-service internal API
    if scope in ("chapters", "all") and project.book_id is not None:
        count = await book_client.count_chapters(project.book_id)
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

    base_cost = Decimal(estimated_tokens) * _DEFAULT_COST_PER_TOKEN
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
) -> ExtractionJob:
    """Create and start an extraction job for a project.

    Atomically: creates the job row, updates the project's extraction
    state to 'building', and transitions the job to 'running' — all
    in a single DB transaction. Returns 409 if another active job
    already exists for this project.

    Worker notification (Redis) is deferred to K16.6 — the worker
    polls for pending/running jobs.
    """
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

    # 3. Atomic transaction: create job + update project + transition to running.
    # Concurrency guard: the unique partial index
    # idx_extraction_jobs_one_active_per_project (K16.3 migration)
    # prevents two concurrent starts from both succeeding — the second
    # INSERT hits a UniqueViolationError which we map to 409.
    trace_id = trace_id_var.get()

    # Validate fields via Pydantic before touching the DB. The INSERT
    # uses conn directly (not jobs_repo.create) so the transaction
    # spans both the job INSERT and the project UPDATE atomically.
    validated = ExtractionJobCreate(
        project_id=project_id,
        scope=body.scope,
        llm_model=body.llm_model,
        embedding_model=body.embedding_model,
        max_spend_usd=body.max_spend_usd,
        scope_range=body.scope_range,
        items_total=body.items_total,
    )

    pool = get_knowledge_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 3a. Create job in pending state
                insert_query = """
                INSERT INTO extraction_jobs
                  (user_id, project_id, scope, scope_range, llm_model,
                   embedding_model, max_spend_usd, items_total)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
                RETURNING job_id
                """
                job_row = await conn.fetchrow(
                    insert_query,
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

                # 3b. Update project extraction state
                updated_project = await projects_repo.set_extraction_state(
                    user_id, project_id,
                    extraction_enabled=True,
                    extraction_status="building",
                    embedding_model=body.embedding_model,
                    conn=conn,
                )
                if updated_project is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="project vanished during transaction",
                    )

                # 3c. Transition job: pending → running
                validate_transition(
                    "pending", "running", trace_id=trace_id,
                )
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
