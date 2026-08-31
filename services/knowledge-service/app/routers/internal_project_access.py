"""GET /internal/projects/{project_id}/access — the grant a user holds on a PROJECT.

T55/g, decided in spec §8.7. `KalAuthGuard`'s user-mode arm gates on
`hasBookAccess(bookId, userId)` and requires `req.params.bookId`, so a project-scoped KAL
controller has no user-mode door at all: every JWT request 401s on `'book scope required'`,
leaving the internal token — which bypasses the guard — as the only way in. Three §8.6
federations (`fact-for-check`, `glossary-semantic`, `wiki-neighborhood`) are blocked on that,
and the missing piece is an authorisation PRIMITIVE, not a route.

⚠️ **This endpoint EXPOSES the existing rule; it does not restate it.** The project-grant
model already lives in `app.auth.grant_deps._resolve_owner` — owner wins outright, a project
WITH a book defers to the book grant, and a BOOK-LESS project is owner-only (R1). Writing
those three branches again here would be a second reader of one concept, which is the
`one concept, two readers` rot pattern §8.4 names. `_project_grant_level` below is the same
decision expressed once as a LEVEL instead of as an exception.

**The response contract mirrors book-service's exactly**, because `hasProjectAccess` in the
gateway is a parallel of `hasBookAccess` and any divergence would be a difference the two
have to remember rather than derive:

    GET /internal/books/{id}/access   -> 200 {"grant_level": "...", "lifecycle_state": "..."}
    GET /internal/projects/{id}/access -> 200 {"grant_level": "...", "lifecycle_state": "..."}

🔴 **Always 200, never 404, and `"none"` for both missing and forbidden.** book-service's own
note is *"Always 200 {grant_level}; `none` for missing/forbidden (no oracle, R4)"* — a 404 for
"no such project" and a 200-none for "no grant" would let any caller enumerate which project
ids exist by the status code alone. The two cases are deliberately indistinguishable.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from loreweave_grants import GrantLevel

from app.db.repositories.projects import ProjectsRepo
from app.deps import get_grant_client, get_projects_repo
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/projects",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

#: GrantLevel → the wire string book-service emits. The INVERSE of
#: `loreweave_grants._WIRE`, derived from it rather than retyped so the two cannot drift into
#: disagreeing about a name.
_LEVEL_NAME = {
    GrantLevel.OWNER: "owner",
    GrantLevel.MANAGE: "manage",
    GrantLevel.EDIT: "edit",
    GrantLevel.VIEW: "view",
    GrantLevel.NONE: "none",
}


async def _project_grant_level(project_id: UUID, user_id: UUID, repo, gc) -> GrantLevel:
    """The caller's level on a project — the same three branches as `_resolve_owner`.

    Fail-closed at every exit: an absent project, a book-less project the caller does not own,
    and an unresolvable book grant all return NONE.
    """
    meta = await repo.project_meta(project_id)
    if meta is None:
        return GrantLevel.NONE                       # no such project — indistinguishable
    owner, book_id = meta
    if user_id == owner:
        return GrantLevel.OWNER
    if book_id is None:
        return GrantLevel.NONE                       # book-less project → owner-only (R1)
    return await gc.resolve_grant(book_id, user_id)


@router.get("/{project_id}/access")
async def project_access(
    project_id: UUID,
    user_id: UUID = Query(...),
    repo: ProjectsRepo = Depends(get_projects_repo),
    gc=Depends(get_grant_client),
) -> dict[str, str]:
    """`{grant_level, lifecycle_state}` — always 200. See the module docstring for why."""
    try:
        level = await _project_grant_level(project_id, user_id, repo, gc)
    except Exception as exc:                          # noqa: BLE001
        # A grant check that ERRORS must not read as a grant. The gateway's `hasBookAccess`
        # already fails closed on a transport error; this closes the same door on the far
        # side, so an outage in the book-grant path cannot widen access from either end.
        logger.warning(
            "project access check failed for project=%s user=%s: %s — returning none",
            project_id, user_id, exc,
        )
        level = GrantLevel.NONE
    return {
        "grant_level": _LEVEL_NAME.get(level, "none"),
        # knowledge projects carry no lifecycle of their own; the book's is what book-service
        # reports. Empty is the value `hasBookAccess` already treats as "not disqualifying"
        # (`lifecycle === '' || lifecycle === 'active'`), so this stays a pure grant answer
        # rather than inventing a second lifecycle for the gateway to interpret.
        "lifecycle_state": "",
    }
