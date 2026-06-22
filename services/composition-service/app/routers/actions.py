"""Tier-W confirm-token routes (S-COMPOSE — NET-NEW per C-CONFIRM / INV-9).

The MCP propose tool `composition_publish` MINTS a confirm token (bound to
user+resource+payload+expiry via the kit's `mint_confirm_token`); these two
routes are the FE-facing pair the generic `confirm_action` frontend tool drives:

  - GET  /v1/composition/actions/preview?token=  → decode + describe (no write)
  - POST /v1/composition/actions/confirm         → verify + EXECUTE (the ONLY
                                                    write path for the canonization)

Both are INTERNAL (X-Internal-Token) — the gateway/BFF calls them on behalf of an
already-authed user; the token itself binds the user identity (claim `u`) so a
token minted for user A can never be confirmed as user B (the confirm re-checks
`claims.user_id == envelope user_id`).

Descriptor namespace: `composition.publish` (C-CONFIRM map → this domain). The
token's `payload` carries the resolved publish spec captured at propose time
(`{project_id, chapter_id, book_id}`), so the confirm executes EXACTLY what was
proposed — the LLM cannot alter the target between propose and confirm.

H13 anti-oracle: a forged/expired/foreign token yields a uniform refusal, never
revealing whether the resource exists.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from loreweave_mcp import (
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    verify_confirm_token,
)

from app.config import settings
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.deps import get_grant_client_dep, get_outline_repo, get_works_repo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.db.models import CompositionWork
from app.mcp.service_bearer import mint_service_bearer
from app.clients.book_client import BookClient, BookClientError
from app.deps import get_book_client_dep
from app.packer.pack import OwnershipError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition/actions")

# The Tier-W descriptors this domain's confirm path commits. Most writes are
# Tier-A (auto-applied with Undo) and do NOT route through here; the two
# cost/canon-bearing actions are: the canonization (publish) and the grounded
# cowrite engine (generate, which spends LLM tokens).
_PUBLISH_DESCRIPTOR = "composition.publish"
_GENERATE_DESCRIPTOR = "composition.generate"


def _require_internal_token(x_internal_token: str | None) -> None:
    """Gate these routes on the internal service token (mirrors the bespoke
    `/internal/*` chokepoint). The confirm TOKEN binds identity; this header
    proves the CALLER is the trusted gateway/BFF, not a random client."""
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="invalid or missing internal service token")


def _verify(token: str) -> Any:
    """Decode + verify a confirm token; map the kit's distinct failure modes to
    the C-CONFIRM outcome semantics. Invalid/forged → 400 (re-propose);
    expired → 410 (token_expired, distinct so the UI says 're-propose' not
    'denied')."""
    try:
        return verify_confirm_token(settings.confirm_token_signing_secret, token)
    except ConfirmTokenExpired as exc:
        raise HTTPException(status_code=410, detail={"code": "token_expired"}) from exc
    except ConfirmTokenInvalid as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc


@router.get("/preview")
async def preview_action(
    token: str = Query(..., min_length=1),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> dict[str, Any]:
    """Decode the confirm token and return a human-readable descriptor of what
    confirming would do (NO side effects). The FE's confirm card renders this."""
    _require_internal_token(x_internal_token)
    claims = _verify(token)
    payload = claims.payload if isinstance(claims.payload, dict) else {}
    return {
        "descriptor": claims.descriptor,
        "resource_id": str(claims.resource_id),
        "payload": payload,
        "expires_at": claims.exp,
    }


@router.post("/confirm")
async def confirm_action(
    token: str = Query(..., min_length=1),
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Verify the token and EXECUTE the bound action — the ONLY write path for a
    Tier-W S-COMPOSE action. Returns `{outcome: "action_done", ...}` on success.

    Re-checks: (1) the token's `u` (proposing user) MUST equal the envelope
    `X-User-Id` (a token minted for A can't be confirmed as B); (2) the caller
    still owns the Work + holds EDIT on its book at confirm time (a grant revoked
    between propose and confirm stops the write)."""
    _require_internal_token(x_internal_token)
    claims = _verify(token)

    # Identity binding (INV-9): the confirming envelope user must be the proposer.
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    try:
        envelope_user = UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid X-User-Id") from exc
    if envelope_user != claims.user_id:
        # H13 anti-oracle — uniform refusal, never reveal "this token is someone else's".
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    if claims.descriptor not in (_PUBLISH_DESCRIPTOR, _GENERATE_DESCRIPTOR):
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    payload = claims.payload if isinstance(claims.payload, dict) else {}
    try:
        project_id = UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    # Re-resolve ownership + EDIT at confirm time, common to every composition
    # confirm descriptor (the Work is user-scoped → None if not the caller's; the
    # grant may have been revoked since propose).
    work = await works.get(envelope_user, project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        await authorize_book(grant, work.book_id, envelope_user, GrantLevel.EDIT)
    except (OwnershipError, InsufficientGrant) as exc:
        raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc

    if claims.descriptor == _PUBLISH_DESCRIPTOR:
        return await _execute_publish(payload, project_id, work, envelope_user, outline, book)
    return await _execute_generate(payload, project_id, work, envelope_user)


async def _execute_publish(
    payload: dict[str, Any], project_id: UUID, work: CompositionWork,
    envelope_user: UUID, outline: OutlineRepo, book: BookClient,
) -> dict[str, Any]:
    """composition.publish effect — canonize a reviewed chapter draft (CM1)."""
    try:
        chapter_id = UUID(str(payload["chapter_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    # Canonization gate (CM1 / OI-1): a chapter is publishable ONLY when all its
    # composition scenes are 'done' and no unresolved canon contradiction survives
    # (the SAME gate the FE's Publish affordance reads). Re-check at execute time.
    gate = await outline.chapter_scene_gate(envelope_user, project_id, chapter_id)
    if not gate.get("can_publish"):
        raise HTTPException(
            status_code=409,
            detail={"code": "action_error", "reason": "not_publishable", "gate": gate},
        )

    # Execute the publish against book-service (canonize the chapter draft). The MCP
    # path has no JWT, so mint a short-lived service bearer for the envelope user
    # (see service_bearer.py); book-service re-checks ownership in SQL on `sub`.
    bearer = mint_service_bearer(envelope_user, settings.jwt_secret)
    try:
        result = await book.publish_chapter(work.book_id, chapter_id, bearer)
    except BookClientError as exc:
        # Surface book-service's client errors as a uniform action_error; a 5xx is
        # an upstream failure (the action did not complete).
        logger.warning("composition.publish book-service error: %s", exc)
        raise HTTPException(status_code=502, detail={"code": "action_error"}) from exc

    return {
        "outcome": "action_done",
        "descriptor": _PUBLISH_DESCRIPTOR,
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "book": result,
    }


async def _execute_generate(
    payload: dict[str, Any], project_id: UUID, work: CompositionWork, envelope_user: UUID,
) -> dict[str, Any]:
    """composition.generate effect — run the grounded cowrite ENGINE (the only
    spend path for the MCP `composition_generate` tool). Calls the engine router
    coroutine IN-PROCESS (the deps are trivial per-request factories) in auto
    (non-stream) mode, so the full canon-grounded drafter+critic pipeline runs and
    returns JSON. The MCP path has no JWT → mint a short-lived service bearer for
    the envelope user (book-service still enforces ownership in SQL on `sub`)."""
    # Imported here (not at module top) to avoid an import cycle: the engine router
    # imports the action confirm helpers' siblings; deferring keeps actions.py light.
    from app.routers import engine as engine_router
    from app.clients.book_client import get_book_client
    from app.clients.glossary_client import get_glossary_client
    from app.clients.knowledge_client import get_knowledge_client
    from app.clients.llm_client import get_llm_client
    from app.db.pool import get_pool
    from app.db.repositories.canon_rules import CanonRulesRepo
    from app.db.repositories.derivatives import DerivativesRepo
    from app.db.repositories.generation_jobs import GenerationJobsRepo
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.db.repositories.scene_links import SceneLinksRepo

    target_kind = str(payload.get("target_kind") or "")
    target_id_raw = payload.get("target_id")
    model_source = str(payload.get("model_source") or "")
    model_ref_raw = payload.get("model_ref")
    if target_kind not in ("scene", "chapter") or not target_id_raw or not model_ref_raw:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        target_id = UUID(str(target_id_raw))
        model_ref = UUID(str(model_ref_raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc
    guide = str(payload.get("guide") or "")
    reasoning = str(payload.get("reasoning") or "auto")
    max_out = payload.get("max_output_tokens")
    operation = payload.get("operation")

    bearer = mint_service_bearer(envelope_user, settings.jwt_secret)
    pool = get_pool()
    deps = dict(
        works=WorksRepo(pool), outline=OutlineRepo(pool),
        scene_links=SceneLinksRepo(pool), canon=CanonRulesRepo(pool),
        jobs=GenerationJobsRepo(pool), book=get_book_client(),
        glossary=get_glossary_client(), knowledge=get_knowledge_client(),
        llm=get_llm_client(), narrative_threads=NarrativeThreadRepo(pool),
        derivatives=DerivativesRepo(pool),
    )
    # Build the engine body from the (signed, tamper-proof) payload. The propose
    # tool already constrains the enums, but guard the construction so a malformed
    # payload is a clean 400 rather than a pydantic 500.
    try:
        if target_kind == "scene":
            body_kwargs: dict[str, Any] = dict(
                outline_node_id=target_id, model_source=model_source, model_ref=model_ref,
                mode="auto", guide=guide, reasoning=reasoning,
                operation=operation or "draft_scene",
            )
            if max_out is not None:
                body_kwargs["max_output_tokens"] = int(max_out)
            body = engine_router.GenerateBody(**body_kwargs)
        else:
            body_kwargs = dict(
                model_source=model_source, model_ref=model_ref, guide=guide,
                reasoning=reasoning, operation=operation or "draft_chapter",
                persist=True,
            )
            if max_out is not None:
                body_kwargs["max_output_tokens"] = int(max_out)
            body = engine_router.GenerateChapterBody(**body_kwargs)
    except (ValueError, TypeError) as exc:  # pydantic ValidationError ⊂ ValueError
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    try:
        if target_kind == "scene":
            resp = await engine_router.generate(
                project_id, body, user_id=envelope_user, bearer=bearer, **deps)
        else:
            resp = await engine_router.generate_chapter(
                project_id, target_id, body, user_id=envelope_user, bearer=bearer, **deps)
    except HTTPException:
        # The engine's own HTTPExceptions (404 not found / 403 insufficient / 413
        # too-large / 409 use-chapter-endpoint / 502 upstream) are already
        # meaningful — let them propagate to the FE confirm card unchanged.
        raise

    # The engine returns a JSONResponse in auto mode; surface its body verbatim.
    try:
        result = json.loads(resp.body)
    except (ValueError, AttributeError, TypeError):
        result = {}
    return {
        "outcome": "action_done",
        "descriptor": _GENERATE_DESCRIPTOR,
        "project_id": str(project_id),
        "target_kind": target_kind,
        "target_id": str(target_id),
        "generation": result,
    }
