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

    Two side effects:
      1. Queue the chapter in `extraction_pending` so worker-ai can
         run Pass 2 LLM extraction later (K14.6 original).
      2. **D-K18.3-01**: ingest passages for K18.3 L3 semantic search
         (fetch text → chunk → embed → upsert `:Passage` nodes).

    Both are idempotent and independent — passage ingestion runs
    even if extraction is paused/disabled on the project, because L3
    passages are useful for Mode 3 regardless of extraction state.

    Note: book-service outbox payload is `{"book_id": "<uuid>"}` — no
    user_id. We resolve user_id from knowledge_projects via book_id
    (book_id is globally unique).
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    chapter_id = event.aggregate_id

    if not chapter_id or book_id is None:
        logger.warning("chapter.saved missing chapter_id or book_id: %s", event.message_id)
        return

    # Look up project + user + embedding config via book_id (globally unique).
    # We pull embedding_model + embedding_dimension so the ingester doesn't
    # need to re-query the project row.
    project_row = await pool.fetchrow(
        """
        SELECT project_id, user_id, embedding_model, embedding_dimension
        FROM knowledge_projects WHERE book_id = $1 LIMIT 1
        """,
        book_id,
    )
    if project_row is None:
        logger.debug("No knowledge project for book %s — skipping chapter event", book_id)
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]
    embedding_model = project_row["embedding_model"]
    embedding_dim = project_row["embedding_dimension"]

    # 1. Queue for Pass 2 extraction.
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
    logger.info(
        "K14.6: chapter.saved queued for extraction: chapter=%s project=%s",
        chapter_id, project_id,
    )

    # 2. D-K18.3-01: ingest passages for L3 semantic search.
    if not embedding_model or not embedding_dim:
        logger.debug(
            "D-K18.3-01: skipping passage ingest — project %s has no "
            "embedding_model/embedding_dimension configured",
            project_id,
        )
        return

    # Inline imports avoid circular imports at module load (events.consumer
    # loads handlers at startup before the Neo4j driver is wired). Keep
    # imports OUTSIDE the try/except below so an ImportError crashes
    # loud — swallowing it as "non-fatal" would mask refactor bugs.
    from app.config import settings

    if not settings.neo4j_uri:
        logger.debug(
            "D-K18.3-01: skipping passage ingest — NEO4J_URI unset (Track 1 mode)"
        )
        return

    from app.clients.book_client import get_book_client
    from app.clients.embedding_client import get_embedding_client
    from app.db.neo4j import neo4j_session
    from app.db.repositories.extraction_jobs import ExtractionJobsRepo
    from app.extraction.passage_ingester import ingest_chapter_passages

    chapter_uuid = _uuid(chapter_id)
    if chapter_uuid is None:
        return

    # C12a (D-K16.2-02b) — honour running chapter-scope jobs'
    # ``scope_range.chapter_range``. Only skip when there's at least
    # one active ``scope='chapters'`` job with a bounded range AND
    # this chapter's sort_order falls outside ALL such ranges (disjoint
    # union check). Graceful degrade: if we can't fetch sort_order,
    # over-ingest rather than risk missing a valid chapter.
    jobs_repo = ExtractionJobsRepo(pool)
    active_jobs = await jobs_repo.list_active_for_project(user_id, project_id)
    chapter_scope_ranges: list[tuple[int, int]] = []
    has_unbounded_chapter_job = False
    for job in active_jobs:
        if job.scope != "chapters":
            continue
        rng = (job.scope_range or {}).get("chapter_range")
        if (
            isinstance(rng, (list, tuple))
            and len(rng) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in rng)
        ):
            chapter_scope_ranges.append((int(rng[0]), int(rng[1])))
        else:
            has_unbounded_chapter_job = True
            break

    if chapter_scope_ranges and not has_unbounded_chapter_job:
        # All chapter-scope active jobs are bounded; check if this
        # chapter's sort_order falls in ANY of them (disjoint union).
        bc = get_book_client()
        sort_orders = await bc.get_chapter_sort_orders([chapter_uuid])
        chapter_sort_order = sort_orders.get(chapter_uuid)
        if chapter_sort_order is None:
            # Book-service unavailable or chapter not found — over-
            # ingest defensively. Skipping on uncertainty risks silent
            # data loss.
            logger.debug(
                "D-K16.2-02b: could not resolve sort_order for chapter=%s; "
                "proceeding with ingest",
                chapter_uuid,
            )
        else:
            in_any_range = any(
                lo <= chapter_sort_order <= hi
                for lo, hi in chapter_scope_ranges
            )
            if not in_any_range:
                logger.debug(
                    "D-K16.2-02b: skipping ingest — chapter %s sort_order=%d "
                    "outside all active chapter_ranges %s",
                    chapter_uuid, chapter_sort_order, chapter_scope_ranges,
                )
                return

    try:
        async with neo4j_session() as session:
            await ingest_chapter_passages(
                session,
                get_book_client(),
                get_embedding_client(),
                user_id=user_id,
                project_id=project_id,
                book_id=book_id,
                chapter_id=chapter_uuid,
                chapter_index=None,  # book-service doesn't expose sort_order here yet
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
            )
    except Exception:
        logger.warning(
            "D-K18.3-01: passage ingest failed for chapter=%s project=%s — non-fatal",
            chapter_id, project_id, exc_info=True,
        )


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
        # + D-K18.3-01 :Passage nodes for this chapter. Best-effort
        # (Neo4j may not be configured).
        try:
            from app.config import settings
            if settings.neo4j_uri:
                from app.db.neo4j import neo4j_session
                from app.extraction.passage_ingester import (
                    delete_chapter_passages,
                )
                chapter_uuid = _uuid(chapter_id)
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
                    # D-K18.3-01: drop the chapter's passages too.
                    if chapter_uuid is not None:
                        passage_count = await delete_chapter_passages(
                            session,
                            user_id=user_id,
                            chapter_id=chapter_uuid,
                        )
                    else:
                        passage_count = 0
                    logger.info(
                        "K14.7: chapter deleted cascade: chapter=%s project=%s "
                        "passages_deleted=%d",
                        chapter_id, project_id, passage_count,
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
