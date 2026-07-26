"""PlanForge auto-bootstrap gate HTTP router (POC).

`/v1/composition/books/{book_id}/plan/...` — propose→record→approve→apply,
see docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1/§4. A raw JSON
response is acceptable review UI for this POC (§4's explicit out-of-scope
list) — the plain-language review treatment is a later, separate pass.

Auth (BPS re-key, spec 25 OQ-3): the E0 book-grant gate here is the ONLY
access decision — proposals are book-scoped rows (VIEW reads, EDIT mutates);
`created_by` is a plain actor stamp on the writes that create rows (propose)
or replay them as the caller (apply), never an access filter.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.clients.book_client import BookClientError
from app.clients.glossary_client import GlossaryClientError
from app.deps import get_bootstrap_service, get_grant_client_dep
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from app.services.bootstrap_service import BootstrapService

router = APIRouter(prefix="/v1/composition")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


@router.post("/books/{book_id}/plan/runs/{run_id}/bootstrap/propose")
async def propose_bootstrap(
    book_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: BootstrapService = Depends(get_bootstrap_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        record = await svc.propose(user_id, book_id, run_id, bearer)
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.get("/books/{book_id}/plan/bootstrap/{proposal_id}")
async def get_bootstrap_proposal(
    book_id: UUID,
    proposal_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: BootstrapService = Depends(get_bootstrap_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    record = await svc.get(book_id, proposal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return record.model_dump(mode="json")


@router.post("/books/{book_id}/plan/bootstrap/{proposal_id}/approve")
async def approve_bootstrap(
    book_id: UUID,
    proposal_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: BootstrapService = Depends(get_bootstrap_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        record = await svc.approve(book_id, proposal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.post("/books/{book_id}/plan/bootstrap/{proposal_id}/reject")
async def reject_bootstrap(
    book_id: UUID,
    proposal_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: BootstrapService = Depends(get_bootstrap_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        record = await svc.reject(book_id, proposal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.post("/books/{book_id}/plan/bootstrap/{proposal_id}/apply")
async def apply_bootstrap(
    book_id: UUID,
    proposal_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: BootstrapService = Depends(get_bootstrap_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        record = await svc.apply(user_id, book_id, proposal_id, bearer)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal not found")
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except GlossaryClientError as exc:
        # GLOSS_BOOK_NOT_SCAFFOLDED is actionable by the user (adopt an
        # ontology first), not a transient outage — 422, not 502.
        status = 422 if exc.code == "GLOSS_BOOK_NOT_SCAFFOLDED" else 502
        raise HTTPException(status_code=status, detail=exc.detail or str(exc)) from exc
    return record.model_dump(mode="json")
