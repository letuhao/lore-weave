"""Templates router (stub — RAID C3 contract freeze).

List returns a spec-valid empty shape (200). Creating a template returns 501
(template scaffolding is C9). Templates are service-level (not per-user), so the
list signature takes no project_id; the principal is still carried for parity.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.api.principal import Principal, require_principal

router = APIRouter(prefix="/v1/lore-enrichment/templates", tags=["templates"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    content={"code": "NOT_IMPLEMENTED", "message": "behaviour ships in a later cycle"},
)


@router.get("")
async def list_templates(
    entity_kind: Optional[str] = Query(None, max_length=64),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
) -> dict:
    # Spec-valid empty list (TemplateListResponse).
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED
