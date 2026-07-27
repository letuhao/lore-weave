"""Glossary-build pipeline HTTP router — `/v1/composition/glossary-build/*`.

The deterministic world-building FSM (spec 2026-07-27): the agent no longer
CHOOSES tools; a caller drives the pipeline and the platform makes every write.

Auth: JWT user + E0 book-grant at the ROUTE (same shape as authoring-runs).
Reads gate VIEW on the run's book; mutations gate EDIT and belong to the run's
owner (`owner_user_id`) — a non-owner 404s (no existence oracle).
Status mapping: bad params → 422 · unknown run → 404 · wrong-from transition →
409 · planner/LLM failure → 502.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_glossary_build_service, get_grant_client_dep
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from app.services.glossary_build.service import (
    GlossaryBuildError,
    GlossaryBuildService,
)

router = APIRouter(prefix="/v1/composition/glossary-build")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


def _http(exc: GlossaryBuildError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


class RunCreate(BaseModel):
    book_id: UUID
    # Params: model_source + model_ref (user-model UUID — resolved via
    # provider-registry, NEVER a literal name), source_text, and the optional
    # caps (kinds, lang, max_items).
    params: dict[str, Any] = Field(default_factory=dict)


class PlanApprove(BaseModel):
    # [human checkpoint #1] the human may TRIM/EDIT the planner's worklist before
    # the build spends anything. Omitted ⇒ approve the stored worklist as-is.
    worklist: list[dict[str, Any]] | None = None


class EdgeApprove(BaseModel):
    # [human checkpoint #3] the human may TRIM the resolved edge list.
    # Omitted ⇒ apply the stored (resolved) edges as-is.
    edges: list[dict[str, Any]] | None = None


def _serialize(run: dict) -> dict[str, Any]:
    out = {k: run.get(k) for k in (
        "status", "worklist", "edges", "error_message")}
    out["run_id"] = str(run["run_id"])
    out["book_id"] = str(run["book_id"])
    out["params"] = {k: v for k, v in (run.get("params") or {}).items() if k != "source_text"}
    for ts in ("created_at", "updated_at"):
        v = run.get(ts)
        out[ts] = v.isoformat() if hasattr(v, "isoformat") else v
    if "items" in run:
        out["items"] = [{
            "item_id": str(i["item_id"]), "ordinal": i["ordinal"], "name": i["name"],
            "kind": i["kind"], "depth": i["depth"], "status": i["status"],
            "skip_reason": i.get("skip_reason"),
            "proposed_entity_id": str(i["proposed_entity_id"]) if i.get("proposed_entity_id") else None,
            "relations": i.get("relations") or [],
            "section_count": len(i.get("sections") or []),
        } for i in run["items"]]
    return out


async def _owned_run(svc: GlossaryBuildService, grant: GrantClient,
                     run_id: UUID, user_id: UUID, need: GrantLevel) -> dict:
    try:
        run = await svc.get(run_id, user_id)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    await _gate_book(grant, run["book_id"], user_id, need)
    return run


@router.post("/runs")
async def create_run(
    body: RunCreate,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    await _gate_book(grant, body.book_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.create_run(owner=user_id, book_id=body.book_id, params=body.params)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return JSONResponse(status_code=201, content=_serialize(run))


@router.post("/runs/{run_id}/plan")
async def plan_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    """draft → plan_ready. Synchronous: the planner is one bounded call."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.plan(run_id, user_id)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return _serialize(run)


@router.post("/runs/{run_id}/approve-plan")
async def approve_plan(
    run_id: UUID,
    body: PlanApprove,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    """[human checkpoint #1] plan_ready → building (spawns the driver)."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.approve_plan(run_id, user_id, worklist=body.worklist)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return _serialize(run)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    return _serialize(await _owned_run(svc, grant, run_id, user_id, GrantLevel.VIEW))


@router.get("/runs")
async def list_runs(
    book_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    runs = await svc.list_runs(owner=user_id, book_id=book_id, limit=limit)
    return {"items": [_serialize(r) for r in runs]}


@router.post("/runs/{run_id}/project-kg")
async def project_kg(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    """[after human checkpoint #2] proposed → kg_projecting → edges_ready.
    Projects the proposed entities into the graph and resolves the NAME-based
    relations into concrete edge proposals."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.project_kg(run_id, user_id, bearer)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return _serialize(run)


@router.post("/runs/{run_id}/approve-edges")
async def approve_edges(
    run_id: UUID,
    body: EdgeApprove | None = None,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    """[human checkpoint #3] edges_ready → done (applies the approved edges)."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.approve_edges(
            run_id, user_id, bearer, edges=body.edges if body else None)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return _serialize(run)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: GlossaryBuildService = Depends(get_glossary_build_service),
):
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.cancel(run_id, user_id)
    except GlossaryBuildError as exc:
        raise _http(exc) from exc
    return _serialize(run)
