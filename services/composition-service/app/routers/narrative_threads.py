"""narrative_thread read router — the promise-ledger debt surface (FD-1 S4a).

`GET /works/{project_id}/narrative-threads` exposes the ledger so an author/FE
can see the unpaid debt (spec §7 foreshadow-drop: open promises still owed). The
`open` set IS the advisory debt — D4: a flag/signal the author acts on, never a
hard gate. The producer (S2) writes the ledger; the pack re-injection (S3) feeds
generation; this read closes the human-visibility side.

Read-only; the ledger is written by the generation flow, not here.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.db.repositories.narrative_thread import NarrativeThreadRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_grant_client_dep, get_narrative_thread_repo, get_works_repo
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
) -> None:
    """PM-8/PM-9: resolve the Work by `project_id` (un-user-scoped) and gate the
    caller's E0 VIEW grant on its `book_id` — reading the promise ledger is a VIEW
    act. Before the package re-key this checked EXISTENCE only; after de-usering the
    repo that would be zero access control (any authenticated caller could read any
    book's ledger by guessing the project id). A missing project OR a no-grant caller
    → uniform 404 (anti-oracle); a grantee under VIEW → 403."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


@router.get("/works/{project_id}/narrative-threads")
async def list_narrative_threads(
    project_id: UUID,
    status: Literal["open", "all"] = "open",
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    threads: NarrativeThreadRepo = Depends(get_narrative_thread_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """List the work's narrative threads. `status=open` (default) = the unpaid
    debt (open/progressing, priority-ordered) — the §7 arc-end check; `status=all`
    = the full ledger (any status) for review. `open_count` is the advisory
    debt signal regardless of the `status` filter."""
    await _require_work(works, grant, user_id, project_id)
    rows = await (threads.list_open(project_id) if status == "open"
                  else threads.list_for_project(project_id))
    # open_count is the TRUE debt (a COUNT), independent of the `status` filter and
    # NOT capped by list_open's LIMIT (review-impl MED#1).
    return {
        "threads": [t.model_dump(mode="json") for t in rows],
        "open_count": await threads.count_open(project_id),
    }
