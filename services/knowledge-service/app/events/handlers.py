"""K14.5 + K14.6 + K14.7 + C4 — Event handlers.

Each handler processes one event type:
  - chat.turn_completed     → K14.5: queue or extract chat turn
  - chapter.published       → CM3b/CM3c: canon=published — queue graph
                              extraction + ingest L3 passages at the PINNED
                              revision (chapter.saved no longer canonizes)
  - chapter.unpublished     → CM3b/CM3c: retract graph evidence + passages
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

from app.db.repositories.extraction_leaves import ExtractionLeavesRepo
from app.db.repositories.extraction_pending import (
    ExtractionPendingQueueRequest,
    ExtractionPendingRepo,
)
from app.events.dispatcher import EventData
from app.events.gating import should_extract

__all__ = [
    "handle_chat_turn",
    "handle_chat_message_feedback",
    "handle_chapter_published",
    "handle_chapter_unpublished",
    "handle_chapter_scenes_reparsed",
    "handle_chapter_deleted",
    "handle_glossary_entity_updated",
    "handle_glossary_entity_merged",
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
            # FD-2: enqueue as 'chat' (matching the chat.turn_completed event's own
            # aggregate_type AND the worker-ai chat drainer's
            # `WHERE aggregate_type='chat'`). Previously 'chat_session' → the worker
            # never consumed these rows, so chat knowledge was never extracted.
            aggregate_type="chat",
            aggregate_id=_uuid(event.aggregate_id) or project_id,
        ),
    )


async def handle_chat_message_feedback(event: EventData, *, pool: asyncpg.Pool) -> None:
    """Track 4 P3b — chat.message_feedback handler (R-T4-02 feedback slice).

    Attributes a thumbs (±1) to the entities the session's context build surfaced
    around the rated turn: the P0 access rows stamped `last_session_id = session`
    with recency inside a ±10-minute window of the message. Advisory telemetry —
    every missing key degrades to a silent skip (old producers without the P3b
    payload keys, sessions with no project, no stamped rows). The boost only
    affects ranking once `salience_feedback_weight > 0` (measure-before-flip).
    """
    from datetime import datetime

    from app.db.repositories.entity_access import EntityAccessRepo

    payload = event.payload
    user_id = _uuid(payload.get("user_id"))
    project_id = _uuid(payload.get("project_id"))
    session_id = _uuid(payload.get("session_id"))
    rating = payload.get("rating")
    turn_at_raw = payload.get("message_created_at")
    if not (user_id and project_id and session_id) or rating not in (1, -1) or not turn_at_raw:
        logger.debug(
            "chat.message_feedback missing P3b keys — skipping (msg=%s)", event.message_id
        )
        return
    try:
        turn_at = datetime.fromisoformat(turn_at_raw)
    except (ValueError, TypeError):
        logger.debug("chat.message_feedback bad message_created_at — skipping")
        return

    boosted = await EntityAccessRepo(pool).apply_feedback(
        user_id, project_id, session_id, int(rating), turn_at,
    )
    if boosted:
        logger.info(
            "P3b: feedback %+d attributed to %d entities (session=%s project=%s)",
            rating, boosted, session_id, project_id,
        )


async def handle_chapter_published(event: EventData, *, pool: asyncpg.Pool) -> None:
    """Canon Model CM3b/CM3c — chapter.published handler (canon = published).

    Two canon writes, both pinned to the PUBLISHED revision (NOT the live
    draft), so only author-published content is canonized:
      1. **Graph (Pass-2):** queue `extraction_pending` (keep-LATEST re-arm);
         the worker-ai coalescing drainer (scope='chapters_pending') drains it,
         fetches each chapter's revision text (CM3a), and extracts.
      2. **CM3c — passages (L3 semantic):** ingest `:Passage` nodes from the
         pinned revision text (moved here from `chapter.saved`). Best-effort,
         inline (same cost profile as the old save-time ingest). On a transient
         revision-fetch failure existing passages are kept (not wiped).

    Re-publish RE-ARMS the chapter at the new revision (keep-LATEST via
    `upsert_chapter_pending`; passages delete-first → self-heal). Payload:
    {book_id, chapter_id, revision_id}. Resolves project via book_id; skips
    if the book has no knowledge project.

    NOTE: graph-job creation is worker-side (it resolves the extraction model
    config via run_snapshot); this handler only enqueues the graph work.
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

    # Pull embedding config alongside project/user so the passage ingester
    # doesn't re-query the project row (mirrors the old chapter.saved lookup).
    project_row = await pool.fetchrow(
        """
        SELECT project_id, user_id, embedding_model, embedding_dimension
        FROM knowledge_projects WHERE book_id = $1 LIMIT 1
        """,
        book_id,
    )
    if project_row is None:
        logger.debug(
            "No knowledge project for book %s — skipping chapter.published", book_id
        )
        return

    project_id = project_row["project_id"]
    user_id = project_row["user_id"]
    embedding_model = project_row["embedding_model"]
    embedding_dim = project_row["embedding_dimension"]

    # 1. Graph (Pass-2): queue first — fast + the critical canon path.
    repo = ExtractionPendingRepo(pool)
    await repo.upsert_chapter_pending(
        user_id, project_id, chapter_uuid, revision_id,
    )
    logger.info(
        "CM3b: chapter.published queued for extraction: chapter=%s revision=%s project=%s",
        chapter_id, revision_id, project_id,
    )

    # 2. CM3c — passages (L3): ingest from the pinned revision. Best-effort.
    await _ingest_published_passages(
        book_id=book_id,
        chapter_uuid=chapter_uuid,
        revision_id=revision_id,
        project_id=project_id,
        user_id=user_id,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
        pool=pool,
    )


async def _ingest_published_passages(
    *,
    book_id: UUID,
    chapter_uuid: UUID,
    revision_id: UUID,
    project_id: UUID,
    user_id: UUID,
    embedding_model: str | None,
    embedding_dim: int | None,
    pool: asyncpg.Pool | None = None,
) -> None:
    """CM3c — ingest L3 passages for a published chapter at its pinned revision.

    Extracted from `handle_chapter_published` for testability. No C12a
    chapter_range scope-gate (publish is an explicit per-chapter canon action →
    always ingest). Wholly best-effort: every failure path is non-fatal so the
    graph-queue (already written) is never blocked.
    """
    if not embedding_model or not embedding_dim:
        logger.debug(
            "CM3c: skipping passage ingest — project %s has no "
            "embedding_model/embedding_dimension configured",
            project_id,
        )
        return

    # Inline imports avoid circular imports at module load (events.consumer
    # loads handlers at startup before the Neo4j driver is wired). Kept OUTSIDE
    # the try/except so an ImportError crashes loud rather than being masked.
    from app.config import settings

    if not settings.neo4j_uri:
        logger.debug(
            "CM3c: skipping passage ingest — NEO4J_URI unset (Track 1 mode)"
        )
        return

    from app.clients.book_client import get_book_client
    from app.clients.embedding_client import get_embedding_client
    from app.db.neo4j import neo4j_session
    from app.extraction.passage_ingester import ingest_chapter_passages

    book_client = get_book_client()
    # CM4: stamp the passage chapter_index from book-service sort_order so the
    # L3 reading-order axis matches the graph's event_order. Best-effort — a
    # missing sort_order falls back to None (passages still ingest, just
    # un-ordered until the next publish/backfill).
    sort_orders = await book_client.get_chapter_sort_orders([chapter_uuid])
    chapter_index = sort_orders.get(chapter_uuid)

    try:
        async with neo4j_session() as session:
            await ingest_chapter_passages(
                session,
                book_client,
                get_embedding_client(),
                user_id=user_id,
                project_id=project_id,
                book_id=book_id,
                chapter_id=chapter_uuid,
                chapter_index=chapter_index,  # CM4: from book-service sort_order
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                revision_id=revision_id,
                # Transient pinned-revision-fetch failure must NOT wipe canon
                # passages (R3-WARN#1) — keep what we have.
                delete_stale_on_missing=False,
                # KG-ML M1 (C10) — meter embedding spend on the live publish path.
                pool=pool,
            )
    except Exception:
        logger.warning(
            "CM3c: passage ingest failed for chapter=%s project=%s — non-fatal",
            chapter_uuid, project_id, exc_info=True,
        )


async def handle_translation_published(event: EventData, *, pool: asyncpg.Pool) -> None:
    """KG-ML M2 — dual-index a chapter's ACTIVE translation as `source_lang`=target
    `:Passage` nodes.

    Fired when a translation version becomes active (manual publish / human edit /
    auto-promote — DD5). INDEX-ONLY: this NEVER re-extracts entities/relations
    (Layer 1 stays canonical, built from the source language only — R1). The vi
    passages share `source_id=chapter_id` but are distinct nodes via the
    language-scoped canonical id, carry the SAME `project_id` (so project/book
    purge cascades — AC8), and re-embed only THIS language on republish (the
    ingester's content-hash skip-gate dedups a no-op edit — R7).

    Payload: {book_id, chapter_id, target_language}. Resolves project via book_id;
    skips when the book has no knowledge project or no embedding model configured.
    Wholly best-effort — a failure must not block the event loop.
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    chapter_uuid = _uuid(payload.get("chapter_id"))
    target_language = (payload.get("target_language") or "").strip().lower()

    if book_id is None or chapter_uuid is None or not target_language:
        logger.warning(
            "translation.published missing book_id/chapter_id/target_language: %s",
            event.message_id,
        )
        return

    project_row = await pool.fetchrow(
        """
        SELECT project_id, user_id, embedding_model, embedding_dimension
        FROM knowledge_projects WHERE book_id = $1 LIMIT 1
        """,
        book_id,
    )
    if project_row is None:
        logger.debug(
            "No knowledge project for book %s — skipping translation.published", book_id
        )
        return
    embedding_model = project_row["embedding_model"]
    embedding_dim = project_row["embedding_dimension"]
    if not embedding_model or not embedding_dim:
        logger.debug(
            "translation.published: project for book %s has no embedding model — skipping",
            book_id,
        )
        return

    from app.config import settings as _settings
    if not _settings.neo4j_uri:
        logger.debug("translation.published: NEO4J_URI unset — skipping")
        return

    from app.clients.book_client import get_book_client
    from app.clients.embedding_client import get_embedding_client
    from app.clients.translation_client import get_translation_client
    from app.db.neo4j import neo4j_session
    from app.extraction.passage_ingester import ingest_chapter_passages

    # Fetch the ACTIVE translated text for this language.
    vi_text = await get_translation_client().get_active_translation_text(
        chapter_uuid, target_language,
    )
    if not vi_text:
        logger.info(
            "translation.published: no active %s text for chapter=%s — skipping",
            target_language, chapter_uuid,
        )
        return

    book_client = get_book_client()
    # Mirror chapter_index off the source chapter's sort_order so the vi reading
    # axis matches the zh passages + the graph event_order.
    sort_orders = await book_client.get_chapter_sort_orders([chapter_uuid])
    chapter_index = sort_orders.get(chapter_uuid)

    try:
        async with neo4j_session() as session:
            await ingest_chapter_passages(
                session,
                book_client,
                get_embedding_client(),
                user_id=project_row["user_id"],
                project_id=project_row["project_id"],
                book_id=book_id,
                chapter_id=chapter_uuid,
                chapter_index=chapter_index,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                canon=True,  # an active translation is canon for its language
                source_lang=target_language,
                text_override=vi_text,
                pool=pool,
            )
    except Exception:
        logger.warning(
            "translation.published: dual-index failed chapter=%s lang=%s — non-fatal",
            chapter_uuid, target_language, exc_info=True,
        )


async def handle_chapter_unpublished(event: EventData, *, pool: asyncpg.Pool) -> None:
    """Canon Model CM3b/CM3c — chapter.unpublished handler.

    Retracts the chapter's extracted canon from BOTH layers (canon=published
    symmetry — unpublish removes what publish added):
      - **Graph:** `remove_evidence_for_source` (decrements the per-target
        evidence counter properly — unlike chapter.deleted's raw DETACH DELETE),
        so re-publishing later cleanly re-extracts. Closes D-CM1-UNPUBLISH-RETRACT.
      - **CM3c — passages (L3):** `delete_passages_for_source` so the semantic
        index doesn't retain published-era passages after unpublish.
    Zero-evidence orphans are swept by the periodic reconcile job, not here.
    Both retracts are INDEPENDENT best-effort steps (own try) so one failing
    doesn't suppress the other (R3-WARN#2).

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

    # Graph retract (independent best-effort).
    try:
        from app.db.neo4j import neo4j_session
        from app.db.neo4j_repos.provenance import remove_evidence_for_natural_key

        async with neo4j_session() as session:
            # CM3b-RETRACT-FIX: retract by NATURAL KEY. The prior call passed the
            # raw chapter_id to `remove_evidence_for_source`, which matches the
            # HASHED ExtractionSource id — so it removed ZERO edges and unpublish
            # never actually retracted the chapter's canon. The natural-key helper
            # hashes (user, project, "chapter", chapter_id) the same way the
            # publish-time extraction wrote the source.
            #
            # Dropping evidence to 0 is the correctness fix: the chapter's
            # nodes become invisible to the `evidence_count >= 1` reads, so the
            # canon is effectively retracted. We deliberately DO NOT sweep the
            # zero-evidence orphans here (/review-impl MED): this handler runs in
            # the events consumer, OUTSIDE the one-active-job-per-project
            # extraction lock, so a `cleanup_zero_evidence_nodes` call could race
            # a concurrent same-project extraction and delete an in-flight node
            # in its merge→add_evidence window. The offline K11.9 reconciler GCs
            # the now-orphaned nodes safely.
            removed = await remove_evidence_for_natural_key(
                session,
                user_id=str(user_id),
                project_id=str(project_id),
                source_type="chapter",
                source_id=str(chapter_id),
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

    # CM3c — passage retract (INDEPENDENT best-effort: a graph-retract failure
    # above must NOT suppress this, else published-era passages linger in the
    # semantic index after unpublish — R3-WARN#2).
    try:
        from app.db.neo4j import neo4j_session
        from app.db.neo4j_repos.passages import delete_passages_for_source

        async with neo4j_session() as session:
            deleted = await delete_passages_for_source(
                session,
                user_id=str(user_id),
                source_type="chapter",
                source_id=str(chapter_id),
            )
        logger.info(
            "CM3c: chapter.unpublished retracted passages: chapter=%s project=%s "
            "passages_deleted=%d",
            chapter_id, project_id, deleted,
        )
    except Exception:
        logger.warning(
            "CM3c: chapter.unpublished passage retract failed for chapter=%s "
            "project=%s — non-fatal",
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


async def handle_chapter_scenes_reparsed(event: EventData, *, pool: asyncpg.Pool) -> None:
    """IX-10 (spec 26) — chapter.scenes_reparsed handler (RB-5 consumer side).

    Book-service re-parses a chapter's index (`scenes` rows) whenever its
    pinned published revision changes — in the publish request path (IX-2) or
    the background sweeper (IX-3) — and emits `chapter.scenes_reparsed` in the
    SAME transaction as the index upsert. The parse leaves the graph reads
    (P2 extraction, F7) just moved under it, so this handler invalidates the
    knowledge extraction cache for the affected book, book-scoped, so the next
    extraction re-derives from the fresh index.

    This wires the F6 orphaned invalidation logic (`ExtractionLeavesRepo.
    delete_by_book`, the same path the `/invalidate-cache/{book_id}` endpoint
    already exposes but nothing called) to its event trigger.

    FROZEN payload (spec 26 IX-10, must equal book-service's producer — 4 fields):
      {book_id, chapter_id, published_revision_id, parse_version}
    Consumed here: `book_id` (the invalidation scope, required) and
    `chapter_id` (log/scope; falls back to the aggregate id per the chapter.*
    convention). `published_revision_id`/`parse_version` are observability fields —
    the invalidation is book-scoped, not per-revision, so it tolerates additional
    or absent observability fields (only `book_id` is load-bearing).

    Idempotent (at-least-once safe): `delete_by_book` deletes the book's leaf
    rows; a redelivered event finds them already gone → deletes 0 → clean
    no-op. Correctness never depends on it — `task_id` keys on the text hash
    (F6/SR-4), so a changed leaf naturally cache-misses; this delete is
    hygiene (dead leaf + claim rows) that also lets the F6 endpoint's logic
    finally fire on the real trigger. Benign race with the chapter.published
    extraction handler is stated in the spec (§Cross-service events): worst
    case is a deleted-then-recomputed cache entry — cost, never corruption.

    A malformed payload (missing/invalid book_id) is a clean skip, never a
    raise, so one bad event can't wedge the consumer loop.
    """
    payload = event.payload
    book_id = _uuid(payload.get("book_id"))
    # chapter_id rides the payload (frozen shape); tolerate the chapter.*
    # convention where it also arrives as the aggregate id.
    chapter_id = payload.get("chapter_id") or event.aggregate_id

    if book_id is None:
        logger.warning(
            "chapter.scenes_reparsed missing/invalid book_id: %s", event.message_id
        )
        return

    # Book-scoped cache invalidation (all extraction ops) — the existing F6
    # path, reused (not reinvented). Best-effort: a failure propagates to the
    # consumer's retry → DLQ policy (K14.8) so a transient DB blip redelivers;
    # the delete is idempotent so a redelivery is safe.
    deleted_leaves, deleted_raw = await ExtractionLeavesRepo(pool).delete_by_book(book_id)
    logger.info(
        "IX-10: chapter.scenes_reparsed invalidated extraction cache: book=%s "
        "chapter=%s parse_version=%s deleted_leaves=%d deleted_raw=%d",
        book_id, chapter_id, payload.get("parse_version"),
        deleted_leaves, deleted_raw,
    )


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
    handle_chapter_published. If no knowledge project exists for the book, the
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
    # as _ingest_published_passages. Kept OUTSIDE the try/except so an
    # ImportError crashes loud rather than being masked as a transient failure.
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


async def handle_glossary_entity_merged(
    event: EventData, *, pool: asyncpg.Pool,
) -> None:
    """mui #1c — glossary.entity_merged handler (KG consolidation side).

    glossary merged a loser entity into a winner (user-confirmed). Consolidate
    the derived KG: merge the loser's :Entity node into the winner's, and
    register the loser's names in entity_alias_map so a future extraction of
    those names routes to the winner (anti-resurrection) rather than recreating
    the loser.

    Payload (glossary outbox insertMergedOutboxEvent):
      book_id, winner_glossary_id, loser_glossary_id, op ("merged"|"unmerged").

    `op="unmerged"` is a best-effort no-op: a full KG un-merge is intractable
    (DETACH DELETE is irreversible), but the KG is DERIVED — the winner's
    glossary.entity_updated re-sync + re-extraction reconverge the graph after a
    glossary un-merge. The alias-map row stays (harmless: it only redirects
    extraction; the restored loser is re-anchored on its next entity_updated).

    glossary_conflict bypass: both nodes carry glossary anchors, which
    merge_entities normally REFUSES (it guards user-initiated KG merges from
    desyncing the two SSOT anchors). Here the merge IS glossary-authorized, so
    we first clear the loser's (now-stale, its glossary entity is gone) anchor,
    then merge.

    Idempotent: a redelivered merge finds the loser node already gone (its
    glossary_entity_id cleared + node deleted) → clean no-op.
    """
    payload = event.payload
    if payload.get("op") == "unmerged":
        logger.info(
            "glossary.entity_merged op=unmerged (%s) — KG reconverges via "
            "re-extraction; no-op",
            event.message_id,
        )
        return

    book_id = _uuid(payload.get("book_id"))
    winner_gid = _uuid(payload.get("winner_glossary_id"))
    loser_gid = _uuid(payload.get("loser_glossary_id"))
    if book_id is None or winner_gid is None or loser_gid is None:
        logger.warning(
            "glossary.entity_merged missing ids: %s", event.message_id
        )
        return

    # D-KG-GLOSSARY-FK-GLOBAL-UNIQUE: consolidate in EVERY knowledge project of the
    # book, not just an arbitrary `LIMIT 1` row. The glossary FK is now unique per
    # (user, project), so a book with two projects has one node per project for the
    # same entity and each must be merged. This also fixes the pre-existing drift the
    # old `LIMIT 1` caused (flagged in this function's own review-impl MED-2 comment).
    project_rows = await pool.fetch(
        "SELECT project_id, user_id FROM knowledge_projects WHERE book_id = $1",
        book_id,
    )
    if not project_rows:
        logger.debug(
            "No knowledge project for book %s — skipping merge sync", book_id
        )
        return

    from app.config import settings

    if not settings.neo4j_uri:
        logger.debug(
            "glossary.entity_merged: NEO4J_URI unset (Track 1) — skipping"
        )
        return

    from app.db.neo4j import neo4j_session
    from app.db.neo4j_repos.canonical import canonicalize_entity_name
    from app.db.neo4j_repos.entities import (
        MergeEntitiesError,
        get_entity_by_glossary_id,
        link_to_glossary,
        merge_entities,
        unlink_from_glossary,
    )
    from app.db.repositories.entity_alias_map import EntityAliasMapRepo

    repo = EntityAliasMapRepo(pool)
    consolidated = 0

    # One consolidation per knowledge project of the book. Each project owns its own
    # node for a given glossary entity (the FK is unique per (user, project)), so a
    # merge in one project says nothing about the others. A project whose nodes are
    # absent is a clean no-op; a project whose merge FAILS re-raises so the consumer
    # redelivers the whole event (each project's step is individually idempotent).
    for project_row in project_rows:
        project_id = project_row["project_id"]
        user_id = project_row["user_id"]
        uid = str(user_id)
        pid = str(project_id)

        async with neo4j_session() as session:
            loser = await get_entity_by_glossary_id(
                session, user_id=uid, project_id=pid,
                glossary_entity_id=str(loser_gid),
            )
            winner = await get_entity_by_glossary_id(
                session, user_id=uid, project_id=pid,
                glossary_entity_id=str(winner_gid),
            )
            if loser is None or winner is None:
                # Either node not yet in the KG (extraction never ran for it) or the
                # loser already merged (redelivery). Nothing to consolidate; the
                # winner's own entity_updated event syncs its (folded) aliases.
                logger.info(
                    "glossary.entity_merged: KG nodes absent in project=%s "
                    "(loser=%s winner=%s) — no-op, reconverges",
                    pid, loser is not None, winner is not None,
                )
                continue

            # Capture loser fields BEFORE surgery (the node is gone after merge).
            loser_id = loser.id
            loser_name = loser.name
            loser_canon = loser.canonical_name
            loser_aliases = list(loser.aliases)
            loser_kind = loser.kind
            winner_id = winner.id
            # project_scope MUST match the read side: the extraction resolver looks
            # up alias_map with the ENTITY's project_id (`project_id or "global"`),
            # and the user-merge route writes with source.project_id — use the
            # node's own project. (review-impl MED-2.)
            scope = loser.project_id or "global"

            # Clear the loser's stale glossary anchor so merge_entities doesn't
            # raise glossary_conflict, then consolidate.
            await unlink_from_glossary(session, user_id=uid, canonical_id=loser_id)
            try:
                await merge_entities(
                    session, user_id=uid, source_id=loser_id, target_id=winner_id,
                )
            except MergeEntitiesError as exc:
                if exc.error_code == "same_entity":
                    continue  # already one node (redelivery) — idempotent no-op
                # review-impl MED-1: the unlink already COMMITTED; if the merge
                # failed, the loser is now un-anchored and a redelivery's
                # glossary-id lookup would MISS it (unrecoverable orphan + broken
                # anti-resurrection). Re-link the loser so redelivery retries
                # cleanly. Use a fresh session (the merge's own tx is unwound).
                try:
                    async with neo4j_session() as relink_session:
                        await link_to_glossary(
                            relink_session, user_id=uid, canonical_id=loser_id,
                            glossary_entity_id=str(loser_gid), name=loser_name,
                            kind=loser_kind, aliases=loser_aliases,
                        )
                except Exception:  # noqa: BLE001
                    logger.error(
                        "glossary.entity_merged: merge FAILED and re-link FAILED for "
                        "loser=%s project=%s — orphaned un-anchored node, recover via "
                        "scripts/backfill_entity_alias_map.py", loser_gid, pid,
                        exc_info=True,
                    )
                raise  # propagate so the consumer redelivers/DLQs

        # Anti-resurrection: register loser's canonicalized names → winner. Postgres
        # I/O, outside the neo4j session. Best-effort (the KG merge already
        # committed); recoverable via scripts/backfill_entity_alias_map.py.
        canonicals: set[str] = {canonicalize_entity_name(a) for a in loser_aliases}
        if loser_canon:
            canonicals.add(canonicalize_entity_name(loser_canon))
        for ca in canonicals:
            if not ca:
                continue
            try:
                await repo.record_merge(
                    user_id=user_id,
                    project_scope=scope,
                    kind=loser_kind,
                    canonical_alias=ca,
                    target_entity_id=winner_id,
                    source_entity_id=loser_id,
                )
            except Exception:  # noqa: BLE001 — alias-map is best-effort
                logger.warning(
                    "glossary.entity_merged: alias-map record_merge failed for %r "
                    "(non-fatal)", ca, exc_info=True,
                )
        consolidated += 1
        logger.info(
            "mui#1c: KG consolidated loser=%s into winner=%s (project=%s)",
            loser_gid, winner_gid, pid,
        )

    if not consolidated:
        logger.info(
            "glossary.entity_merged: nothing consolidated for book=%s across %d "
            "project(s) — reconverges", book_id, len(project_rows),
        )


def _uuid(val: str | None) -> UUID | None:
    """Parse a UUID string, returning None on failure."""
    if not val:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None
