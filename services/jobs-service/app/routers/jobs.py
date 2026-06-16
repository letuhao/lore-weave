"""`/v1/jobs` read API (Unified Job Control Plane P2, req 2 backend).

Every query is OWNER-SCOPED to the verified JWT `sub` — the spec's load-bearing
invariant (no cross-tenant job leak). `control_caps` are derived per-row at read
time from (status, kind) so they always reflect the job's CURRENT state. Control
ROUTING (forwarding cancel/pause/resume to the owning service) is P3; the SSE
stream is added in M3.
"""

from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from .. import control, sse
from ..config import settings
from ..contract import derive_control_caps
from ..deps import get_current_user, get_db
from ..projection import store

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def _with_caps(job: dict) -> dict:
    job["control_caps"] = [c.value for c in derive_control_caps(job["status"], job["kind"])]
    return job


@router.get("")
async def list_jobs(
    status: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    parent: Optional[str] = Query(default=None, description="parent job_id — list its children (H3)"),
    q: Optional[str] = Query(default=None, description="search across title/kind/service/model/job_id (ILIKE)"),
    bucket: Optional[str] = Query(default=None, description="'active' (non-terminal) | 'history' (terminal)"),
    cursor: Optional[str] = Query(default=None, description="keyset cursor (Active/live mode)"),
    offset: Optional[int] = Query(default=None, ge=0, description="offset → paginated mode (History); returns total"),
    limit: int = Query(default=store.DEFAULT_LIMIT, ge=1, le=store.MAX_LIMIT),
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """List the caller's jobs. Two modes:

    - **Active/live** (default, or `bucket=active`): keyset cursor on updated_at —
      stable under live SSE updates, unpaginated in the GUI. Returns `next_cursor`.
    - **History** (`offset` set, typically with `bucket=history`): offset pagination
      ordered by created_at — returns `total` for an "X–Y of N" pager.

    Default view = top-level jobs with a `child_count`; `?parent=<job_id>` returns
    that parent's children."""
    if offset is not None:
        items, total = await store.list_jobs_paged(
            db, user_id, status=status, kind=kind, parent=parent, q=q,
            bucket=bucket, offset=offset, limit=limit,
        )
        return {"items": [_with_caps(j) for j in items], "next_cursor": None, "total": total}
    items, next_cursor = await store.list_jobs(
        db, user_id, status=status, kind=kind, parent=parent, q=q, bucket=bucket,
        cursor=cursor, limit=limit,
    )
    return {"items": [_with_caps(j) for j in items], "next_cursor": next_cursor, "total": None}


@router.get("/summary")
async def jobs_summary(
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Owner-scoped status counts for the GUI's 4 summary cards (top-level jobs).
    Single segment — declared before the 2-segment `/{service}/{job_id}` detail route
    so it can never be parsed as a job id."""
    return await store.count_summary(db, user_id)


@router.get("/stream")
async def stream_jobs(user_id: str = Depends(get_current_user)) -> StreamingResponse:
    """Live SSE of the caller's job updates (owner-scoped pub/sub). Declared
    before the 2-segment detail route; `/stream` is a single segment so it can
    never be mistaken for `/{service}/{job_id}`. NB: browser EventSource cannot
    set Authorization — the P4 GUI uses a fetch-stream with the bearer (token in
    the URL is intentionally NOT supported — it would leak into logs)."""
    return StreamingResponse(
        sse.stream_user_events(settings.redis_url, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx/proxy buffering of the stream
        },
    )


@router.get("/{service}/{job_id}")
async def get_job(
    service: str,
    job_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """One job's detail. 404 if not found OR not owned (anti-oracle — never
    distinguish "exists but not yours" from "doesn't exist")."""
    job = await store.get_job(db, user_id, service, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _with_caps(job)


@router.post("/{service}/{job_id}/{action}")
async def control_job(
    service: str,
    job_id: str,
    action: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
) -> JSONResponse:
    """Cancel / pause / resume a job (P3). Owner-checked against the projection +
    gated on the job's state-aware control_caps, then forwarded to the owning
    service's internal endpoint (which RE-VERIFIES ownership on the row — M4).

    404 if not found/not owned (anti-oracle); 400 unknown action; 409 if the
    action isn't valid for the current state; 501 if the service has no P3 control
    endpoint yet. The downstream status (incl. its own 409 on a concurrent change)
    is relayed verbatim — the owning service is authoritative."""
    if action not in control.VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unknown action '{action}'")
    job = await store.get_job(db, user_id, service, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    caps = [c.value for c in derive_control_caps(job["status"], job["kind"])]
    if action not in caps:
        raise HTTPException(
            status_code=409,
            detail=f"action '{action}' not valid for status '{job['status']}'",
        )
    result = await control.forward_control(service, job_id, action, user_id)
    return JSONResponse(status_code=result.status_code, content=result.body)
