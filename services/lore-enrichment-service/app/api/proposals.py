"""Proposals review gate + H0 write-back (RAID C13).

Implements the proposal review API mirroring knowledge-service ``pending_facts``
(Q1) PLUS the H0 author-only ``promote`` and a ``retract``:

  GET  /v1/lore-enrichment/proposals                 — list (Q3-scoped, filterable)
  GET  /v1/lore-enrichment/proposals/{id}            — read one
  POST /v1/lore-enrichment/proposals/{id}/approve    — proposed/reviewing → approved
  POST /v1/lore-enrichment/proposals/{id}/reject     — → rejected (terminal)
  POST /v1/lore-enrichment/proposals/{id}/edit       — author edits makeup content
  POST /v1/lore-enrichment/proposals/{id}/promote    — AUTHOR-ONLY → canon (H0 gate)
  POST /v1/lore-enrichment/proposals/{id}/retract    — recycle-bin (M6, reversible)

H0 (LOCKED):
  * approve does NOT canonize — it stays enriched (confidence<1.0) until promote.
  * promote is the ONLY path to canon; authorized against the book-service
    ``owner_user_id`` (truth source), not a client claim → non-owner gets 403.
  * write-back enters the KG QUARANTINED (source_type='enriched', pending,
    confidence<1.0); promote flips it to canon RETAINING the permanent origin
    marker; retract soft-deletes via the recycle-bin.

Cross-scope/missing collapses to 404 (no existence oracle), mirroring
pending_facts.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.principal import Principal, require_principal
from app.clients.writeback import WritebackError, WritebackPorts
from app.config import settings
from app.deps import get_db
from app.services.review import (
    IllegalTransitionError,
    ProposalsRepo,
    ReviewStatus,
)
from app.services.writeback import (
    NotApprovedError,
    NotOwnerError,
    WritebackService,
)

router = APIRouter(prefix="/v1/lore-enrichment/proposals", tags=["proposals"])


# ── dependency wiring ──────────────────────────────────────────────────────────


async def get_repo(pool: asyncpg.Pool = Depends(get_db)) -> ProposalsRepo:
    return ProposalsRepo(pool)


def _make_ports() -> WritebackPorts:
    return WritebackPorts(
        glossary_base_url=settings.glossary_service_url,
        knowledge_base_url=settings.knowledge_service_url,
        book_base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
    )


# ── request bodies ──────────────────────────────────────────────────────────────


class RejectBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000)


class EditBody(BaseModel):
    content: str = Field(min_length=1)
    cultural_grounding_ref: Optional[str] = None


class PromoteBody(BaseModel):
    """Promote/write-back/retract need the canon anchor coordinates. ``book_id``
    is the glossary/book scope; ``glossary_entity_id`` is optional (resolved via
    the glossary SSOT write when absent)."""

    book_id: UUID
    glossary_entity_id: Optional[UUID] = None


# ── helpers ──────────────────────────────────────────────────────────────────────


def _require_scope(principal: Principal, project_id: UUID) -> UUID:
    """The acting user (Q3 scope). Anonymous → 401."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    return principal.user_id


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")


# ── list / read ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_proposals(
    project_id: UUID = Query(...),
    job_id: Optional[UUID] = Query(None),
    review_status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    items, total = await repo.list(
        user_id=user_id,
        project_id=project_id,
        review_status=review_status,
        job_id=job_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [p.as_dict() for p in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    proposal = await repo.get(
        user_id=user_id, project_id=project_id, proposal_id=proposal_id
    )
    if proposal is None:
        raise _not_found()
    return proposal.as_dict()


# ── approve / reject / edit (mirror pending_facts — NOT canonization) ─────────────


@router.post("/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    try:
        proposal = await repo.set_status(
            user_id=user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            to_status=ReviewStatus.APPROVED,
        )
    except LookupError:
        raise _not_found()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return proposal.as_dict()


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    project_id: UUID = Query(...),
    body: Optional[RejectBody] = Body(None),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    reason = body.reason if body else None
    try:
        proposal = await repo.set_status(
            user_id=user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            to_status=ReviewStatus.REJECTED,
            rejected_reason=reason,
        )
    except LookupError:
        raise _not_found()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return proposal.as_dict()


@router.post("/{proposal_id}/edit")
async def edit_proposal(
    proposal_id: UUID,
    body: EditBody,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    try:
        proposal = await repo.edit_content(
            user_id=user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            content=body.content,
        )
    except LookupError:
        raise _not_found()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return proposal.as_dict()


# ── promote (AUTHOR-ONLY → canon, H0 gate) ───────────────────────────────────────


@router.post("/{proposal_id}/promote")
async def promote_proposal(
    proposal_id: UUID,
    body: PromoteBody,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    # No anonymous promote — and the owner check below is the real gate.
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    ports = _make_ports()
    service = WritebackService(repo, ports)
    try:
        result = await service.promote(
            acting_user_id=principal.user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            book_id=body.book_id,
            glossary_entity_id=body.glossary_entity_id,
        )
    except NotOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except LookupError:
        raise _not_found()
    except (NotApprovedError, IllegalTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except WritebackError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=str(exc))
    finally:
        await ports.aclose()

    p = result.proposal
    return {
        "proposal_id": p["proposal_id"],
        "review_status": p["review_status"],
        "promoted_entity_id": result.promoted_entity_id,
        "promoted_by": result.promoted_by,
        "promoted_at": result.promoted_at,
        "origin": p["origin"],
        "promoted_from_proposal_id": p["promoted_from_proposal_id"],
        "original_technique": p["original_technique"],
        "facts_promoted": result.facts_promoted,
        "canon": result.canon,
    }


# ── write-back (admit approved proposal to KG QUARANTINED — NOT canon) ────────────


@router.post("/{proposal_id}/write-back")
async def write_back_proposal(
    proposal_id: UUID,
    body: PromoteBody,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    user_id = _require_scope(principal, project_id)
    ports = _make_ports()
    service = WritebackService(repo, ports)
    try:
        result = await service.write_back(
            user_id=user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            book_id=body.book_id,
            glossary_entity_id=body.glossary_entity_id,
        )
    except LookupError:
        raise _not_found()
    except NotApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except WritebackError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=str(exc))
    finally:
        await ports.aclose()
    return {
        "proposal_id": result.proposal["proposal_id"],
        "glossary_entity_id": result.glossary_entity_id,
        "facts": [
            {
                "fact_id": f.fact_id,
                "dimension": f.dimension,
                "source_type": f.source_type,
                "confidence": f.confidence,
                "pending_validation": f.pending_validation,
            }
            for f in result.facts
        ],
        "canon": result.canon,
    }


# ── retract (M6 recycle-bin, reversible) ─────────────────────────────────────────


@router.post("/{proposal_id}/retract")
async def retract_proposal(
    proposal_id: UUID,
    body: PromoteBody,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    repo: ProposalsRepo = Depends(get_repo),
) -> dict:
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    ports = _make_ports()
    service = WritebackService(repo, ports)
    try:
        result = await service.retract(
            acting_user_id=principal.user_id,
            project_id=project_id,
            proposal_id=proposal_id,
            book_id=body.book_id,
            glossary_entity_id=body.glossary_entity_id,
            # F-C13-1: no JWT threaded — retract soft-deletes the supplement over
            # the internal token; the canonical entity is preserved.
        )
    except NotOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except LookupError:
        raise _not_found()
    except WritebackError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=str(exc))
    finally:
        await ports.aclose()
    return {
        "proposal_id": result.proposal["proposal_id"],
        "facts_retracted": result.facts_retracted,
        "supplement_retracted": result.supplement_retracted,
        "review_status": result.proposal["review_status"],
    }
