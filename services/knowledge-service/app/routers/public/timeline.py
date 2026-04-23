"""K19e.2 — Public timeline endpoint.

GET /v1/knowledge/timeline

Paginated browse over the caller's :Event nodes, ordered by narrative
position (``event_order``). Powers the Timeline tab's list view.

Cycle α ships the minimal BE surface: ``project_id`` + ``after_order`` +
``before_order`` filters + pagination + total count. Three filter
dimensions from the plan row are deferred (entity_id, wall-clock
date range, chronological_order range) — see the
``list_events_filtered`` docstring for the rationale.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.clients.book_client import BookClient
from app.clients.chapter_title_enricher import enrich_events_with_chapter_titles
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.events import (
    EVENTS_MAX_LIMIT,
    Event,
    list_events_filtered,
)
from app.deps import get_book_client
from app.middleware.jwt_auth import get_current_user

timeline_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["timeline"],
    dependencies=[Depends(get_current_user)],
)


class TimelineResponse(BaseModel):
    events: list[Event]
    total: int


@timeline_router.get("/timeline", response_model=TimelineResponse)
async def list_timeline_events(
    project_id: UUID | None = Query(
        default=None,
        description=(
            "Filter to a specific project. Omit to browse timeline "
            "events across every project + global-scope events the "
            "caller owns."
        ),
    ),
    after_order: int | None = Query(
        default=None,
        ge=0,
        description=(
            "Return events whose ``event_order`` is strictly greater "
            "than this value. NULL-order events are excluded when set."
        ),
    ),
    before_order: int | None = Query(
        default=None,
        ge=0,
        description=(
            "Return events whose ``event_order`` is strictly less "
            "than this value. NULL-order events are excluded when set."
        ),
    ),
    limit: int = Query(50, ge=1, le=EVENTS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user_id: UUID = Depends(get_current_user),
    book_client: BookClient = Depends(get_book_client),
) -> TimelineResponse:
    """K19e.2 — timeline list for the caller.

    Multi-tenant safety: ``user_id`` comes from the JWT and is threaded
    into the Cypher ``$user_id`` param. The caller cannot spoof another
    user's events — cross-user rows are filtered at the MATCH.

    422 on reversed range (``after_order >= before_order``) so the FE
    sees an explicit error rather than an empty result that looks like
    "no events in range".
    """
    if (
        after_order is not None
        and before_order is not None
        and after_order >= before_order
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"after_order ({after_order}) must be < "
                f"before_order ({before_order})"
            ),
        )
    async with neo4j_session() as session:
        rows, total = await list_events_filtered(
            session,
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            after_order=after_order,
            before_order=before_order,
            limit=limit,
            offset=offset,
        )
    # C6 (D-K19e-β-01) — batch-resolve chapter titles before serving
    # so the FE renders "Chapter 12 — The Bridge Duel" instead of
    # ``…last8chars``. In-place mutation; on any book-service failure
    # events keep ``chapter_title=None`` and the FE falls back to
    # the UUID short.
    await enrich_events_with_chapter_titles(rows, book_client)
    return TimelineResponse(events=rows, total=total)
