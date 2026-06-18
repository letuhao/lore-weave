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

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.clients.book_client import (
    BookClient,
    BookServiceUnavailable,
    WorldNotFound,
)
from app.clients.chapter_title_enricher import enrich_events_with_chapter_titles
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import get_entity
from app.db.neo4j_repos.events import (
    EVENTS_MAX_LIMIT,
    Event,
    list_events_filtered,
)
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_book_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user
from app.spoiler_window import resolve_before_order
from app.world_rollup import resolve_world_project_ids

timeline_router = APIRouter(
    prefix="/v1/knowledge",
    tags=["timeline"],
    dependencies=[Depends(get_current_user)],
)


class TimelineResponse(BaseModel):
    events: list[Event]
    total: int


class WorldTimelineResponse(BaseModel):
    """D-WORLD-TIMELINE-ROLLUP — the world timeline union. Events carry their
    own ``project_id`` so the FE legends per book. ``truncated`` flags that the
    merged union exceeded the cap (a busy book can crowd a quieter one)."""

    events: list[Event]
    total: int
    truncated: bool


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
    event_date_from: str | None = Query(
        default=None,
        # C18 REVIEW-DESIGN catch — structural calendar validation:
        # 4-digit year + optional 2-digit month [01-12] + optional
        # 2-digit day [01-31]. Doesn't catch Feb 30 (would need
        # calendar awareness) but catches the dominant typo class.
        pattern=r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$",
        description=(
            "C18 (D-K19e-α-02): inclusive lower bound on "
            "``e.event_date_iso``. ISO truncated: ``YYYY``, "
            "``YYYY-MM``, or ``YYYY-MM-DD``. Events with NULL "
            "``event_date_iso`` are EXCLUDED when set."
        ),
    ),
    event_date_to: str | None = Query(
        default=None,
        pattern=r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$",
        description=(
            "C18 (D-K19e-α-02): inclusive upper bound on "
            "``e.event_date_iso``. ISO truncated: ``YYYY``, "
            "``YYYY-MM``, or ``YYYY-MM-DD``. Events with NULL "
            "``event_date_iso`` are EXCLUDED when set."
        ),
    ),
    before_chapter_id: UUID | None = Query(
        default=None,
        description=(
            "T2.1 — spoiler-window the timeline THROUGH this book chapter "
            "(resolved server-side to a ``before_order`` ceiling). An "
            "explicit ``before_order`` wins if both are given. Fail-closed: "
            "an unresolvable chapter yields an empty timeline, never a leak."
        ),
    ),
    sort_by: Literal["narrative", "chronological"] = Query(
        default="narrative",
        description=(
            "C14 (C14-narrative-order-sort): timeline sort axis. "
            "``narrative`` (default) = reading position (event_order) — "
            "the legacy ordering, so omitting this is back-compatible. "
            "``chronological`` = in-story chronology (chronological_order; "
            "undated events sink last)."
        ),
    ),
    sort_dir: Literal["asc", "desc"] = Query(
        default="asc",
        description=(
            "D-K19e-α-03: sort direction, applied to the selected ``sort_by`` "
            "axis. ``asc`` (default) = earliest-first (legacy, back-compatible); "
            "``desc`` = latest-first. Undated/unordered events sink last in BOTH "
            "directions."
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
    ``after_chronological >= before_chronological`` OR
    ``event_date_from > event_date_to``) so the FE sees an explicit
    error rather than an empty result that looks like "no events
    in range".

    C18: ``event_date_from`` / ``event_date_to`` are INCLUSIVE both
    ends (vs the EXCLUSIVE ``after_order`` / ``before_order``); the
    reversed-range check uses strict ``>`` not ``>=`` so
    ``from == to`` is valid (selects events with that exact date).
    Events with NULL ``event_date_iso`` are EXCLUDED when either
    filter is active — no-date events have no business answering
    "what happened in 1880?".
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
    if (
        event_date_from is not None
        and event_date_to is not None
        and event_date_from > event_date_to
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"event_date_from ({event_date_from!r}) must be "
                f"<= event_date_to ({event_date_to!r})"
            ),
        )
    # T2.1 — resolve the chapter spoiler-window to a before_order ceiling. An
    # explicit before_order wins; an unresolvable chapter fails CLOSED (-1 → empty).
    if before_order is None and before_chapter_id is not None:
        before_order, _available = await resolve_before_order(book_client, before_chapter_id)

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
            event_date_from=event_date_from,
            event_date_to=event_date_to,
            participant_candidates=participant_candidates,
            sort_by=sort_by,
            sort_dir=sort_dir,
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


@timeline_router.get(
    "/worlds/{world_id}/timeline",
    response_model=WorldTimelineResponse,
)
async def list_world_timeline(
    world_id: UUID = Path(
        description="The world whose member books' timelines to roll up.",
    ),
    sort_by: Literal["narrative", "chronological"] = Query(
        default="narrative",
        description=(
            "Sort axis for the merged union. ``narrative`` (default) = reading "
            "position (event_order); ``chronological`` = in-story chronology "
            "(undated events sink last)."
        ),
    ),
    limit: int = Query(50, ge=1, le=EVENTS_MAX_LIMIT),
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
    book_client: BookClient = Depends(get_book_client),
) -> WorldTimelineResponse:
    """D-WORLD-TIMELINE-ROLLUP — the world timeline: a UNION of each member
    book's canon timeline + the world-level (bible) project, the timeline mirror
    of the W2 graph rollup.

    Membership + the partition set are resolved by the SAME ``resolve_world_
    project_ids`` helper the subgraph rollup uses (owner-scoped via book-service
    internal; a world the caller doesn't own → 404; book-service down → 503). The
    union is N isolated per-(user_id, project_id) reads stitched in app code —
    no cross-partition Cypher, no cross-user/cross-project bleed. Events keep
    their ``project_id`` so the FE legends each book; the merged set is re-sorted
    on the chosen axis and capped (``truncated`` flags an over-cap union).
    """
    try:
        project_ids = await resolve_world_project_ids(
            world_id=world_id, user_id=user_id, repo=repo, book=book_client
        )
    except WorldNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="world not found"
        )
    except BookServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="world membership unavailable",
        )

    merged: list[Event] = []
    seen_ids: set[str] = set()
    # /review-impl MED — each per-project read is itself capped at `limit`, and
    # `list_events_filtered` returns the TRUE pre-cap count. A single member book
    # with more than `limit` events would otherwise leave the union at exactly
    # `limit` → `len(merged) > limit` is False → the FE "showing the first N"
    # banner never shows though more exist. Track per-project truncation so the
    # flag is honest whether the overflow is within ONE book or ACROSS the union.
    any_project_truncated = False
    async with neo4j_session() as session:
        for pid in project_ids:
            rows, project_total = await list_events_filtered(
                session,
                user_id=str(user_id),
                project_id=pid,
                after_order=None,
                before_order=None,
                sort_by=sort_by,
                limit=limit,
                offset=0,
            )
            if project_total > len(rows):
                any_project_truncated = True
            for e in rows:
                if e.id not in seen_ids:
                    seen_ids.add(e.id)
                    merged.append(e)

    # Re-sort the union on the global axis (each per-project read was sorted only
    # within its own partition), then cap. NULL-order events sink last.
    if sort_by == "chronological":
        merged.sort(key=lambda e: (e.chronological_order is None, e.chronological_order or 0, e.id))
    else:
        merged.sort(key=lambda e: (e.event_order is None, e.event_order or 0, e.id))

    total = len(merged)
    truncated = any_project_truncated or total > limit
    events = merged[:limit]

    await enrich_events_with_chapter_titles(events, book_client)
    return WorldTimelineResponse(events=events, total=total, truncated=truncated)
