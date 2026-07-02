"""Autonomous authoring-run HTTP router (RAID Wave D2, DR-D / 07S §10) —
`/v1/composition/authoring-runs/*`.

Auth mirrors plan_forge: JWT user + E0 book-grant gate (EDIT — an authoring run
writes chapter drafts and spends) on the routes that carry a book_id; the
run-scoped routes are owner-filtered in SQL (a foreign run_id is a 404, no
existence oracle). Status mapping: gate-validation failure → 400 · unknown
run → 404 · wrong-from transition → 409 · active-run overlap (scope fence,
edge #11) → 409 with code `active_run_overlap`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.deps import get_authoring_run_service, get_book_client_dep, get_grant_client_dep
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from app.services.authoring_run_service import (
    ActiveRunOverlapError,
    AuthoringRunService,
    TransitionConflictError,
)

router = APIRouter(prefix="/v1/composition/authoring-runs")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


class AuthoringRunCreate(BaseModel):
    book_id: UUID
    plan_run_id: UUID
    level: Literal[3, 4]
    scope: list[UUID] = Field(default_factory=list)   # ordered chapter list
    budget_usd: Decimal = Decimal("0")
    # C2-allowlist SNAPSHOT, provided by the FE/chat layer at gate time (DR-D
    # deviation-by-necessity: chat's user_tool_approvals DB is not composition's
    # — the snapshot lives on the run row; provenance is the caller's).
    tool_allowlist: list[str] = Field(default_factory=list)
    # Drafting-seam inputs: {model_source, model_ref (user-model UUID), guide?}.
    # Models resolve via provider-registry from the ref — never a literal.
    params: dict[str, Any] = Field(default_factory=dict)


def _serialize(run: Any) -> dict[str, Any]:
    return {
        "run_id": str(run.run_id),
        "book_id": str(run.book_id),
        "plan_run_id": str(run.plan_run_id),
        "level": run.level,
        "scope": [str(c) for c in run.scope],
        "budget_usd": str(run.budget_usd),
        "spent_usd": str(run.spent_usd),
        "tool_allowlist": run.tool_allowlist,
        "params": run.params,
        "breaker_state": run.breaker_state,
        "status": run.status,
        "current_unit": run.current_unit,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


@router.post("")
async def create_authoring_run(
    body: AuthoringRunCreate,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    await _gate_book(grant, body.book_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.create(
            user_id, body.book_id,
            plan_run_id=body.plan_run_id,
            level=body.level,
            scope=[str(c) for c in body.scope],
            budget_usd=body.budget_usd,
            tool_allowlist=body.tool_allowlist,
            params=body.params,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="plan run not found")
    return JSONResponse(status_code=201, content=_serialize(run))


@router.get("")
async def list_authoring_runs(
    book_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    runs = await svc.list(user_id, book_id, limit=limit)
    return {"items": [_serialize(r) for r in runs]}


@router.get("/{run_id}")
async def get_authoring_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    run = await svc.get(user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _serialize(run)


@router.post("/{run_id}/gate")
async def gate_authoring_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    # Resolve the book's active chapter-id set for the scope-membership check
    # (with the CALLER's bearer — book-service re-checks ownership on `sub`).
    run = await svc.get(user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        chapters = await book.list_chapters(run.book_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    chapter_ids = {str(c["chapter_id"]) for c in chapters if c.get("chapter_id")}
    try:
        gated = await svc.gate(user_id, run_id, book_chapter_ids=chapter_ids)
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except ActiveRunOverlapError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "active_run_overlap", "detail": str(exc)},
        )
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(gated)


def _transition_route(action: str):
    async def _run(
        run_id: UUID,
        user_id: UUID = Depends(get_current_user),
        svc: AuthoringRunService = Depends(get_authoring_run_service),
    ):
        try:
            run = await getattr(svc, action)(user_id, run_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="run not found")
        except TransitionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return _serialize(run)

    _run.__name__ = f"{action}_authoring_run"
    return _run


router.add_api_route("/{run_id}/start", _transition_route("start"), methods=["POST"])
router.add_api_route("/{run_id}/pause", _transition_route("pause"), methods=["POST"])
router.add_api_route("/{run_id}/resume", _transition_route("resume"), methods=["POST"])
router.add_api_route("/{run_id}/close", _transition_route("close"), methods=["POST"])


# ── D3 — Run Report + dependency-ordered accept/reject + Revert-All ─────────


def _serialize_unit(unit: Any) -> dict[str, Any]:
    return {
        "run_id": str(unit.run_id),
        "unit_index": unit.unit_index,
        "chapter_id": str(unit.chapter_id),
        "status": unit.status,
        "pre_revision_id": str(unit.pre_revision_id) if unit.pre_revision_id else None,
        "post_revision_id": str(unit.post_revision_id) if unit.post_revision_id else None,
        "cost_usd": str(unit.cost_usd),
        "error_message": unit.error_message,
        "created_at": unit.created_at.isoformat() if unit.created_at else None,
        "updated_at": unit.updated_at.isoformat() if unit.updated_at else None,
    }


@router.get("/{run_id}/report")
async def get_run_report(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    """Run Report — owner or E0 VIEW grantee (this is the ONE run-scoped route
    that is grant- rather than owner-gated: the report is the run's reviewable
    artifact, same read tier as the runs list). Available from report_ready and
    from failed/paused (edge #12 — partial completion must be reviewable) +
    closed (post-Revert-All audit)."""
    run = await svc.get_any(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    await _gate_book(grant, run.book_id, user_id, GrantLevel.VIEW)
    try:
        units = await svc.unit_report(run)
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "run": _serialize(run),
        "units": units,
        "dependencies": {
            "model": "sequential_thread",
            "note": (
                "units are drafted sequentially and each unit's prose threads into "
                "every later unit; each unit's downstream_unit_indexes lists the "
                "later drafted/accepted units that depend on it — rejecting an "
                "upstream unit warns (does NOT auto-reject) its downstream (v1)"
            ),
        },
    }


@router.post("/{run_id}/units/{unit_index}/accept")
async def accept_run_unit(
    run_id: UUID,
    unit_index: int,
    user_id: UUID = Depends(get_current_user),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    try:
        unit = await svc.accept_unit(user_id, run_id, unit_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _serialize_unit(unit)


@router.post("/{run_id}/units/{unit_index}/reject")
async def reject_run_unit(
    run_id: UUID,
    unit_index: int,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    """Reject = restore the chapter to its pre-run revision FIRST (book-service
    public restore route, CALLER's bearer — the owner clicked it), then mark
    rejected. Restore failure → 502 with the unit left drafted. The response
    carries `cascade_warning` (edge #3): the downstream drafted/accepted units
    this rejection invalidates (v1 warns, never auto-rejects)."""

    async def _restore(book_id: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await book.restore_revision(book_id, chapter_id, revision_id, bearer)

    try:
        unit, cascade, reverted = await svc.reject_unit(
            user_id, run_id, unit_index, restore=_restore,
        )
    except BookClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "RESTORE_FAILED",
                "detail": f"book-service restore failed ({exc}); unit left drafted",
            },
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        **_serialize_unit(unit),
        "reverted": reverted,
        "cascade_warning": {
            "downstream_unit_indexes": cascade,
            "note": (
                "these later drafted/accepted units were threaded on the rejected "
                "chapter's prose — review or reject them too (not auto-rejected)"
            ),
        },
    }


@router.post("/{run_id}/revert-all")
async def revert_all_run_units(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    """Reject every drafted/accepted unit in REVERSE unit order (downstream
    first — the threaded restores unwind cleanly). First restore failure stops
    the sweep → 502 reporting which units DID revert (run left as-is); full
    success closes the run."""

    async def _restore(book_id: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await book.restore_revision(book_id, chapter_id, revision_id, bearer)

    try:
        result = await svc.revert_all(user_id, run_id, restore=_restore)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result["failed_unit_index"] is not None:
        raise HTTPException(
            status_code=502,
            detail={"code": "REVERT_ALL_PARTIAL", **result},
        )
    return result
