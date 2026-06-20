"""E0-4b access gate — book-grant authorization for campaign routes.

Model (PO CLARIFY 2026-06-18): **caller-attributed + caller-pays** with a **shared
per-book read view** (D-E0-4-F). A route authorizes the caller's grant on the
campaign's book, then:
  - writes stay attributed to the caller (``campaigns.owner_user_id = caller``); the
    knowledge stage bills the caller via the dual-identity dispatch (the graph stays
    partitioned under the BOOK OWNER — ``book_owner_user_id``);
  - reads drop the ``owner_user_id`` predicate (the campaign_id PK + book scope stay)
    so every grantee sees the book's campaigns (E0-2 R3 transform — IDOR-safe: the
    row is still scoped, the grant is the single gate).

need-mapping (D-E0-4-D): reads → view; pause → edit; create/start/cancel/budget/
rerun → manage.

Anti-oracle: no grant (``none``) → 404 (uniform with a missing book/campaign, no
existence oracle); a grantee under the required tier → 403; book-service unreachable
→ grant ``none`` → 404 (fail-closed, grant_client contract).

Routes with ``book_id`` in the body (create/estimate) authorize inline via
``authorize_book``. Routes keyed by ``campaign_id`` bootstrap the book from the row
first (the router-local ``_grant_campaign`` helper).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException

from .deps import get_current_user
from .grant_client import GrantLevel, get_grant_client

__all__ = [
    "GrantLevel",
    "get_grant_client_dep",
    "authorize_book",
    "require_book_grant",
    "not_found",
    "forbidden",
]


def not_found() -> HTTPException:
    # Uniform 404 — a non-grantee is indistinguishable from a missing resource.
    return HTTPException(status_code=404, detail={"code": "CAMPAIGN_NOT_FOUND", "message": "Not found"})


def forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "CAMPAIGN_FORBIDDEN", "message": "Insufficient permission"})


def get_grant_client_dep():
    """FastAPI seam for the grant client singleton (overridden in tests)."""
    return get_grant_client()


async def authorize_book(gc, book_id: UUID, caller: UUID, need: GrantLevel) -> UUID:
    """Resolve the caller's grant on ``book_id``; raise 404 (none) / 403 (under
    tier). Returns the caller (caller-attributed). The single grant chokepoint."""
    lvl = await gc.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise not_found()
    if not lvl.at_least(need):
        raise forbidden()
    return caller


def require_book_grant(need: GrantLevel):
    """FastAPI dependency for routes with ``book_id`` in the PATH (none in campaign
    today — body-keyed create/estimate authorize inline via ``authorize_book``)."""
    async def _dep(
        book_id: UUID,
        caller: str = Depends(get_current_user),
        gc=Depends(get_grant_client_dep),
    ) -> UUID:
        return await authorize_book(gc, book_id, UUID(caller), need)
    return _dep
