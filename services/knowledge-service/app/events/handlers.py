"""K14.5 + K14.6 + K14.7 + C4 — Event handlers.

Each handler processes one event type:
  - chat.turn_completed     → K14.5: queue or extract chat turn
  - chapter.saved           → K14.6: queue or extract chapter
  - chapter.deleted         → K14.7: cascade delete from Neo4j
  - glossary.entity_updated → C4 (K14): trigger glossary_sync → Neo4j

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
    "handle_glossary_entity_updated",
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

    **D-K18.3-01**: ingest passages for K18.3 L3 semantic search
    (fetch text → chunk → embed → upsert `:Passage` nodes).

    Canon Model CM3b: graph-extraction (Pass 2) is no longer queued here —
    it triggers on `chapter.published` (canon = published). Passage ingestion
    still runs on save (moves to chapter.published in CM3c). It runs even if
    extraction is paused/disabled, because L3 passages are useful for Mode 3
    regardless of extraction state.

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

    # Canon Model CM3b: graph extraction (Pass 2) is NO LONGER queued on
    # chapter.saved — `handle_chapter_published` queues it at the pinned
    # published revision (canon = published), so unreviewed draft prose never
    # canonizes. Passage ingest (L3 semantic) stays here for now; it moves to
    # chapter.published in CM3c.

    # D-K18.3-01: ingest passages for L3 semantic search.
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


async def handle_chapter_published(event: EventData, *, pool: asyncpg.Pool) -> None:
    """Canon Model CM3b — chapter.published handler (canon = published).

    Queues the chapter for Pass-2 graph extraction at its PINNED published
    revision (NOT the live draft), so only author-published content is
    canonized. The worker-ai coalescing drainer (scope='chapters_pending')
    creates/runs the job that drains the queue, fetches each chapter's
    revision text via book-service (CM3a), and extracts.

    Re-publish RE-ARMS the chapter at the new revision (keep-LATEST via
    `upsert_chapter_pending`). Payload: {book_id, chapter_id, revision_id}.
    Resolves project via book_id; skips if the book has no knowledge project.

    NOTE: job creation is worker-side (it resolves the extraction model config
    via run_snapshot); this handler only enqueues.
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    chapter_id = event.aggregate_id
    revision_id = _uuid(payload.get("revision_id"))

    if not chapter_id or book_id is None:
        logger.warning(
            "chapter.published missing chapter_id or book_id: %s", event.message_id
        )
        return
    if revision_id is None:
        logger.warning(
            "chapter.published missing revision_id: %s — cannot pin canon revision",
            event.message_id,
        )
        return

    chapter_uuid = _uuid(chapter_id)
    if chapter_uuid is None:
        logger.warning("chapter.published non-UUID chapter_id: %s", chapter_id)
        return

    project_row = await pool.fetchrow(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
        book_id,
    )
    if project_row is None:
        logger.debug(
            "No knowledge project for book %s — skipping chapter.published", book_id
        )
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]

    repo = ExtractionPendingRepo(pool)
    await repo.upsert_chapter_pending(
        user_id, project_id, chapter_uuid, revision_id,
    )
    logger.info(
        "CM3b: chapter.published queued for extraction: chapter=%s revision=%s project=%s",
        chapter_id, revision_id, project_id,
    )


async def handle_chapter_unpublished(event: EventData, *, pool: asyncpg.Pool) -> None:
    """Canon Model CM3b — chapter.unpublished handler.

    Retracts the chapter's extracted canon from the KG (closes
    D-CM1-UNPUBLISH-RETRACT). Uses `remove_evidence_for_source` (decrements
    the per-target evidence counter properly — unlike chapter.deleted's raw
    DETACH DELETE), so re-publishing later cleanly re-extracts. Zero-evidence
    orphans are swept by the periodic reconcile job, not here (user-wide
    cleanup must not run concurrently with extraction). Best-effort.

    Also drops any unprocessed pending row for the chapter so a queued-but-
    not-yet-drained extraction doesn't re-canonize it.
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    chapter_id = event.aggregate_id

    if not chapter_id or book_id is None:
        logger.warning(
            "chapter.unpublished missing chapter_id or book_id: %s", event.message_id
        )
        return

    project_row = await pool.fetchrow(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
        book_id,
    )
    if project_row is None:
        logger.debug(
            "No knowledge project for book %s — skipping chapter.unpublished", book_id
        )
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]

    # Drop any unprocessed pending row so a not-yet-drained publish doesn't
    # re-canonize after unpublish (scoped by user for defense-in-depth).
    await pool.execute(
        """
        DELETE FROM extraction_pending
        WHERE project_id = $1 AND aggregate_id = $2
          AND aggregate_type = 'chapter' AND user_id = $3
          AND processed_at IS NULL
        """,
        project_id, _uuid(chapter_id), user_id,
    )

    from app.config import settings
    if not settings.neo4j_uri:
        return
    try:
        from app.db.neo4j import neo4j_session
        from app.db.neo4j_repos.provenance import remove_evidence_for_source

        async with neo4j_session() as session:
            removed = await remove_evidence_for_source(
                session, user_id=str(user_id), source_id=str(chapter_id),
            )
        logger.info(
            "CM3b: chapter.unpublished retracted canon: chapter=%s project=%s "
            "evidence_edges_removed=%d",
            chapter_id, project_id, removed,
        )
    except Exception:
        logger.warning(
            "CM3b: chapter.unpublished retract failed for chapter=%s project=%s — non-fatal",
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


async def handle_glossary_entity_updated(
    event: EventData, *, pool: asyncpg.Pool,
) -> None:
    """C4 (K14) — glossary.entity_updated handler.

    Triggers the EXISTING `sync_glossary_entity_to_neo4j` (K15.11) so a
    glossary entity write in glossary-service automatically lands in Neo4j
    — no manual /glossary-sync-entity call (resolves H1). This handler does
    NOT write Neo4j canonical content directly: it only invokes glossary_sync,
    which is the single SSOT→Neo4j path (Q2).

    Payload (from glossary-service outbox.go):
      book_id, glossary_entity_id, name, kind, aliases, short_description,
      op, source_type, emitted_at

    user_id/project_id are NOT in the payload — resolved here from the
    knowledge_projects table via book_id (globally unique), mirroring
    handle_chapter_saved. If no knowledge project exists for the book, the
    event is a clean no-op (the user hasn't enabled the KG for that book).

    Idempotency / at-least-once: Redis Streams may redeliver. The underlying
    glossary_sync MERGE is keyed on (user_id, glossary_entity_id), so
    re-processing the same event updates the node in place — never duplicates
    nodes/edges. Safe to replay.

    Neo4j unavailable (Track 1 / no NEO4J_URI) → clean skip: the canonical
    glossary data still lives in Postgres; a later scope='glossary_sync'
    backfill or the next event re-converges the graph once Neo4j is wired.
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    glossary_entity_id = _uuid(payload.get("glossary_entity_id")) or _uuid(
        event.aggregate_id
    )
    name = (payload.get("name") or "").strip()
    kind = (payload.get("kind") or "").strip()

    if book_id is None or glossary_entity_id is None:
        logger.warning(
            "glossary.entity_updated missing book_id/glossary_entity_id: %s",
            event.message_id,
        )
        return

    # A freshly-created draft can arrive with an empty name/kind (the
    # glossary create path emits before the name attribute is filled). We
    # cannot MERGE a meaningful entity without a name+kind — skip cleanly;
    # the follow-up PATCH/extract event carries the populated fields and
    # re-emits, at which point the MERGE (keyed on glossary_entity_id)
    # creates/updates the node. This is correct at-least-once behaviour,
    # not a dropped event.
    if not name or not kind:
        logger.debug(
            "glossary.entity_updated for %s has empty name/kind (op=%s) — "
            "skipping until a populated event arrives",
            glossary_entity_id, payload.get("op"),
        )
        return

    # Resolve project + user via book_id (globally unique).
    project_row = await pool.fetchrow(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1 LIMIT 1",
        book_id,
    )
    if project_row is None:
        logger.debug(
            "No knowledge project for book %s — skipping glossary sync", book_id
        )
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]

    # Neo4j must be configured to sync. In Track 1 mode there is no graph
    # to write — skip without error (canonical data is safe in Postgres).
    from app.config import settings

    if not settings.neo4j_uri:
        logger.debug(
            "glossary.entity_updated: NEO4J_URI unset (Track 1 mode) — "
            "skipping sync for entity %s",
            glossary_entity_id,
        )
        return

    aliases = payload.get("aliases")
    if not isinstance(aliases, list):
        aliases = []
    short_description = payload.get("short_description") or None

    # Inline imports avoid circular imports at module load (consumer loads
    # handlers at startup before the Neo4j driver is wired) — same pattern
    # as handle_chapter_saved. Kept OUTSIDE the try/except so an ImportError
    # crashes loud rather than being masked as a transient failure.
    from app.db.neo4j import neo4j_session
    from app.extraction.glossary_sync import sync_glossary_entity_to_neo4j

    # Let exceptions propagate to the consumer's DLQ/retry path (K14.8):
    # a transient Neo4j outage SHOULD redeliver, not silently drop the
    # propagation. The MERGE keeps redelivery idempotent.
    async with neo4j_session() as session:
        result = await sync_glossary_entity_to_neo4j(
            session,
            user_id=str(user_id),
            project_id=str(project_id),
            glossary_entity_id=str(glossary_entity_id),
            name=name,
            kind=kind,
            aliases=[str(a) for a in aliases],
            short_description=short_description,
        )
    logger.info(
        "C4: glossary.entity_updated synced to Neo4j: entity=%s action=%s project=%s",
        glossary_entity_id, result.get("action"), project_id,
    )


def _uuid(val: str | None) -> UUID | None:
    """Parse a UUID string, returning None on failure."""
    if not val:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None
