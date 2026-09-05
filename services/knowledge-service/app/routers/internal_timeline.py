"""M4d-1 — Internal timeline read endpoint (translation cross-chapter memo).

POST /internal/knowledge/timeline

Service-to-service read surface for the **translation-service** V3 pipeline,
which builds a cross-chapter "story so far" memo to keep proper nouns and
continuity stable across chapters. The timeline (narrative events with
participants + dates) lives only in Neo4j here; translation has no access to it
except via the knowledge MCP server (session/JWT) — so this mirrors the
``wiki-neighborhood`` internal endpoint to give the worker a clean
X-Internal-Token read path.

Namespace bridge is resolved **server-side**: translation works in ``book_id``
space, so the caller passes only ``book_id`` (+ the chapter reading position).
``(project_id, user_id)`` are looked up from ``knowledge_projects`` — the book
owner's tenant, exactly like the event handlers do. A book with no knowledge
project ⇒ ``found=False`` (cold start), not an error.

Reading-position-aware (no spoilers): events are capped to ``event_order <
chapter_index × stride`` (strictly before the chapter being translated), and a
sliding window (``_TIMELINE_CHAPTER_WINDOW`` chapters) keeps the memo to recent
continuity rather than the whole book. Read-only — never writes Neo4j.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db.graph import graph_session
# T17 A4 — the browse goes through the PORT (`events_page`, grown in A3 by this
# router's demand). `EVENT_ORDER_CHAPTER_STRIDE` stays a domain constant, not an
# operation: it is the reading-axis stride every producer stamps on, and moving it
# behind the port would make an engine responsible for a fact about the BOOK.
from app.adapters.graph_store_provider import get_graph_store
from app.domain.graph_models import EVENT_ORDER_CHAPTER_STRIDE
from app.db.pool import get_knowledge_pool
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/knowledge",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

# How many chapters back the memo window reaches. Earlier story is already
# covered by the glossary + the rolling prev-chapter summary; the timeline adds
# *recent* event continuity. Tunable; small to keep the prompt block bounded.
_TIMELINE_CHAPTER_WINDOW = 8


class TimelineRequest(BaseModel):
    book_id: UUID
    # The book-service chapter ``sort_order`` of the chapter being translated —
    # the GLOBAL reading position, the same axis ``event_order`` is keyed on (NOT
    # the caller's job-local index). Events strictly before it are "story so far".
    chapter_order: int = Field(ge=0)
    limit: int = Field(default=25, ge=1, le=50)


class TimelineEventOut(BaseModel):
    title: str
    summary: str | None = None
    event_date: str | None = None
    participants: list[str] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    """Empty timeline is a first-class valid result: ``found`` is False when the
    book has no knowledge project (cold start); True with an empty ``events``
    list when the project exists but no prior events match."""

    found: bool = False
    events: list[TimelineEventOut] = Field(default_factory=list)
    count: int = 0
    total: int = 0


@router.post("/timeline", response_model=TimelineResponse)
async def get_timeline(req: TimelineRequest) -> TimelineResponse:
    """Read narrative events up to a chapter reading position for the translation
    memo. Read-only; resolves the book→project→owner tenant server-side."""
    row = None
    async with get_knowledge_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
            req.book_id,
        )
    if row is None:
        # No knowledge project for this book ⇒ cold start (§11.3.C).
        return TimelineResponse(found=False)

    if req.chapter_order == 0:
        # First chapter — nothing precedes it.
        return TimelineResponse(found=True)

    before_order = req.chapter_order * EVENT_ORDER_CHAPTER_STRIDE
    # Sliding window: only the last _TIMELINE_CHAPTER_WINDOW chapters of events.
    after_order: int | None = None
    if req.chapter_order > _TIMELINE_CHAPTER_WINDOW:
        after_order = (req.chapter_order - _TIMELINE_CHAPTER_WINDOW) * EVENT_ORDER_CHAPTER_STRIDE

    async with graph_session() as session:
        # `after`/`before` are ORDINALS here because the axis is `narrative` (the default) —
        # the port types them as a union precisely so the axis stays a value a caller can
        # pass through, rather than three methods a caller has to choose between.
        events, total = await get_graph_store(session).events_page(
            user_id=str(row["user_id"]),
            project_id=str(row["project_id"]),
            after=after_order,
            before=before_order,
            limit=req.limit,
            offset=0,
        )

    items = [
        TimelineEventOut(
            title=ev.title,
            summary=ev.summary,
            event_date=ev.event_date_iso,
            participants=ev.participants,
        )
        for ev in events
    ]
    return TimelineResponse(found=True, events=items, count=len(items), total=total)
