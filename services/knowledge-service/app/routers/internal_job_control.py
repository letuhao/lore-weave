"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/knowledge/jobs/{job_id}/{action}` (action ∈ cancel|pause|resume)
— the `job_id`-keyed control surface the central **jobs-service** routes user
control actions to. jobs-service has already verified the caller owns the job
(against its projection) + that the action is valid for the job's state; THIS
endpoint **re-verifies ownership on the actual `extraction_jobs` row** (spec M4 —
never trust the projection's possibly-stale owner) by loading via the
owner-scoped `ExtractionJobsRepo.get(owner, job_id)` (→ 404 if not owned/found),
then reuses the K16.4 transition (`_validate_or_409` + `update_status`) and the
project-state mirror. Internal-token + asserted `owner_user_id` in the body;
S2S only, never gateway-exposed.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_extraction_jobs_repo, get_projects_repo
from app.middleware.internal_auth import require_internal_token
from app.middleware.trace_id import trace_id_var
from app.routers.public.extraction import _validate_or_409

router = APIRouter(
    prefix="/internal/knowledge/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)

# action → (target canonical status, pause_reason, project extraction_status mirror,
#           project extraction_enabled). Mirrors the K16.4 public pause/resume/cancel.
_ACTIONS = {
    "cancel": ("cancelled", None, "disabled", False),
    "pause": ("paused", "user", "paused", True),
    "resume": ("running", None, "building", True),
}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-checked
    # against the row here — M4.
    owner_user_id: UUID


class JobControlResponse(BaseModel):
    job_id: UUID
    status: str


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_extraction_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> JobControlResponse:
    if action not in _ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNKNOWN_ACTION", "message": f"unknown action: {action}"},
        )
    target, pause_reason, proj_status, proj_enabled = _ACTIONS[action]

    # M4 — re-verify ownership on the row: get() is owner-scoped, so a job not
    # owned by the asserted user simply isn't found (404, never a cross-tenant act).
    job = await jobs_repo.get(payload.owner_user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )

    trace_id = trace_id_var.get()
    _validate_or_409(job.status, target, trace_id=trace_id, pause_reason=pause_reason)
    updated = await jobs_repo.update_status(payload.owner_user_id, job_id, target)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED", "message": "job status changed concurrently"},
        )
    # Mirror to the project so the FE reflects the new state (advisory; the job
    # row is the SoT — same non-atomic note as the K16.4 public cancel).
    await projects_repo.set_extraction_state(
        payload.owner_user_id, job.project_id,
        extraction_enabled=proj_enabled, extraction_status=proj_status,
    )
    return JobControlResponse(job_id=updated.job_id, status=updated.status)
