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
from app.mcp.service_bearer import mint_service_bearer
from app.clients.book_client import BookClient, BookClientError
from app.deps import get_book_client_dep
from app.packer.pack import OwnershipError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition/actions")

# The single descriptor this domain's confirm path commits. Kept narrow: only
# the canonization (publish) is Tier-W in S-COMPOSE; every other write is Tier-A
# (auto-applied with Undo), so it does NOT route through here.
_PUBLISH_DESCRIPTOR = "composition.publish"


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

    if claims.descriptor != _PUBLISH_DESCRIPTOR:
        raise HTTPException(status_code=400, detail={"code": "action_error"})

    payload = claims.payload if isinstance(claims.payload, dict) else {}
    try:
        project_id = UUID(str(payload["project_id"]))
        chapter_id = UUID(str(payload["chapter_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "action_error"}) from exc

    # Re-resolve ownership at confirm time (the Work is user-scoped → None if not
    # the caller's; the grant may have been revoked since propose).
    work = await works.get(envelope_user, project_id)
    if work is None:
        raise HTTPException(status_code=400, detail={"code": "action_error"})
    try:
        await authorize_book(grant, work.book_id, envelope_user, GrantLevel.EDIT)
    except (OwnershipError, InsufficientGrant) as exc:
        raise HTTPException(status_code=403, detail={"code": "action_error"}) from exc

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
        "descriptor": claims.descriptor,
        "project_id": str(project_id),
        "chapter_id": str(chapter_id),
        "book": result,
    }
