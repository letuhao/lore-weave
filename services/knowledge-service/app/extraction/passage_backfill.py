"""D-KG-PASSAGES-NOT-INGESTED — reusable per-project passage backfill.

Passages are ingested on the live `chapter.published` event (CM3c), but that path
SKIPS when the project has no embedding config at publish time — e.g. a KG project
linked to a book AFTER its chapters were published gets 0 passages, leaving semantic
memory/story search empty. This helper (re)ingests a project's published-chapter
passages from their pinned revisions, so semantic search has chapter-body data.

Shared by:
  • the admin route `POST /internal/projects/{id}/backfill-passages`, and
  • the extraction-start auto-trigger (the user's "index my book" action, where the
    embedding config + book link are guaranteed present) — so passages get built
    whenever the book is indexed, not only on the live publish event.

Idempotent (`ingest_chapter_passages` re-ingests by content hash — unchanged chapters
skip the re-embed). Wholly best-effort: a per-chapter failure is logged and skipped.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.db.neo4j import neo4j_session
from app.extraction.passage_ingester import ingest_chapter_passages

logger = logging.getLogger(__name__)


async def backfill_project_passages(
    *,
    project_id: UUID,
    user_id: UUID,
    book_id: UUID,
    embedding_model: str,
    embedding_dim: int,
    book_client,
    embedding_client,
    chapter_range: tuple[int, int] | None = None,
) -> dict:
    """(Re)ingest passages for a book's published chapters into ``project_id``.

    ``chapter_range=(lo, hi)`` (inclusive ``sort_order``) bounds the backfill to a slice
    (D-BACKFILL-NO-SCOPE-LIMIT) — the extraction-start caller passes the job's own
    chapter_range so passages are ingested ONLY for the chapters being extracted, never
    the whole book. Returns per-run counts. Callers guarantee the embedding config
    (``embedding_model``/``embedding_dim``) + Neo4j are present before calling."""
    # WS-0.6: enumerate the chapters in the KNOWLEDGE GRAPH, not the published ones.
    # Both the enumeration and the revision pin below must move together — either alone
    # still yields zero passages.
    chapters = await book_client.list_chapters(book_id, kg_indexed=True)
    if chapters is None:
        return {
            "chapters_ingested": 0, "passages_created": 0, "chapters_failed": 0,
            "error": "book_service_unavailable",
        }

    if chapter_range is not None:
        lo, hi = chapter_range
        chapters = [
            ch for ch in chapters
            if isinstance(ch.get("sort_order"), int) and lo <= ch["sort_order"] <= hi
        ]

    ingested = passages = failed = 0
    for ch in chapters:
        # Pin the revision the KNOWLEDGE LAYER reflects (possibly a draft the user
        # explicitly indexed), falling back to the published revision for safety.
        rev = ch.get("kg_indexed_revision_id") or ch.get("published_revision_id")
        cid = ch.get("chapter_id")
        if not rev or not cid:
            # Was a bare `continue`. A chapter that is IN the graph but has no pinned
            # revision is a real anomaly (the sweeper cannot heal it either) — say so,
            # rather than silently ingesting zero passages for it.
            logger.warning(
                "WS-0.6: chapter %s is kg-indexed but has no pinned revision — skipping "
                "passage ingest; re-index it to pin a revision",
                cid,
            )
            continue
        # review-impl P0/P1 — DERIVE canon; do NOT accept ingest_chapter_passages'
        # `canon: bool = True` default.
        #
        # WS-0.6b re-keyed the ENUMERATION above onto kg_indexed=True, which now returns
        # never-published, user-indexed DRAFT chapters. The canon flag was left on its
        # True default, so this backfill silently CANONIZED them — overwriting the correct
        # canon=False that handle_chapter_kg_indexed had just written. And the content-hash
        # skip-gate does not save us: it requires `state["canon"] == canon`, so a
        # False→True flip is a deliberate cache MISS that delete-then-upserts at canon=True.
        #
        # The result: unreviewed draft prose returned from every `surface=canon` read
        # (chat grounding's default, wiki, story search) — and `surface=canon`, the exact
        # control that exists to exclude it, could no longer filter it out.
        #
        # The rule is spec §3.7 / P1-8: canon = (revision_id == published_revision_id).
        # The data was already on the row and was being thrown away.
        published_rev = ch.get("published_revision_id")
        canon = bool(published_rev) and str(published_rev) == str(rev)
        try:
            async with neo4j_session() as session:
                res = await ingest_chapter_passages(
                    session, book_client, embedding_client,
                    user_id=user_id, project_id=project_id, book_id=book_id,
                    chapter_id=UUID(cid), chapter_index=ch.get("sort_order"),
                    embedding_model=embedding_model, embedding_dim=embedding_dim,
                    revision_id=UUID(rev),
                    canon=canon,
                    # A transient revision-fetch miss must not wipe existing canon.
                    delete_stale_on_missing=False,
                )
            ingested += 1
            passages += res.chunks_created
        except Exception:
            failed += 1
            logger.warning(
                "backfill_project_passages: chapter=%s project=%s failed — continuing",
                cid, project_id, exc_info=True,
            )

    return {
        "chapters_ingested": ingested,
        "passages_created": passages,
        "chapters_failed": failed,
    }
