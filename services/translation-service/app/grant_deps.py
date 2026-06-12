"""E0-4a access gate — book-grant authorization for translation routes.

Model (PO CLARIFY 2026-06-11): **caller-attributed + caller-pays** with a
**shared per-book read view**. A route authorizes the caller's grant on the
book, then:
  - writes stay attributed to the caller (`owner_user_id = caller`, billed to the
    caller's BYOK) — the gate just authorizes;
  - reads drop the `owner_user_id` predicate (the book/job/chapter scope stays) so
    every grantee sees the full per-book translation state (E0-2 R3 transform —
    IDOR-safe: the row is still scoped by book/job, the grant is the single gate).

Anti-oracle: no grant (`none`) → 404 (uniform with a missing book/job/version, no
existence oracle); a grantee under the required tier → 403; book-service
unreachable → grant `none` → 404 (fail-closed, grant_client contract).

Routes keyed by `book_id` in the path use ``require_book_grant``; routes keyed by
``job_id``/``version_id`` bootstrap the book from the row first
(``require_job_grant``/``require_version_grant``). Body-keyed callers (save-edit,
internal dispatch) use the inline ``authorize_book``/``authorize_job`` helpers.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException

from .deps import get_current_user
from .grant_client import GrantLevel, get_grant_client

__all__ = [
    "GrantLevel",
    "get_grant_client_dep",
    "authorize_book",
    "book_for_chapter",
    "require_book_grant",
]


def _not_found() -> HTTPException:
    # Uniform 404 — a non-grantee is indistinguishable from a missing resource.
    return HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Not found"})


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "TRANSL_FORBIDDEN", "message": "Insufficient permission"})


def get_grant_client_dep():
    """FastAPI seam for the grant client singleton (overridden in tests)."""
    return get_grant_client()


async def authorize_book(gc, book_id: UUID, caller: UUID, need: GrantLevel) -> UUID:
    """Resolve the caller's grant on `book_id`; raise 404 (none) / 403 (under
    tier). Returns the caller (caller-attributed). The single grant chokepoint."""
    lvl = await gc.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise _not_found()
    if not lvl.at_least(need):
        raise _forbidden()
    return caller


async def book_for_chapter(db: asyncpg.Pool, chapter_id: UUID) -> UUID | None:
    """Resolve a chapter's book from ANY of its translation rows. Returns None when
    the chapter has no translations yet (the caller decides 404 vs empty)."""
    return await db.fetchval(
        "SELECT book_id FROM chapter_translations WHERE chapter_id=$1 LIMIT 1", chapter_id,
    )


def require_book_grant(need: GrantLevel):
    """FastAPI dependency for routes with `book_id` in the PATH. Resource-keyed
    routes (job/version/chapter) authorize inline via ``authorize_book`` on the
    book_id of the row they already fetch (one query, no bootstrap)."""
    async def _dep(
        book_id: UUID,
        caller: str = Depends(get_current_user),
        gc=Depends(get_grant_client_dep),
    ) -> UUID:
        return await authorize_book(gc, book_id, UUID(caller), need)
    return _dep
