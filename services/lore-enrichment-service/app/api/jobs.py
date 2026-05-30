"""Jobs router (stub — RAID C3 contract freeze).

Lists/reads return spec-valid empty/placeholder shapes (200). Create + lifecycle
actions (start/pause/resume/cancel) return 501 — their behaviour belongs to the
job orchestrator (C8/C14). The acting principal (Q3) is carried on every route.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.api.principal import Principal, require_principal

router = APIRouter(prefix="/v1/lore-enrichment/jobs", tags=["jobs"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    content={"code": "NOT_IMPLEMENTED", "message": "behaviour ships in a later cycle"},
)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.get("")
async def list_jobs(
    project_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
) -> dict:
    # Spec-valid empty list shape (JobListResponse).
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    # No store yet (C3 freeze); a fetch can't fabricate a real job, so 501.
    return _NOT_IMPLEMENTED


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED
