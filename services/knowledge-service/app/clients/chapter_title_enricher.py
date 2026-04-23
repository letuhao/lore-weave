"""C6 (D-K19b.3-01 + D-K19e-β-01) — denormalize book-service
chapter titles into Timeline events + ExtractionJob current-cursor
rows before serving them to the FE.

One HTTP round-trip per knowledge-service response instead of per-row:
each enricher collects the chapter_ids set from its input list,
fires a single batch POST to ``book-service /internal/chapters/titles``
via ``BookClient.get_chapter_titles``, and mutates the input objects
in-place to attach ``chapter_title`` / ``current_chapter_title``.

Graceful-degrade chain (every failure leaves the title ``None``):
  1. empty input → skip network entirely
  2. no matching chapter_ids in any row → skip network
  3. ``BookClient.get_chapter_titles`` returns ``{}`` on any HTTP
     error (timeout, 5xx, bad body) — enricher exits with every
     ``*_title`` still ``None``
  4. partial responses (some ids resolved, some missing) — the
     missing keys simply leave their ``*_title`` as ``None``; the
     FE falls back to ``chapterShort()`` for UUID-suffix display

Mutates the input Pydantic models directly (``model_config`` defaults
to mutable). The routers call these AFTER all filtering + pagination
so the batch size equals the response page size, never the full
underlying list.
"""

from __future__ import annotations

from uuid import UUID

from app.clients.book_client import BookClient
from app.db.neo4j_repos.events import Event
from app.db.repositories.extraction_jobs import ExtractionJob

__all__ = [
    "enrich_events_with_chapter_titles",
    "enrich_jobs_with_current_chapter_titles",
]


def _safe_uuid(raw: object) -> UUID | None:
    """Parse a UUID or return None. Defensive against malformed
    chapter_id strings in Neo4j / job cursors — we never want an
    enricher bug to 500 the whole response."""
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


async def enrich_events_with_chapter_titles(
    events: list[Event],
    book_client: BookClient,
) -> None:
    """Attach ``chapter_title`` to each event whose ``chapter_id``
    resolves via book-service. In-place mutation — returns ``None``.
    """
    if not events:
        return
    ids: list[UUID] = []
    for e in events:
        parsed = _safe_uuid(e.chapter_id)
        if parsed is not None:
            ids.append(parsed)
    if not ids:
        return
    # Dedup (events can share a chapter_id) — fewer bytes over the
    # wire without semantic change.
    unique_ids = list({i: None for i in ids}.keys())
    titles = await book_client.get_chapter_titles(unique_ids)
    if not titles:
        return
    for e in events:
        parsed = _safe_uuid(e.chapter_id)
        if parsed is not None:
            e.chapter_title = titles.get(parsed)


async def enrich_jobs_with_current_chapter_titles(
    jobs: list[ExtractionJob],
    book_client: BookClient,
) -> None:
    """For jobs whose ``current_cursor.last_chapter_id`` is present,
    resolve the title and attach as ``current_chapter_title``.
    In-place mutation — returns ``None``.

    Jobs without a cursor OR with a cursor that doesn't carry a
    last_chapter_id (e.g. chat-scope cursors use ``last_pending_id``)
    are left untouched.
    """
    if not jobs:
        return
    # Collect (job, chapter_id) pairs so we can map back after the
    # batch resolves.
    pairs: list[tuple[ExtractionJob, UUID]] = []
    for job in jobs:
        cursor = job.current_cursor or {}
        parsed = _safe_uuid(cursor.get("last_chapter_id"))
        if parsed is not None:
            pairs.append((job, parsed))
    if not pairs:
        return
    unique_ids = list({cid: None for _, cid in pairs}.keys())
    titles = await book_client.get_chapter_titles(unique_ids)
    if not titles:
        return
    for job, cid in pairs:
        job.current_chapter_title = titles.get(cid)
