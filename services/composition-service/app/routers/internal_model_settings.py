"""Internal book model-settings — the Book tier for the Chat & AI settings
cascade (spec docs/specs/2026-07-05-chat-ai-settings.md §3.2, D-CHATAI-M1B).

`GET /internal/composition/books/{book_id}/model-settings?caller_user_id=`
returns the book-OWNER's per-role model settings so chat-service's
effective-settings resolver can populate the Book tier — for the owner AND for a
grantee. Because `composition_work` is per-`(user_id, book_id)`, the book tier is
the OWNER's row; a grantee reads it through this **grant-gated** cross-tenant seam
(resolve_owner confirms a grant before the owner-scoped read). No grant → 404 (no
existence/owner oracle). The book-tier WRITE path stays owner-`user_id`-scoped;
this is a read-only exception, not a widening of the write scope (LOCKED).

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
    owner = await grant.resolve_owner(book_id, caller_user_id)
    if owner is None:
        # no grant (or book absent) — uniform 404, never a 403/owner oracle.
        raise HTTPException(status_code=404, detail="book not found or no access")
    rows = await works.resolve_by_book(owner, book_id)
    settings = (rows[0].settings if rows else {}) or {}
    return {"model_roles": _model_roles_from_settings(settings)}
