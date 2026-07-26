"""Prose-source proxy router (composition-service, M3 — decision B).

FE ↔ composition ↔ book-service for canonical chapter DRAFT content, so the
reused editor never reworks its backend when V1 adds sandbox branch/take prose.

Auth (spec 25 PM-8/PM-9): composition resolves the Work by `project_id` (un-user-
scoped) to find its `book_id`, then gates the caller's E0 grant on that book —
VIEW to read prose, EDIT to write it — BEFORE forwarding the caller's JWT to
book-service's public draft routes. The grant gate is the access decision (the
repo never filters on the caller); book-service additionally enforces book access
in SQL. A missing project OR a no-grant caller collapses to the same 404 (no
existence oracle).

OI-2/PS2 (the load-bearing bit): `PUT` requires `expected_draft_version` in the
body (a required model field → 422 if omitted) so a blind clobber can never
reach book-service. book-service leaves it optional; composition makes it
mandatory. A stale version → book-service 409 `CHAPTER_DRAFT_CONFLICT` → surfaced
here as 409. `PUT` writes the DRAFT only (book emits `chapter.saved`, never
`chapter.published`) — canonization is the separate CM1 `/publish` call.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.clients.book_client import BookClient, BookClientError
from app.db.repositories.works import WorksRepo
from app.deps import get_book_client_dep, get_grant_client_dep, get_works_repo
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, book_id_for_project
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")

# Book-service error statuses we forward verbatim (client errors); everything
# else (5xx / transport) becomes 502 (we are a proxy).
_PASSTHROUGH_STATUSES = frozenset({400, 404, 409, 422})


class ProsePutBody(BaseModel):
    # A TipTap/ProseMirror doc is ALWAYS a JSON object ({type:"doc", content:[…]}).
    # Typing it `dict` (not `Any`) rejects an explicit `null`/scalar/array body —
    # otherwise `body: null` would forward to book-service and could clobber the
    # draft to null (/review-impl M3 MED#1). Required, so an omitted body → 422.
    body: dict[str, Any]
    # MANDATORY (OI-2/PS2): omitting it would be a blind clobber. A required
    # field → 422 when absent, which is the "rejected client-side" guard.
    expected_draft_version: int
    body_format: str | None = None
    commit_message: str | None = None


def _map_book_error(exc: BookClientError) -> HTTPException:
    if exc.status in _PASSTHROUGH_STATUSES:
        return HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "detail": exc.detail},
        )
    return HTTPException(
        status_code=502,
        detail={"code": exc.code or "BOOK_SERVICE_ERROR", "upstream_status": exc.status},
    )


async def _resolve_book_id(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID, need: GrantLevel,
) -> UUID:
    """PM-8/PM-9: resolve `project_id` → its Work's `book_id` via the ids-only,
    un-user-scoped `scope_meta` read and gate the caller's E0 grant on that book at
    `need` (VIEW to read prose, EDIT to write). The gate is the ONLY access decision;
    a missing project OR a no-grant caller → uniform 404 (anti-oracle), under-tier → 403."""
    try:
        return await book_id_for_project(works, grant, project_id, user_id, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


def _base_revision_id(revisions: dict[str, Any]) -> str | None:
    items = revisions.get("items") or []
    if items and isinstance(items[0], dict):
        return items[0].get("revision_id")
    return None


@router.get("/works/{project_id}/chapters/{chapter_id}/prose")
async def get_prose(
    project_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    # Reading prose is a VIEW act on the book (E0-4c).
    book_id = await _resolve_book_id(works, grant, user_id, project_id, GrantLevel.VIEW)
    try:
        draft = await book.get_draft(book_id, chapter_id, bearer)
        revisions = await book.list_revisions(book_id, chapter_id, bearer, limit=1)
    except BookClientError as exc:
        raise _map_book_error(exc)
    # base_revision_id (OI-2 grounding anchor) isn't on the draft read → derive
    # it from the latest revision.
    draft["base_revision_id"] = _base_revision_id(revisions)
    return draft


@router.put("/works/{project_id}/chapters/{chapter_id}/prose")
async def put_prose(
    project_id: UUID,
    chapter_id: UUID,
    payload: ProsePutBody,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    # Writing the draft is an authoring act → EDIT grant on the book (E0-4c).
    book_id = await _resolve_book_id(works, grant, user_id, project_id, GrantLevel.EDIT)
    try:
        updated = await book.patch_draft(
            book_id, chapter_id, bearer,
            body=payload.body,
            expected_draft_version=payload.expected_draft_version,
            body_format=payload.body_format,
            commit_message=payload.commit_message,
        )
        revisions = await book.list_revisions(book_id, chapter_id, bearer, limit=1)
    except BookClientError as exc:
        raise _map_book_error(exc)
    updated["base_revision_id"] = _base_revision_id(revisions)
    return updated
