"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/video_gen/jobs/{job_id}/{action}` — the `job_id`-keyed control
surface the central **jobs-service** routes user control actions to. A video-gen
job is a single provider call → **cancel-only** (no pause/resume). jobs-service
has verified the caller owns the job against its projection; THIS endpoint
**re-verifies ownership on the actual `video_gen_jobs` row** (spec M4) via the
owner-scoped `VideoGenJobsRepo.get`, then CAS-cancels via the existing
`fail(status='cancelled')` (only transitions from an active state).

A provider generation that completes AFTER a cancel is harmlessly ignored — the
consumer's `complete()` CAS won't fire on an already-`cancelled` row, so there is
no resurrection and no double-bill. Proactively aborting the in-flight provider
job to reclaim its gateway slot/cost is a later enhancement
(D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT). Internal-token S2S only; the asserted
`owner_user_id` rides in the body and is re-checked here.

Job rows exist only in the decoupled path (the pool is brought up iff
`video_gen_decouple_enabled`). When stateless, there are no rows to control —
`get_pool()` raising is mapped to a 404 (nothing to cancel), never a 500.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from ..config import settings
from ..db.pool import get_pool
from ..db.repository import VideoGenJobsRepo


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token"
        )


router = APIRouter(
    prefix="/internal/video_gen/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("")
async def reconcile_jobs(
    since: datetime = Query(..., description="ISO-8601 — rows updated at/after this"),
    limit: int = Query(1000, ge=1, le=5000, description="page cap — the sweeper's _PAGE_LIMIT"),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): video-gen jobs updated
    since `since` (oldest-first, capped at `limit`), in canonical `JobEvent` payload shape,
    for the jobs-service sweep to upsert. Stateless (decouple off → no pool/rows) → an empty
    list, never a 500."""
    try:
        pool = get_pool()
    except RuntimeError:
        return {"jobs": []}
    rows = await VideoGenJobsRepo(pool).list_since(since, limit=limit)
    return {"jobs": [
        {
            "service": "video_gen", "job_id": str(j.id), "owner_user_id": str(j.user_id),
            "kind": "video_gen", "status": j.status, "parent_job_id": None,
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


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_video_gen_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
) -> JobControlResponse:
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNSUPPORTED_ACTION",
                    "message": f"video-gen jobs support only 'cancel', not '{action}'"},
        )
    try:
        pool = get_pool()
    except RuntimeError:
        # Stateless (decouple off) — no job rows exist to control.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    repo = VideoGenJobsRepo(pool)
    # M4 — re-verify ownership on the real row (owner-scoped → 404 if not owned/found).
    job = await repo.get(payload.owner_user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    # CAS cancel via the existing terminal-transition helper (active → cancelled).
    won = await repo.fail(
        job_id, status="cancelled", error={"code": "cancelled", "message": "cancelled by user"}
    )
    if not won:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED",
                    "message": f"job not cancellable from status '{job.status}'"},
        )
    return JobControlResponse(job_id=job_id, status="cancelled")
