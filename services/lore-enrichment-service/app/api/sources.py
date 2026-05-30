"""Sources (corpora) router (stub — RAID C3 contract freeze).

List returns a spec-valid empty shape (200). Registering a corpus returns 501
(no DB writes at C3; ingest/chunking/embedding is C10). Principal carried (Q3).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.api.principal import Principal, require_principal

router = APIRouter(prefix="/v1/lore-enrichment/sources", tags=["sources"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    content={"code": "NOT_IMPLEMENTED", "message": "behaviour ships in a later cycle"},
)


@router.get("")
async def list_sources(
    project_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
) -> dict:
    # Spec-valid empty list (SourceListResponse).
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED
