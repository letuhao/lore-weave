"""PlanForge HTTP router (M3) — `/v1/composition/books/{book_id}/plan/*`."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from app.deps import get_grant_client_dep, get_plan_forge_service
from app.grant_client import GrantClient, GrantLevel
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError
from app.db.models import PlanPassId
from app.grant_deps import InsufficientGrant, authorize_book
from app.services.plan_forge_service import PlanForgeService
from app.services.plan_pass_service import UpstreamStale

router = APIRouter(prefix="/v1/composition")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


# A braindump is long, but not UNBOUNDED. `_var_deltas` is O(lines x declared-codes) and every
# line is scanned, so an uncapped field is both a parser-cost and a memory surface — and the
# field is interpolated into prompts. 256K chars is ~65K tokens: far above any real braindump
# (the S06 flagship's is <8K) and far below a denial-of-service. (DBT-10; the repo-wide sweep of
# EVERY large-text field at the router layer stays tracked — this closes the one field I own.)
_SOURCE_MARKDOWN_MAX = 262_144


class PlanRunCreate(BaseModel):
    source_markdown: str = Field(min_length=1, max_length=_SOURCE_MARKDOWN_MAX)
    mode: Literal["rules", "llm"]
    model_ref: UUID | None = None
    force: bool = False
    # 27 PF-15 — the genre this plan is written FOR (reaches the cast/world/motif prompts, which
    # are already genre-aware). Declared HERE explicitly: Pydantic's default `extra='ignore'`
    # would silently DROP an undeclared field, so the client would send genre_tags, get a 200, and
    # the plan would be written genre-blind — the `rest-write-mirror-drops-fields` bug exactly.
    # Each tag is interpolated into a SYSTEM prompt (cast/world/motif are all genre-aware), so an
    # uncapped string is both a token-blowup and a system-prompt-injection surface. Cap the ITEM,
    # not just the list.
    genre_tags: list[Annotated[str, StringConstraints(max_length=40)]] = Field(
        default_factory=list, max_length=20,
    )


class PlanRefineRequest(BaseModel):
    model_ref: UUID
    revision: dict[str, Any] | None = None
    focus_paths: list[str] | None = None


class PlanAutofixRequest(BaseModel):
    """HTTP mirror of MCP `plan_handoff_autofix`. model_ref is OPTIONAL — the service resolves the
    author's default planner model. max_rounds is a closed range (→ 422, not a silent clamp)."""

    model_ref: UUID | None = None
    max_rounds: int = Field(default=3, ge=1, le=5)


class PlanInterpretRequest(BaseModel):
    user_message: str = Field(min_length=1)
    model_ref: UUID
    apply_mode_hint: Literal["auto", "confirm", "diagnose_only"] | None = None


class PlanCompileRequest(BaseModel):
    arc_id: str
    run_pipeline: bool = False
    model_ref: UUID | None = None


class PlanPassRequest(BaseModel):
    """27 V2-C2. `pass_id` is a CLOSED SET, so it is typed as one — an agent that sends `"motif"`
    (the id I myself drifted to once; see DR-06) gets a 422 naming the seven legal values, not a
    silent no-op or a 500 three layers down."""

    model_ref: UUID | None = None
    #: Per-pass knobs (k_ceiling, max_select…). Fingerprinted WITH the pass: changing one stales
    #: exactly that pass and everything downstream, with zero invalidation writes.
    params: dict[str, Any] = Field(default_factory=dict)
    #: PF-5's only escape. An explicit per-call argument, never an env flag — two users planning two
    #: books would want different answers, so it is a choice, not platform config.
    force: bool = False


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
    # PM-9 (spec 25, F5): `user_id` flows into the service as the plain ACTOR
    # (created_by stamp + spend attribution), never as scope — _ensure_work
    # resolves the book's canonical Work caller-independently, so an EDIT
    # grantee no longer forks a private pending Work.
    try:
        run, is_async, job_id = await svc.create_run(
            user_id, book_id,
            source_markdown=body.source_markdown,
            mode=body.mode,
            model_ref=body.model_ref,
            force=body.force,
            genre_tags=body.genre_tags,
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


@router.get("/books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}")
async def get_plan_artifact(
    book_id: UUID,
    run_id: UUID,
    artifact_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """BE-3. One artifact's content, so the Pass Rail can show what a checkpoint approves.

    ONE 404 covers run-not-found + artifact-not-found + cross-book artifact — emitting 403 for a
    foreign artifact_id would be an enumeration oracle (H13). READ-ONLY (FE opens it read-only).
    """
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    art = await svc.get_artifact(user_id, book_id, run_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return art


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
        # patch is an edit-merge (last-write-wins, no OCC) — the only failure is
        # "the run has no spec artifact to patch yet", an unprocessable state, NOT a
        # 409 conflict (which would wrongly signal the client to refetch-and-retry).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@router.post("/books/{book_id}/plan/runs/{run_id}/autofix")
async def autofix_plan_run(
    book_id: UUID,
    run_id: UUID,
    body: PlanAutofixRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """Bounded self-check→refine loop (M4 plan_handoff_autofix). Returns `{rounds, run}` — the
    Repair strip renders `rounds` (WHAT was fixed) and `run` carries the fresh detail."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        out = await svc.handoff_autofix(
            user_id, book_id, run_id,
            model_ref=body.model_ref, max_rounds=body.max_rounds,
        )
    except ValueError as exc:  # "no spec to refine" / no default planner model
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    # 202 ONLY when the worker path enqueued a round and the loop stopped with a live job; the
    # default worker-off path already finished → 200. A bare ack would lie about being async on
    # the sync path and would throw away `rounds` the Repair strip needs.
    run = out.get("run") or {}
    if run.get("active_job_id"):
        return JSONResponse(status_code=202, content=out)
    return out


class PlanCheckpointRequest(BaseModel):
    """27 V2-D2. The HTTP mirror of `plan_review_checkpoint` — same service call, same gates."""

    approved: bool
    #: Omit for the SPEC checkpoint. Give it to review one COMPILER PASS.
    pass_id: PlanPassId | None = None
    #: Deep-merge patch into the pass's artifact (requires `pass_id`). Saves a NEW artifact, so
    #: everything downstream goes stale by derivation — which is the point.
    edits: dict[str, Any] | None = None


@router.get("/books/{book_id}/plan/runs/{run_id}/passes")
async def pass_status_route(
    book_id: UUID,
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """27 V2-F2. The run's DERIVED pass ledger — nothing here is stored."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    out = await svc.pass_status(user_id, book_id, run_id)
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out


class PlanLinkRequest(BaseModel):
    target: Literal["skeleton", "scene_plan"] = "skeleton"


@router.post("/books/{book_id}/plan/runs/{run_id}/link")
async def relink_route(
    book_id: UUID,
    run_id: UUID,
    body: PlanLinkRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """27 V2-F2. Re-link a compiled plan into the spec tree. Idempotent; never reclaims an edit."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        return await svc.relink(user_id, book_id, run_id, target=body.target)
    except LookupError:
        raise HTTPException(status_code=404, detail="run not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "LINK_REFUSED", "message": str(exc)})


@router.post("/books/{book_id}/plan/runs/{run_id}/checkpoint")
async def review_checkpoint_route(
    book_id: UUID,
    run_id: UUID,
    body: PlanCheckpointRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        out = await svc.review_checkpoint(
            user_id, book_id, run_id, approved=body.approved,
            pass_id=body.pass_id, edits=body.edits,
        )
    except ValueError as exc:
        # 409: the request is well-formed and WILL succeed once the gate is satisfied (apply the
        # seed proposal, run the pass). A 400 would read as "you asked wrong", which is false and
        # would send the caller looking in the wrong place.
        raise HTTPException(
            status_code=409,
            detail={"code": "CHECKPOINT_REFUSED", "message": str(exc)},
        ) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out


@router.post("/books/{book_id}/plan/runs/{run_id}/passes/{pass_id}/run")
async def run_plan_pass_route(
    book_id: UUID,
    run_id: UUID,
    pass_id: PlanPassId,
    body: PlanPassRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """Run ONE compiler pass (27 V2-C2). Returns the job envelope + the run's DERIVED pass view
    (cursor / blocked_at / per-pass freshness) — all computed at serialization, never stored."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        return await svc.run_pass(
            user_id, book_id, run_id, pass_id,
            model_ref=body.model_ref, params=body.params, force=body.force,
        )
    except UpstreamStale as exc:
        # 409, not 400: the request is well-formed and will succeed once the upstream is accepted.
        # The blockers ride along, so the caller learns WHICH pass to fix rather than guessing.
        raise HTTPException(
            status_code=409,
            detail={"code": "UPSTREAM_STALE", "pass_id": exc.pass_id,
                    "blockers": exc.blockers, "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
