"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/composition/jobs/{job_id}/{action}` — the `job_id`-keyed control
surface the central **jobs-service** routes user control actions to. composition
`generation_job`s are single-call (one compose/critic LLM round) → **cancel-only**
(no pause/resume — the jobs-service caps-gate already blocks those for this kind;
we 400 defensively in case the registry drifts). jobs-service has verified the
caller owns the job against its projection; THIS endpoint **re-verifies ownership
on the actual `generation_job` row** (spec M4 — never trust the projection's
possibly-stale owner) via the owner-scoped `GenerationJobsRepo.get`, then
CAS-cancels (race-safe — never clobbers a job that completed in the meantime).
Internal-token + asserted `owner_user_id` in the body; S2S only, never gateway-exposed.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.deps import get_generation_jobs_repo
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/composition/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-checked
    # against the row here — M4.
    owner_user_id: UUID


class JobControlResponse(BaseModel):
    job_id: UUID
    status: str


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_generation_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> JobControlResponse:
    # Single-call kind → cancel-only. pause/resume are never valid here.
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNSUPPORTED_ACTION",
                    "message": f"composition jobs support only 'cancel', not '{action}'"},
        )
    # M4 — re-verify ownership on the real row: get() is owner-scoped, so a job not
    # owned by the asserted user simply isn't found (404, never a cross-tenant act).
    job = await jobs.get(payload.owner_user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    # CAS cancel — only from an active state. None ⇒ already terminal (or raced to
    # terminal between the get and here); the job row is authoritative → 409.
    cancelled = await jobs.cancel(payload.owner_user_id, job_id)
    if cancelled is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED",
                    "message": f"job not cancellable from status '{job.status}'"},
        )
    return JobControlResponse(job_id=cancelled.id, status=cancelled.status)
