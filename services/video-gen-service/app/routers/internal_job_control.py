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

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from loreweave_llm import Client
from pydantic import BaseModel

from ..config import settings
from ..db.pool import get_pool
from ..db.repository import VideoGenJobsRepo
from ..models import GenerateRequest  # D-JOBS-P4-RETRY-VIDEOGEN — reconstruct from request_json

log = logging.getLogger(__name__)


async def _abort_provider_job(provider_job_id: UUID, owner_user_id: UUID) -> None:
    """D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT — best-effort: tell provider-registry to abort
    the in-flight provider job, which cancels its upstream goroutine (frees the GPU/API
    slot) and releases the spend reservation. The local `video_gen_jobs` row is already
    `cancelled` (canonical) before this runs, so a failure here only forfeits slot/cost
    reclaim — never correctness. cancel_job is idempotent (204/409 → None, 404 →
    LLMJobNotFound); all are swallowed (the job is, by truth, no longer ours to run)."""
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=str(owner_user_id),
    )
    try:
        await client.cancel_job(provider_job_id, user_id=str(owner_user_id))
    except Exception as exc:  # noqa: BLE001 — slot/cost reclaim is pure best-effort
        # 404 (LLMJobNotFound) / transport / 5xx — AND any unexpected error: the local row
        # is already `cancelled` (canonical), so the abort must NEVER fail the user's cancel.
        # The lease TTL + the consumer's already-cancelled CAS are the backstops.
        log.warning("video-gen: provider abort of %s failed (best-effort): %s", provider_job_id, exc)
    finally:
        await client.aclose()


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
    # D-JOBS-P4-RETRY-VIDEOGEN — re-submit a failed job from its stored request_json.
    if action == "retry":
        return await _retry_video_gen_job(job_id, payload.owner_user_id)
    if action != "cancel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNSUPPORTED_ACTION",
                    "message": f"video-gen jobs support 'cancel' | 'retry', not '{action}'"},
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
    # D-JOBS-P3-VIDEOGEN-PROVIDER-ABORT: now that WE own the cancel (the CAS won), abort
    # the in-flight provider job to reclaim its slot + spend reservation. Best-effort —
    # the local row is already `cancelled`, so this never affects correctness.
    if job.provider_job_id is not None:
        await _abort_provider_job(job.provider_job_id, payload.owner_user_id)
    return JobControlResponse(job_id=job_id, status="cancelled")


async def _retry_video_gen_job(job_id: UUID, owner_user_id: UUID) -> JobControlResponse:
    """D-JOBS-P4-RETRY-VIDEOGEN — re-submit a FAILED video-gen job as a FRESH job, reusing
    the failed row's stored `request_json` (prompt/model/duration/aspect/style — persisted
    since the producer-emit backfill, so NO migration needed). Mirrors the translation /
    knowledge retry contract: owner-scoped (404 if not owned), 409 unless `failed`, 404 when
    stateless (decouple off → no rows). A pre-emit row with an empty request_json can't be
    reconstructed → 409 (graceful, not a 500). The reconstructed GenerateRequest re-runs the
    existing `_submit_decoupled` (submit gateway job → new pending row → emits 'running'), so
    there is zero duplication of the submit/create/emit logic. Video-gen jobs are never
    campaign-dispatched (the row has no campaign_id), so no campaign-managed guard applies."""
    try:
        pool = get_pool()
    except RuntimeError:
        # Stateless (decouple off) — no job rows exist to retry.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    repo = VideoGenJobsRepo(pool)
    job = await repo.get(owner_user_id, job_id)  # M4 owner re-check (owner-scoped → 404)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_NOT_RETRYABLE",
                    "message": f"only a failed job can be retried (status='{job.status}')"},
        )
    req = job.request_json or {}
    if not req.get("model_ref") or not req.get("prompt"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_MISSING_PARAMS",
                    "message": "job has no stored request params to retry"},
        )
    # Reconstruct the original GenerateRequest from request_json (same field names). Pass
    # only present optional fields so the model's defaults apply for any the row omitted.
    kwargs: dict = {"prompt": req["prompt"], "model_ref": req["model_ref"]}
    for k in ("model_source", "duration_seconds", "aspect_ratio", "style"):
        v = req.get(k)
        if v is not None:
            kwargs[k] = v
    # Lazy imports — keep the router-import graph acyclic + avoid loading the submit path
    # (and its heavy deps) unless a retry actually fires.
    from fastapi import Response
    from .generate import _submit_decoupled
    new = await _submit_decoupled(GenerateRequest(**kwargs), str(owner_user_id), Response())
    return JobControlResponse(job_id=UUID(str(new.job_id)), status=new.status)
