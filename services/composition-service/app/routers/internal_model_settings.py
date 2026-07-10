"""Internal book model-settings — the Book tier for the Chat & AI settings
cascade (spec docs/specs/2026-07-05-chat-ai-settings.md §3.2, D-CHATAI-M1B).

`GET /internal/composition/books/{book_id}/model-settings?caller_user_id=`
returns the book's per-role model settings so chat-service's effective-settings
resolver can populate the Book tier — identically for the owner and any grantee.

SCOPE (book-package re-key — spec 25 PM-9/PM-14, supersedes the prior PO note):
`composition_work` is now PER-BOOK (one canonical manifest per book, grant-gated),
NOT per-`(user_id, book_id)`. So the Book tier is simply the book's canonical Work
settings — a shared row resolved by `book_id` alone (`resolve_by_book`), with NO
actor scoping. The OLD rationale ("the book tier is the OWNER's per-user row; a
grantee reads it through a cross-tenant seam") is RETIRED: there is no per-user Work
fork to reach across. This is rewritten at its source because a stale in-code
decision is exactly how a future agent reverts the re-key backwards (PM-14
anti-revert).

ACCESS: this /internal route is fed a client-traceable `book_id` + `caller_user_id`,
so the internal token authenticates the SERVICE, not the caller — a real E0 book
grant is still required (`internal-route-driven-by-a-session-must-grant-check`). The
grant check is NOT weakened by the re-key: `GrantClient.resolve_owner` doubles as it
— no grant (or book absent) → uniform 404 (no existence/owner oracle). This is a
read; writes gate on the book grant at their own EDIT chokepoint.

Model roles are **dual-read**: the new `settings.model_roles` map wins if present,
else the legacy `default_model_ref` (→ chat) / `critic_model_ref` (→ critic)
scalars — so no write-path change is needed for the resolver to see the book model.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_grant_client_dep, get_works_repo
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/composition",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


def _model_roles_from_settings(settings: dict) -> dict:
    """Derive the per-role model map from a work.settings blob (new map ▸ legacy
    scalars). Only well-formed {model_ref[, model_source]} entries survive."""
    roles: dict[str, dict] = {}
    existing = settings.get("model_roles")
    if isinstance(existing, dict):
        for role, val in existing.items():
            if isinstance(val, dict) and val.get("model_ref"):
                roles[role] = {
                    "model_ref": str(val["model_ref"]),
                    "model_source": val.get("model_source") or "user_model",
                }
    # legacy scalars fill only roles the new map didn't set (dual-read compat).
    dmr = settings.get("default_model_ref")
    if dmr and "chat" not in roles:
        roles["chat"] = {"model_ref": str(dmr), "model_source": settings.get("default_model_source") or "user_model"}
    cmr = settings.get("critic_model_ref")
    if cmr and "critic" not in roles:
        roles["critic"] = {"model_ref": str(cmr), "model_source": settings.get("critic_model_source") or "user_model"}
    return roles


@router.get("/books/{book_id}/model-settings")
async def get_book_model_settings(
    book_id: UUID,
    caller_user_id: UUID = Query(...),
    works=Depends(get_works_repo),
    grant=Depends(get_grant_client_dep),
) -> dict:
    # Grant check FIRST (the internal token is not authorization): resolve_owner
    # returns the book owner iff `caller_user_id` holds a grant, else None. Post
    # re-key the Work is per-book, so the returned owner is no longer needed to scope
    # the read — resolve_owner is kept purely as the grant gate. No grant (or book
    # absent) → uniform 404, never a 403/owner oracle.
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    # resolve_by_book (PM-9, no user_id) returns the book's marked Works ordered by
    # created_at — rows[0] is the canonical manifest (source_work_id IS NULL, minted
    # before any C23 derivative), whose settings hold the Book-tier model roles.
    rows = await works.resolve_by_book(book_id)
    settings = (rows[0].settings if rows else {}) or {}
    return {"model_roles": _model_roles_from_settings(settings)}
