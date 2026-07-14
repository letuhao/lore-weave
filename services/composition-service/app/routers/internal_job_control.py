"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/composition/jobs/{job_id}/{action}` — the `job_id`-keyed control
surface the central **jobs-service** routes user control actions to. composition
`generation_job`s are single-call (one compose/critic LLM round) → **cancel-only**
(no pause/resume — the jobs-service caps-gate already blocks those for this kind;
we 400 defensively in case the registry drifts). jobs-service has verified the
caller owns the job against its projection; THIS endpoint **re-verifies ownership
on the actual `generation_job` row** (spec M4 — never trust the projection's
possibly-stale owner). Post book-package re-key (spec 25 PM-5/PM-9)
`GenerationJobsRepo.get` is BARE-ID (its old owner-scoping leg is gone), so we load
by id and then **EXPLICITLY assert the row's `created_by` matches the asserted
principal** — the same uniform 404 the old owner-scoped `get`'s None-return produced
— before CAS-cancelling (race-safe — never clobbers a job that completed in the
meantime). That re-scope-to-parent assert is load-bearing: without it any internal
caller could drive ANY job by id (worker-loaded-id-needs-parent-scoping).
Internal-token + asserted `owner_user_id` in the body; S2S only, never gateway-exposed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.clients.model_name import resolve_model_name
from app.config import settings
from app.db.repositories import ChapterJobInFlightError, ReferenceViolationError
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.deps import get_generation_jobs_repo
from app.middleware.internal_auth import require_internal_token
from app.worker.constants import is_worker_drivable, worker_op_of
from app.worker.events import enqueue_job

router = APIRouter(
    prefix="/internal/composition/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("")
async def reconcile_jobs(
    since: datetime = Query(..., description="ISO-8601 — rows updated at/after this"),
    limit: int = Query(1000, ge=1, le=5000, description="page cap — the sweeper's _PAGE_LIMIT"),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): all generation jobs
    updated since `since` (oldest-first, capped at `limit`), in canonical `JobEvent`
    payload shape, for the jobs-service sweep to upsert (heals outbox drift). A full page
    signals the sweeper to continue from the last row rather than skip the overflow.
    Internal-token (router dep); ALL owners — user-scoping is at the jobs-service read API."""
    rows = await jobs.list_since(since, limit=limit)
    return {"jobs": [
        {
            # Wire key stays literally "owner_user_id" (jobs-service projection
            # contract); its VALUE now sources the actor stamp `created_by` (PM-5).
            "service": "composition", "job_id": str(j.id), "owner_user_id": str(j.created_by),
            "kind": j.operation, "status": j.status, "parent_job_id": None,
            "detail_status": None, "progress": None, "title": None, "error": None,
            "occurred_at": j.updated_at.isoformat() if j.updated_at else None,
        }
        for j in rows
    ]}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-checked
    # against the row here — M4.
    owner_user_id: UUID


class JobControlResponse(BaseModel):
    job_id: UUID
    status: str


async def _retry_generation_job_core(
    job_id: UUID, payload: "JobControlPayload", jobs: GenerationJobsRepo,
) -> JobControlResponse:
    """Re-submit a FAILED, worker-drivable composition job as a NEW job
    (D-JOBS-P4-RETRY-COMPOSITION). The failed row stays as history — mirrors
    extraction/video_gen retry. Only worker-drivable jobs are retryable: their
    persisted ``input`` carries the full bearer-resolved context the worker re-runs
    from (the inline/streamed cowrite path packs its prompt live → not on the row →
    not retryable here; the FE re-generate is that surface).

    Order: 404 if missing OR not owned by the asserted principal (bare-id get +
    explicit `created_by` assert — the parent-scope guard the post-re-key bare-id
    repo no longer does) → 409 unless `failed` → 409 if not worker-drivable
    (re-checked on the REAL row, not trusting the projection flag) → 409 if the
    worker is disabled (a re-submitted job would sit `pending` with no consumer —
    don't offer a control we can't honor now) → create a new `pending` job copying
    operation/mode/node/input (NEVER the idempotency_key — copying it would
    replay→return the SAME failed row via ON CONFLICT) → enqueue."""
    # get() is bare-id post-re-key (PM-5/PM-9); the owner leg that used to scope this
    # read is gone, so re-scope to the asserted principal HERE — else any internal
    # caller could drive ANY job by id. Missing OR foreign → the same uniform 404 the
    # old owner-scoped None-return produced (no existence/owner oracle).
    job = await jobs.get(job_id)
    if job is None or job.created_by != payload.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_NOT_FAILED",
                    "message": f"only a failed job can be retried, not '{job.status}'"},
        )
    if not is_worker_drivable(job.operation, job.input):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_NOT_RETRYABLE",
                    "message": "this job's prompt was streamed inline and not persisted; "
                               "it cannot be re-run server-side"},
        )
    if not settings.composition_worker_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_WORKER_DISABLED",
                    "message": "the composition worker is disabled; retry cannot run"},
        )

    op = worker_op_of(job.operation, job.input)
    if op in ("chapter_generate", "stitch_chapter"):
        # Both chapter-draft writers (single-pass generate + per-scene stitch) write
        # the SAME book chapter draft → honor the in-flight guard (O3) on retry too: a
        # concurrent active chapter job 409s, consistent with the create path (engine.py
        # routes both through create_chapter_job_guarded). /review-impl MED-2.
        chapter_id = (job.input or {}).get("chapter_id")
        if not chapter_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "JOBS_NOT_RETRYABLE",
                        "message": "chapter job missing chapter_id in input"},
            )
        try:
            new, _created = await jobs.create_chapter_job_guarded(
                job.project_id, UUID(str(chapter_id)), created_by=job.created_by,
                operation=job.operation, mode=job.mode, status="pending",
                input=job.input, idempotency_key=None,
                stale_secs=settings.chapter_inflight_stale_secs,
                # Resolve the model NAME out-of-tx (the guarded create holds a row
                # lock and won't self-resolve) so the new job's emit carries it.
                model_name=await resolve_model_name(
                    (job.input or {}).get("model_source"), (job.input or {}).get("model_ref")),
            )
        except ChapterJobInFlightError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CHAPTER_JOB_IN_FLIGHT", "active_job_id": exc.active_job_id},
            )
    elif job.project_id is None:
        # BE-7c — an UNBOUND (Work-LESS) job: a corpus/book motif-mine or an arc-import.
        # These ARE worker-drivable (they're in SUPPORTED_OPERATIONS and carry `worker_op`),
        # so retryable=True and the Retry button is live for them. They must re-submit
        # through the SAME Work-less writer the confirm path uses — the plain create()
        # derives book_id from composition_work, so it would raise ReferenceViolationError
        # and 409 with a lie about a deleted outline node.
        new = await jobs.create_unbound(
            created_by=job.created_by, operation=job.operation,
            input=job.input, status="pending",
        )
    else:
        # Plain create self-resolves the model name (conn is None) from the input.
        # create() re-validates the copied outline_node_id is a node in this project; if
        # that node was deleted since the job failed, the draft can't be re-attached → 409
        # (not a 500). selection_edit worker jobs carry outline_node_id=None (the scene is
        # grounding-only), so they skip this check.
        try:
            new, _created = await jobs.create(
                job.project_id, created_by=job.created_by, operation=job.operation,
                outline_node_id=job.outline_node_id, mode=job.mode, status="pending",
                input=job.input, idempotency_key=None,
            )
        except ReferenceViolationError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "JOBS_NOT_RETRYABLE",
                        "message": "the job's outline node no longer exists"},
            )

    # Best-effort enqueue (the row persists either way; the sweeper re-drives a
    # missed trigger — same contract as the create path's enqueue).
    await enqueue_job(
        # `user_id` is the worker-trigger STREAM field (the acting user the worker
        # resolves BYOK/bearer for); its value now sources the actor stamp `created_by`.
        settings.redis_url, job_id=str(new.id),
        user_id=str(job.created_by),
        # An unbound job has no project — send "" (not the string "None"). run_job
        # re-loads the job by id and never reads this field.
        project_id=str(job.project_id) if job.project_id is not None else "",
    )
    return JobControlResponse(job_id=new.id, status=new.status)


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_generation_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> JobControlResponse:
    # Single-call kind → cancel + retry only. pause/resume are never valid here.
    if action == "retry":
        return await _retry_generation_job_core(job_id, payload, jobs)
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNSUPPORTED_ACTION",
                    "message": f"composition jobs support only 'cancel'/'retry', not '{action}'"},
        )
    # M4 — re-verify ownership on the real row. get() is BARE-ID post-re-key
    # (PM-5/PM-9): the owner leg that used to scope this read is gone, so re-scope to
    # the asserted principal HERE with an explicit `created_by` assert — else any
    # internal caller could drive ANY job by id. Missing OR foreign → the same uniform
    # 404 (never a cross-tenant act, never an existence/owner oracle).
    job = await jobs.get(job_id)
    if job is None or job.created_by != payload.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    # CAS cancel — only from an active state; by-id now that ownership is asserted
    # above. None ⇒ already terminal (or raced to terminal between the get and here);
    # the job row is authoritative → 409.
    cancelled = await jobs.cancel(job_id)
    if cancelled is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED",
                    "message": f"job not cancellable from status '{job.status}'"},
        )
    return JobControlResponse(job_id=cancelled.id, status=cancelled.status)
