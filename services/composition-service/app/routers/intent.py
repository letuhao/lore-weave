"""Intent-collection FSM HTTP router — `/v1/composition/intent/*` (spec 2026-07-28).

Auth: JWT user + E0 book grant at the ROUTE (same shape as glossary-build). Reads gate VIEW on the
run's book; mutations gate EDIT and belong to the run's `owner_user_id` — a non-owner 404s rather
than 403ing, so the route is not an existence oracle.

Owner-scoped runs are deliberate, not an oversight: an intent run is a CONVERSATION with one author,
and two collaborators answering the same slot is a separate design the spec parks (§9).

Status mapping: bad params/value → 422 · unknown run → 404 · wrong-from transition → 409 ·
LLM failure → 502.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.deps import get_grant_client_dep, get_intent_fsm_service
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError
from app.services.intent_fsm.service import ACTIONS, IntentFSMError, IntentFSMService

router = APIRouter(prefix="/v1/composition/intent")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


def _http(exc: IntentFSMError) -> HTTPException:
    return HTTPException(status_code=exc.status,
                         detail={"code": exc.code, "message": exc.message})


class RunOpen(BaseModel):
    book_id: UUID
    node_id: UUID
    # model_source + model_ref (the user-model UUID — resolved through provider-registry, NEVER a
    # literal model name), plus the optional arm / n / lang / slots caps.
    params: dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    # CLOSED SET, enum-validated on the way in. A free string here is the frontend-tool bug class
    # that already shipped once: an unrecognised value fell through to a silent no-op and the model
    # reported success it never had.
    action: str = Field(pattern="^(accept|revise|decline)$")
    # `accept` with no value takes the top candidate; `revise` carries the author's own words;
    # `decline` ignores it entirely.
    value: Any = None


class Score(BaseModel):
    slot: str
    #: `[{"index": 0, "verdict": "accept"|"light_edit"|"discard"}, …]` — metric A, and it is the
    #: AUTHOR who fills it in. No route accepts a model-produced verdict, by design.
    verdicts: list[dict[str, Any]]


def _serialize(run: dict) -> dict[str, Any]:
    out = {k: run.get(k) for k in ("status", "slot_plan", "slot_cursor", "candidates",
                                   "error_detail")}
    out["run_id"] = str(run["run_id"])
    out["book_id"] = str(run["book_id"])
    out["node_id"] = str(run["node_id"])
    # `params` carries the resolved structure PROVENANCE — surfaced, not hidden, so the caller can
    # see whether `beat_role` was offered from the author's own structure or a platform default.
    out["params"] = {k: v for k, v in (run.get("params") or {}).items()
                     if k in ("arm", "n", "lang", "structure", "beat_keys")}
    for ts in ("created_at", "updated_at"):
        v = run.get(ts)
        out[ts] = v.isoformat() if hasattr(v, "isoformat") else v
    if "records" in run:
        out["records"] = [{
            "slot": r["slot"], "position": r["position"],
            "constraint_class": r["constraint_class"], "arm": r["arm"],
            "candidates": r.get("candidates") or [], "verdicts": r.get("verdicts") or [],
            "author_value": r.get("author_value"), "applied_value": r.get("applied_value"),
            "outcome": r["outcome"], "llm_calls": r["llm_calls"], "retried": r["retried"],
        } for r in run["records"]]
    return out


async def _owned_run(svc: IntentFSMService, grant: GrantClient, run_id: UUID,
                     user_id: UUID, need: GrantLevel) -> dict:
    try:
        run = await svc.get(run_id, user_id)
    except IntentFSMError as exc:
        raise _http(exc) from exc
    await _gate_book(grant, run["book_id"], user_id, need)
    return run


@router.post("/runs")
async def open_run(
    body: RunOpen,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """Open a run over the slots this node has not settled yet."""
    await _gate_book(grant, body.book_id, user_id, GrantLevel.EDIT)
    try:
        run = await svc.open_run(owner=user_id, book_id=body.book_id, node_id=body.node_id,
                                 params=body.params)
    except IntentFSMError as exc:
        raise _http(exc) from exc
    return JSONResponse(status_code=201, content=_serialize(run))


@router.get("/runs")
async def list_runs(
    book_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    return [_serialize(r) for r in await svc.list_runs(owner=user_id, book_id=book_id, limit=limit)]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    return _serialize(await _owned_run(svc, grant, run_id, user_id, GrantLevel.VIEW))


@router.post("/runs/{run_id}/propose")
async def propose(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """The run's ONLY LLM call: N candidates for the cursor's slot. One call, one retry, no loop."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.propose(run_id, user_id))
    except IntentFSMError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/answer")
async def answer(
    run_id: UUID,
    body: Answer,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """The author's blocking checkpoint. All three actions WRITE — `decline` stamps `absent`."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.answer(run_id, user_id, action=body.action, value=body.value))
    except IntentFSMError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/skip")
async def skip(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """Move past a slot whose proposal failed. The slot stays unasked — and the record says so."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.skip(run_id, user_id))
    except IntentFSMError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/resume")
async def resume(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """Rewind a run a restart stranded mid-request. Never skips the author."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.resume(run_id, user_id))
    except IntentFSMError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/cancel")
async def cancel(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """End the run. Every slot already settled STAYS settled — the writes were never provisional."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.cancel(run_id, user_id))
    except IntentFSMError as exc:
        raise _http(exc) from exc


@router.post("/runs/{run_id}/score")
async def score(
    run_id: UUID,
    body: Score,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: IntentFSMService = Depends(get_intent_fsm_service),
):
    """Metric A — the author's per-candidate verdict. Never written by a model."""
    await _owned_run(svc, grant, run_id, user_id, GrantLevel.EDIT)
    try:
        return _serialize(await svc.score(run_id, user_id, slot=body.slot, verdicts=body.verdicts))
    except IntentFSMError as exc:
        raise _http(exc) from exc


__all__ = ["router", "ACTIONS"]
