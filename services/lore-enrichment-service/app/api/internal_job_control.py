"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/lore_enrichment/jobs/{job_id}/{action}` (action ∈ cancel|pause|resume)
— the `job_id`-keyed control surface the central **jobs-service** routes user control
to. Unlike composition/video-gen (single-call, cancel-only), the C8 `enrichment_job`
genuinely runs as multiple dispatched gap-fill units → it supports **pause/resume**
(manual pause; resume re-arms the re-drive worker via the resume stream — distinct
from the cost-cap auto-pause and the stranded-job sweeper, spec M5).

jobs-service has verified the caller owns the job against its projection; THIS endpoint
**re-verifies ownership on the actual `enrichment_job` row** (spec M4) by looking up its
`project_id` scoped to `(owner_user_id, job_id)` (→ 404 if not owned/found), then
DELEGATES to the existing C8 public handlers (`cancel_job`/`pause_job`/`resume_job`) —
reusing the same state machine, the atomic UPDATE+emit, and (for resume) the resume-stream
re-drive enqueue, with no duplicated lifecycle logic. The control plane carries only
`(owner, job_id)`; `project_id` is recovered here from the owner-scoped row.

Only the C8 `enrichment_job` is controllable here; the one-shot `enrichment_compose_task`
(kind profile_suggest/intent_resolve) is cancel-irrelevant and not wired
(D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL). Internal-token S2S; asserted `owner_user_id` in body.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.api.jobs import cancel_job, pause_job, resume_job
from app.api.principal import Principal
from app.config import settings
from app.deps import get_db
from app.jobs.job_events import canonical_status, job_error


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Server-to-server guard. Rejects a missing/wrong token (401)."""
    if not x_internal_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token"
        )


router = APIRouter(
    prefix="/internal/lore_enrichment/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)

# action → the public C8 handler that performs it (each reuses the state machine +
# atomic UPDATE+emit; resume also re-arms the re-drive worker via the resume stream).
_HANDLERS = {"cancel": cancel_job, "pause": pause_job, "resume": resume_job}


@router.get("")
async def reconcile_jobs(
    since: datetime = Query(..., description="ISO-8601 — rows updated at/after this"),
    limit: int = Query(1000, ge=1, le=5000, description="page cap — the sweeper's _PAGE_LIMIT"),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): `enrichment_job` rows
    updated since `since` (oldest-first, capped at `limit`), in canonical `JobEvent` payload
    shape, for the jobs-service sweep to upsert. Internal-token (router dep); ALL owners. A
    transient `estimating` row (canonical None) is skipped — it has no canonical JobStatus."""
    rows = await pool.fetch(
        "SELECT job_id, user_id, status, error_message, updated_at FROM enrichment_job "
        "WHERE updated_at >= $1 ORDER BY updated_at ASC LIMIT $2",
        since, limit,
    )
    out = []
    for r in rows:
        cstatus = canonical_status(r["status"])
        if cstatus is None:  # transient (estimating) — no canonical JobStatus
            continue
        out.append({
            "service": "lore_enrichment", "job_id": str(r["job_id"]),
            "owner_user_id": str(r["user_id"]), "kind": "enrichment_job", "status": cstatus,
            "parent_job_id": None, "detail_status": None, "progress": None, "title": None,
            "error": job_error(r["error_message"]) if cstatus == "failed" else None,
            "occurred_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })
    return {"jobs": out}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-checked
    # against the row here — M4.
    owner_user_id: UUID


class JobControlResponse(BaseModel):
    job_id: UUID
    status: str


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_enrichment_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    pool: asyncpg.Pool = Depends(get_db),
) -> JobControlResponse:
    handler = _HANDLERS.get(action)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown action: {action}",
        )
    # M4 — re-verify ownership on the real row + recover project_id (the control plane
    # carries only owner + job_id). Owner-scoped → a job not owned by the asserted user
    # simply isn't found (404, never a cross-tenant act).
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT project_id FROM enrichment_job WHERE user_id=$1 AND job_id=$2",
            payload.owner_user_id, job_id,
        )
    if project_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    # Delegate to the C8 public handler (reuses machine + UPDATE+emit + resume enqueue).
    # A 409 from an illegal transition propagates verbatim — the row is authoritative.
    principal = Principal(user_id=payload.owner_user_id)
    result = await handler(
        job_id, project_id=project_id, principal=principal, pool=pool,
    )
    return JobControlResponse(job_id=UUID(result["job_id"]), status=result["status"])
