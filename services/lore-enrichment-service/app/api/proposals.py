"""Proposals router (stub — RAID C3 contract freeze). H0 surface.

List/read return spec-valid shapes (200). Review actions (approve/reject/edit)
mirror knowledge-service `pending_facts` (Q1) and the H0 author-only `promote`
are NOT implemented here — they return 501. The promote handler documents that
ONLY the book/project owner may call it (real owner check + write-back ship in
C13); the principal is carried so the route is never anonymous.

H0 note: there is intentionally NO PATCH/`review_status` mutation that reaches
canon. The dedicated `/promote` endpoint is the only canonization path.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status
from fastapi.responses import JSONResponse

from app.api.principal import Principal, require_principal

router = APIRouter(prefix="/v1/lore-enrichment/proposals", tags=["proposals"])

_NOT_IMPLEMENTED = JSONResponse(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    content={"code": "NOT_IMPLEMENTED", "message": "behaviour ships in a later cycle"},
)


@router.get("")
async def list_proposals(
    project_id: UUID = Query(...),
    job_id: Optional[UUID] = Query(None),
    review_status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
) -> dict:
    # Spec-valid empty review queue (ProposalListResponse).
    return {"items": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    # Q1: mirrors pending_facts confirm. NOT canonization (still confidence<1.0).
    return _NOT_IMPLEMENTED


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    body: Optional[dict] = Body(None),
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{proposal_id}/edit")
async def edit_proposal(
    proposal_id: UUID,
    body: dict = Body(...),
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    return _NOT_IMPLEMENTED


@router.post("/{proposal_id}/promote")
async def promote_proposal(
    proposal_id: UUID,
    principal: Principal = Depends(require_principal),
) -> JSONResponse:
    # H0: the ONE path to canon. AUTHOR-ONLY (book/project owner). The owner
    # check + glossary-SSOT write-back + permanent origin markers ship in C13;
    # at C3 this is a stub. The principal is carried (never anonymous) so the
    # authorization seam is present in the signature.
    return _NOT_IMPLEMENTED
