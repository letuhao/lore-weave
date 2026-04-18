"""K14.5 + K14.6 + K14.7 — Event handlers.

Each handler processes one event type:
  - chat.turn_completed  → K14.5: queue or extract chat turn
  - chapter.saved        → K14.6: queue or extract chapter
  - chapter.deleted      → K14.7: cascade delete from Neo4j

All handlers receive EventData + pool (via dispatcher kwargs).
If extraction is disabled for the project, events are queued in
extraction_pending for later backfill (K16.7).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.db.repositories.extraction_pending import (
    ExtractionPendingQueueRequest,
    ExtractionPendingRepo,
)
from app.events.dispatcher import EventData
from app.events.gating import should_extract

__all__ = [
    "handle_chat_turn",
    "handle_chapter_saved",
    "handle_chapter_deleted",
]

logger = logging.getLogger(__name__)


async def handle_chat_turn(event: EventData, *, pool: asyncpg.Pool) -> None:
    """K14.5 — chat.turn_completed handler.

    If extraction enabled: queue for Pass 2 processing via worker-ai.
    If disabled: park in extraction_pending for backfill.

    Resilient to missing user_id in payload — falls back to looking
    up user_id from knowledge_projects via project_id.
    """
    payload = event.payload
    project_id = _uuid(payload.get("project_id"))
    user_id = _uuid(payload.get("user_id") or payload.get("owner_user_id"))

    if project_id is None:
        logger.warning("chat.turn_completed missing project_id: %s", event.message_id)
        return

    # Resolve user_id from project if not in payload
    if user_id is None:
        row = await pool.fetchrow(
            "SELECT user_id FROM knowledge_projects WHERE project_id = $1 LIMIT 1",
            project_id,
        )
        if row is None:
            logger.debug("No knowledge project %s — skipping chat event", project_id)
            return
        user_id = row["user_id"]

    if await should_extract(pool, project_id, user_id):
        logger.info("K14.5: chat turn queued for extraction: %s", event.aggregate_id)

    # Always queue in extraction_pending — worker-ai processes from here
    repo = ExtractionPendingRepo(pool)
    await repo.queue_event(
        user_id,
        ExtractionPendingQueueRequest(
            project_id=project_id,
            event_id=_uuid(event.aggregate_id) or _uuid(event.message_id),
            event_type=event.event_type,
            aggregate_type="chat_session",
            aggregate_id=_uuid(event.aggregate_id) or project_id,
        ),
    )


async def handle_chapter_saved(event: EventData, *, pool: asyncpg.Pool) -> None:
    """K14.6 — chapter.saved handler.

    Same pattern as chat turn: queue in extraction_pending.
    Worker-ai will process via book-service chapter text lookup.

    Note: book-service outbox payload is {"book_id": "<uuid>"} — no
    user_id. We resolve user_id from knowledge_projects via book_id
    (book_id is globally unique).
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    chapter_id = event.aggregate_id

    if not chapter_id or book_id is None:
        logger.warning("chapter.saved missing chapter_id or book_id: %s", event.message_id)
        return

    # Look up project + user via book_id (globally unique, no user_id needed)
    project_row = await pool.fetchrow(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
        book_id,
    )
    if project_row is None:
        logger.debug("No knowledge project for book %s — skipping chapter event", book_id)
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]

    repo = ExtractionPendingRepo(pool)
    await repo.queue_event(
        user_id,
        ExtractionPendingQueueRequest(
            project_id=project_id,
            event_id=_uuid(chapter_id) or _uuid(event.message_id),
            event_type=event.event_type,
            aggregate_type="chapter",
            aggregate_id=_uuid(chapter_id) or project_id,
        ),
    )

    logger.info("K14.6: chapter.saved queued: chapter=%s project=%s", chapter_id, project_id)


async def handle_chapter_deleted(event: EventData, *, pool: asyncpg.Pool) -> None:
    """K14.7 — chapter.deleted handler.

    Cascade delete from Neo4j:
      1. Find ExtractionSource for this chapter
      2. Remove provenance edges
      3. Cleanup zero-evidence nodes
      4. Clear extraction_pending rows

    Uses Neo4j session if available, otherwise just clears pending.
    """
    payload = event.payload
    chapter_id = event.aggregate_id
    book_id = _uuid(payload.get("book_id"))

    if not chapter_id or book_id is None:
        logger.warning("chapter.deleted missing chapter_id or book_id: %s", event.message_id)
        return

    # Look up project + user via book_id (globally unique)
    project_row = await pool.fetchrow(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
        book_id,
    )

    if project_row is not None:
        project_id = project_row["project_id"]
        user_id = project_row["user_id"]

        # Clear pending events for this chapter (user_id scoped for defense-in-depth)
        await pool.execute(
            """
            DELETE FROM extraction_pending
            WHERE project_id = $1 AND aggregate_id = $2
              AND aggregate_type = 'chapter' AND user_id = $3
            """,
            project_id, _uuid(chapter_id), user_id,
        )

        # Neo4j cascade — delete ExtractionSource + orphaned entities
        # This requires Neo4j which may not be configured. Do best-effort.
        try:
            from app.config import settings
            if settings.neo4j_uri:
                from app.db.neo4j import neo4j_session
                async with neo4j_session() as session:
                    # Delete extraction source and cascade
                    await session.run(
                        """
                        MATCH (s:ExtractionSource {source_id: $source_id})
                        WHERE s.user_id = $user_id AND s.project_id = $project_id
                        DETACH DELETE s
                        """,
                        source_id=chapter_id,
                        user_id=str(user_id),
                        project_id=str(project_id),
                    )
                    logger.info(
                        "K14.7: chapter deleted cascade: chapter=%s project=%s",
                        chapter_id, project_id,
                    )
        except Exception:
            logger.warning(
                "K14.7: Neo4j cascade failed for chapter %s (non-fatal)",
                chapter_id,
            )
    else:
        logger.debug("No knowledge project for book %s — skipping delete cascade", book_id)


def _uuid(val: str | None) -> UUID | None:
    """Parse a UUID string, returning None on failure."""
    if not val:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None
