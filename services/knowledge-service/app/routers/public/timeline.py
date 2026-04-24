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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.clients.book_client import BookClient
from app.clients.chapter_title_enricher import enrich_events_with_chapter_titles
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import get_entity
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
    after_chronological: int | None = Query(
        default=None,
        ge=0,
        description=(
            "C10 (D-K19e-α-03): strict ``chronological_order > N`` "
            "filter. NULL-chrono events are excluded when set."
        ),
    ),
    before_chronological: int | None = Query(
        default=None,
        ge=0,
        description=(
            "C10 (D-K19e-α-03): strict ``chronological_order < N`` "
            "filter. NULL-chrono events are excluded when set."
        ),
    ),
    entity_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "C10 (D-K19e-α-01): filter to events whose "
            "``participants`` array includes the entity's display "
            "name, canonical_name, or any alias. Missing / cross-"
            "user entity collapses to an empty timeline (no 404 "
            "existence leak)."
        ),
    ),
    limit: int = Query(50, ge=1, le=EVENTS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user_id: UUID = Depends(get_current_user),
    book_client: BookClient = Depends(get_book_client),
) -> TimelineResponse:
    """K19e.2 + C10 — timeline list for the caller.

    Multi-tenant safety: ``user_id`` comes from the JWT and is threaded
    into the Cypher ``$user_id`` param. The caller cannot spoof another
    user's events — cross-user rows are filtered at the MATCH. The
    entity_id resolution step also uses the JWT's user_id so a
    cross-user entity_id collapses to an empty candidate list.

    422 on reversed range (``after_order >= before_order`` OR
    ``after_chronological >= before_chronological``) so the FE sees an
    explicit error rather than an empty result that looks like
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
    if (
        after_chronological is not None
        and before_chronological is not None
        and after_chronological >= before_chronological
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"after_chronological ({after_chronological}) must "
                f"be < before_chronological ({before_chronological})"
            ),
        )
    async with neo4j_session() as session:
        # C10 (D-K19e-α-01): resolve entity_id → participant candidates
        # BEFORE the list query so the repo's Cypher can filter in a
        # single round-trip via `ANY(c IN $candidates WHERE c IN
        # e.participants)`. Missing / cross-user entity → empty list
        # (Cypher's `IN []` is always false → zero rows returned).
        # This collapses the 404 path to an empty timeline per KSA
        # §6.4 anti-existence-leak rules.
        participant_candidates: list[str] | None = None
        if entity_id is not None:
            ent = await get_entity(
                session,
                user_id=str(user_id),
                canonical_id=entity_id,
            )
            if ent is None:
                participant_candidates = []
            else:
                # Dedupe via set; drop any empty strings defensively.
                candidates = {
                    c
                    for c in (ent.name, ent.canonical_name, *ent.aliases)
                    if c
                }
                participant_candidates = list(candidates)

        rows, total = await list_events_filtered(
            session,
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            after_order=after_order,
            before_order=before_order,
            after_chronological=after_chronological,
            before_chronological=before_chronological,
            participant_candidates=participant_candidates,
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
