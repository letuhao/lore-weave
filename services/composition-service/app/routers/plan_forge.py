"""PlanForge HTTP router (M3) — `/v1/composition/books/{book_id}/plan/*`."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_grant_client_dep, get_plan_forge_service
from app.grant_client import GrantClient, GrantLevel
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError
from app.grant_deps import InsufficientGrant, authorize_book
from app.services.plan_forge_service import PlanForgeService

router = APIRouter(prefix="/v1/composition")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


class PlanRunCreate(BaseModel):
    source_markdown: str = Field(min_length=1)
    mode: Literal["rules", "llm"]
    model_ref: UUID | None = None
    force: bool = False


class PlanRefineRequest(BaseModel):
    model_ref: UUID
    revision: dict[str, Any] | None = None
    focus_paths: list[str] | None = None


class PlanInterpretRequest(BaseModel):
    user_message: str = Field(min_length=1)
    model_ref: UUID
    apply_mode_hint: Literal["auto", "confirm", "diagnose_only"] | None = None


class PlanCompileRequest(BaseModel):
    arc_id: str
    run_pipeline: bool = False
    model_ref: UUID | None = None


class NovelSystemSpecPatch(BaseModel):
    model_config = {"extra": "allow"}


@router.post("/books/{book_id}/plan/runs")
async def create_plan_run(
    book_id: UUID,
    body: PlanRunCreate,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        run, is_async, job_id = await svc.create_run(
            user_id, book_id,
            source_markdown=body.source_markdown,
            mode=body.mode,
            model_ref=body.model_ref,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detail = await svc.get_run_detail(user_id, book_id, run.id)
    if is_async:
        return JSONResponse(
            status_code=202,
            content={
                "run_id": str(run.id),
                "job_id": str(job_id) if job_id else None,
                "status": "pending",
            },
        )
    return JSONResponse(status_code=201, content=detail)


@router.get("/books/{book_id}/plan/runs")
async def list_plan_runs(
    book_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    return await svc.list_runs(user_id, book_id, limit=limit, cursor=cursor)


@router.get("/books/{book_id}/plan/runs/{run_id}")
async def get_plan_run(
    book_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    detail = await svc.get_run_detail(user_id, book_id, run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.patch("/books/{book_id}/plan/runs/{run_id}/novel-system-spec")
async def patch_novel_system_spec(
    book_id: UUID,
    run_id: UUID,
    body: NovelSystemSpecPatch,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        detail = await svc.patch_spec(user_id, book_id, run_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.post("/books/{book_id}/plan/runs/{run_id}/validate")
async def validate_plan_run(
    book_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    try:
        report = await svc.validate(user_id, book_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail="run not found")
    return report


@router.post("/books/{book_id}/plan/runs/{run_id}/refine")
async def refine_plan_run(
    book_id: UUID,
    run_id: UUID,
    body: PlanRefineRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        mode, payload = await svc.refine(
            user_id, book_id, run_id,
            model_ref=body.model_ref,
            revision=body.revision,
            focus_paths=body.focus_paths,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if mode == "async":
        return JSONResponse(status_code=202, content=payload)
    return payload


@router.post("/books/{book_id}/plan/runs/{run_id}/interpret")
async def interpret_plan_feedback(
    book_id: UUID,
    run_id: UUID,
    body: PlanInterpretRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        out = await svc.interpret(
            user_id, book_id, run_id,
            user_message=body.user_message,
            model_ref=body.model_ref,
            apply_mode_hint=body.apply_mode_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out


@router.post("/books/{book_id}/plan/runs/{run_id}/self-check")
async def self_check_plan_run(
    book_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    try:
        report = await svc.self_check(user_id, book_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail="run not found")
    return report


@router.post("/books/{book_id}/plan/runs/{run_id}/compile")
async def compile_plan_run(
    book_id: UUID,
    run_id: UUID,
    body: PlanCompileRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        mode, payload = await svc.compile(
            user_id, book_id, run_id,
            arc_id=body.arc_id,
            run_pipeline=body.run_pipeline,
            model_ref=body.model_ref,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except ValueError as exc:
        if "validation failed" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if mode == "async":
        return JSONResponse(status_code=202, content=payload)
    return payload
