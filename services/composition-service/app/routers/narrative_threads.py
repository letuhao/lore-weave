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
from app.deps import get_narrative_thread_repo, get_works_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")


async def _require_work(works: WorksRepo, user_id: UUID, project_id: UUID) -> None:
    if await works.get(user_id, project_id) is None:
        raise HTTPException(status_code=404, detail="work not found")


@router.get("/works/{project_id}/narrative-threads")
async def list_narrative_threads(
    project_id: UUID,
    status: Literal["open", "all"] = "open",
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    threads: NarrativeThreadRepo = Depends(get_narrative_thread_repo),
) -> dict[str, Any]:
    """List the work's narrative threads. `status=open` (default) = the unpaid
    debt (open/progressing, priority-ordered) — the §7 arc-end check; `status=all`
    = the full ledger (any status) for review. `open_count` is the advisory
    debt signal regardless of the `status` filter."""
    await _require_work(works, user_id, project_id)
    rows = await (threads.list_open(user_id, project_id) if status == "open"
                  else threads.list_for_project(user_id, project_id))
    # open_count is the TRUE debt (a COUNT), independent of the `status` filter and
    # NOT capped by list_open's LIMIT (review-impl MED#1).
    return {
        "threads": [t.model_dump(mode="json") for t in rows],
        "open_count": await threads.count_open(user_id, project_id),
    }
