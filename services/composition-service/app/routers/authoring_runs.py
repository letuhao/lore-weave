"""Autonomous authoring-run HTTP router (RAID Wave D2, DR-D / 07S §10) —
`/v1/composition/authoring-runs/*`.

Auth (BPS re-key, spec 25 OQ-3): JWT user + E0 book-grant gate at the ROUTE —
the repo no longer filters on the actor. READS are book-grant-keyed: GET /
list / report gate VIEW on the run's book_id (every grantee sees the book's
runs — `.runs/` is inside the package). MUTATIONS belong to the run's CREATOR
(`created_by`, the stored actor stamp), gated EDIT on the book; pause/close
additionally keep the OWNER escalation (an OWNER-grant holder may pause/close
a collaborator's run — the row's created_by stamp is untouched). A no-grant or
non-creator caller 404s (no existence oracle). Status mapping: gate-validation
failure → 400 · unknown run → 404 · wrong-from transition → 409 · active-run
overlap (scope fence, edge #11) → 409 with code `active_run_overlap`.
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
    ALLOWLISTABLE_TOOLS,
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


async def _run_for_mutation(
    svc: "AuthoringRunService",
    grant: GrantClient,
    run_id: UUID,
    user_id: UUID,
    *,
    book_owner_may_act: bool = False,
) -> Any:
    """Load the run and decide access for a MUTATING route (OQ-3: access is
    decided at the gate, never by an actor filter in the repo). Run mutations
    belong to the run's CREATOR (`created_by` — the stored actor stamp), gated
    EDIT on the run's book. `book_owner_may_act` (pause/close only): the scope
    fence is per-BOOK across users, so a collaborator's abandoned gated/paused
    run would lock the book's owner out of autonomous runs forever if only the
    creator could clear it — the book's OWNER-grant holder may therefore
    pause/close ANY run on their book (the row's created_by stamp is
    preserved). Non-creator callers without that escalation 404 (no existence
    oracle)."""
    run = await svc.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.created_by == user_id:
        await _gate_book(grant, run.book_id, user_id, GrantLevel.EDIT)
    elif book_owner_may_act:
        await _gate_book(grant, run.book_id, user_id, GrantLevel.OWNER)
    else:
        raise HTTPException(status_code=404, detail="run not found")
    return run


class AuthoringRunCreate(BaseModel):
    book_id: UUID
    plan_run_id: UUID
    level: Literal[3, 4]
    scope: list[UUID] = Field(default_factory=list)   # ordered chapter list
    budget_usd: Decimal = Decimal("0")
    # C2-allowlist SNAPSHOT, provided by the FE/chat layer at gate time (DR-D
    # deviation-by-necessity: chat's user_tool_approvals DB is not composition's
    # — the snapshot lives on the run row; provenance is the caller's).
    # IN-3 (mcp-tool-io.md, /review-impl 2026-07-05): closed-set enum, single
    # source of truth = authoring_run_service.ALLOWLISTABLE_TOOLS (gate() also
    # re-validates against the same set as the shared backstop).
    tool_allowlist: list[Literal[ALLOWLISTABLE_TOOLS]] = Field(default_factory=list)
    # Drafting-seam inputs: {model_source, model_ref (user-model UUID), guide?}.
    # Models resolve via provider-registry from the ref — never a literal.
    params: dict[str, Any] = Field(default_factory=dict)
    # D4 fg/bg toggle — v1 semantics: a pure display/filter flag surfaced in
    # GET/list (the FE's fg/bg UX comes later). Durable sweep-resume applies to
    # BOTH foreground and background runs.
    background: bool = False
    # D-AGENT-MODE §20 D4/D4a: server-side auto-pause-after-each-unit policy.
    # Default true for this REST/human path ONLY — the MCP create tool (D4b)
    # requires it explicitly, no silent default there.
    pause_after_each_unit: bool = True


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
        "background": run.background,  # D4 fg/bg flag (FE filter)
        "pause_after_each_unit": run.pause_after_each_unit,  # D-AGENT-MODE §20 D4
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
            user_id, body.book_id,  # caller = created_by (plain actor stamp)
            plan_run_id=body.plan_run_id,
            level=body.level,
            scope=[str(c) for c in body.scope],
            budget_usd=body.budget_usd,
            tool_allowlist=body.tool_allowlist,
            params=body.params,
            background=body.background,
            pause_after_each_unit=body.pause_after_each_unit,
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
    runs = await svc.list(book_id, limit=limit)
    return {"items": [_serialize(r) for r in runs]}


@router.get("/{run_id}")
async def get_authoring_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    # OQ-3 read widening: any E0 VIEW grantee on the run's book may read it
    # (load-then-gate; a no-grant caller 404s — no existence oracle).
    run = await svc.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    await _gate_book(grant, run.book_id, user_id, GrantLevel.VIEW)
    return _serialize(run)


class AuthoringRunPausePolicy(BaseModel):
    pause_after_each_unit: bool


@router.patch("/{run_id}/pause-policy")
async def set_authoring_run_pause_policy(
    run_id: UUID,
    body: AuthoringRunPausePolicy,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    """D-AGENT-MODE §20 D4a: flip the server-side auto-pause-after-each-unit
    policy — creator-only (no book_owner_may_act widening), gated EDIT on the
    run's book, allowed from any non-closed status (a run-header toggle, not
    an FSM transition)."""
    await _run_for_mutation(svc, grant, run_id, user_id)
    try:
        run = await svc.set_pause_policy(run_id, body.pause_after_each_unit)
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except TransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _serialize(run)


@router.post("/{run_id}/gate")
async def gate_authoring_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    # Creator-only mutation, gated EDIT on the run's book (OQ-3: gate at the
    # route, no actor filter in the repo).
    run = await _run_for_mutation(svc, grant, run_id, user_id)
    # Resolve the book's active chapter-id set for the scope-membership check
    # (with the CALLER's bearer — book-service re-checks access on `sub`).
    try:
        chapters = await book.list_chapters(run.book_id, bearer)
    except BookClientError as exc:
        if exc.status in (401, 403):  # revoked/expired caller access, not an outage
            raise HTTPException(status_code=403, detail="insufficient access")
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    chapter_ids = {str(c["chapter_id"]) for c in chapters if c.get("chapter_id")}
    try:
        gated = await svc.gate(run_id, book_chapter_ids=chapter_ids)
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


def _transition_route(action: str, *, book_owner_may_act: bool = False):
    """FSM transition route. Access via `_run_for_mutation`: the run's CREATOR
    (created_by), gated EDIT on the book — plus, when `book_owner_may_act`
    (pause/close only), the book's OWNER-grant holder acting on a
    collaborator's run (the scope fence is per-BOOK across users, so an
    abandoned gated/paused run would otherwise lock the owner out forever).
    The row's created_by stamp is untouched by the escalation. No-grant /
    non-creator callers still 404 (no existence oracle)."""

    async def _run(
        run_id: UUID,
        user_id: UUID = Depends(get_current_user),
        grant: GrantClient = Depends(get_grant_client_dep),
        svc: AuthoringRunService = Depends(get_authoring_run_service),
    ):
        await _run_for_mutation(
            svc, grant, run_id, user_id, book_owner_may_act=book_owner_may_act,
        )
        try:
            run = await getattr(svc, action)(run_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="run not found")
        except TransitionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return _serialize(run)

    _run.__name__ = f"{action}_authoring_run"
    return _run


router.add_api_route("/{run_id}/start", _transition_route("start"), methods=["POST"])
router.add_api_route(
    "/{run_id}/pause", _transition_route("pause", book_owner_may_act=True),
    methods=["POST"],
)
router.add_api_route("/{run_id}/resume", _transition_route("resume"), methods=["POST"])
router.add_api_route(
    "/{run_id}/close", _transition_route("close", book_owner_may_act=True),
    methods=["POST"],
)


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
        "critic_verdict": unit.critic_verdict,  # D5 (None = not critiqued)
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
    """Run Report — any E0 VIEW grantee on the run's book (the report is the
    run's reviewable artifact, same read tier as the runs list — the
    load-then-gate shape every read route now uses under OQ-3). Available from
    report_ready and from failed/paused (edge #12 — partial completion must be
    reviewable) + closed (post-Revert-All audit)."""
    run = await svc.get(run_id)
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
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
):
    # Review is a mutation: creator-only + EDIT gate on the run's book.
    await _run_for_mutation(svc, grant, run_id, user_id)
    try:
        unit = await svc.accept_unit(run_id, unit_index)
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
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    """Reject = restore the chapter to its pre-run revision FIRST (book-service
    public restore route, CALLER's bearer — the creator clicked it), then mark
    rejected. Creator-only + EDIT gate on the run's book. Restore failure →
    502 with the unit left drafted. The response carries `cascade_warning`
    (edge #3): the downstream drafted/accepted units this rejection
    invalidates (v1 warns, never auto-rejects)."""
    await _run_for_mutation(svc, grant, run_id, user_id)

    async def _restore(book_id: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await book.restore_revision(book_id, chapter_id, revision_id, bearer)

    try:
        unit, cascade, reverted = await svc.reject_unit(
            run_id, unit_index, restore=_restore,
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
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: AuthoringRunService = Depends(get_authoring_run_service),
    book: BookClient = Depends(get_book_client_dep),
):
    """Reject every drafted/accepted unit in REVERSE unit order (downstream
    first — the threaded restores unwind cleanly). Creator-only + EDIT gate on
    the run's book. First restore failure stops the sweep → 502 reporting
    which units DID revert (run left as-is); full success closes the run."""
    await _run_for_mutation(svc, grant, run_id, user_id)

    async def _restore(book_id: UUID, chapter_id: UUID, revision_id: UUID) -> None:
        await book.restore_revision(book_id, chapter_id, revision_id, bearer)

    try:
        result = await svc.revert_all(run_id, restore=_restore)
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
