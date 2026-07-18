"""C-merge C2 — the manuscript-parts → structure_node mirror consumer.

A SEPARATE consumer (own group) from the written-verdict CompositionEventConsumer, so C4 deletes this
file + its one worker registration cleanly without touching the permanent mirror.

book-service emits `manuscript_part.changed {book_id}` (aggregate_type='book' → loreweave:events:book)
on any part mutation. This RE-READS the book's active parts and reconciles the kind='part' structure_node
rows — minimal event + re-read ⇒ idempotent and order-insensitive under at-least-once redelivery
(the chapter.scenes_linked discipline). A book-service read failure RAISES so the base retries and
(after max_retries) dead-letters — never a reconcile-to-empty that would blank a real book's groupings.

TEMPORARY: removed at C4 when parts is retired and structure_node is the sole SSOT.
"""
from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from loreweave_jobs import BaseProjectionConsumer

from app.clients.book_client import BookClient, BookClientError
from app.events.consumer import _parse
from app.services.parts_mirror_service import reconcile_book_parts

logger = logging.getLogger(__name__)

BOOK_STREAM = "loreweave:events:book"
GROUP_NAME = "composition-parts-mirror"
PART_CHANGED = "manuscript_part.changed"


class PartsMirrorConsumer(BaseProjectionConsumer):
    """Reconciles the kind='part' structure_node mirror from book-service part events."""

    streams = [BOOK_STREAM]
    group = GROUP_NAME
    max_retries = 3
    block_ms = 5000
    reclaim_every_n_loops = 12
    reclaim_min_idle_ms = 30000
    consumer_name_prefix = "pm"
    retry_prefix = "pm:retry"

    def __init__(
        self, redis_url: str, pool: asyncpg.Pool, *,
        book_base_url: str, internal_token: str, consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._book = BookClient(book_base_url, internal_token)

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        event = _parse(stream, msg_id, fields)
        if event is None:
            return  # unparseable — ack
        if event.event_type != PART_CHANGED:
            # The 'book' stream also carries grant/other book events; ignoring THOSE is correct.
            return
        book = event.payload.get("book_id") or event.aggregate_id
        if not book:
            logger.warning("manuscript_part.changed without book_id: %s", event.payload)
            return
        book_id = UUID(str(book))
        try:
            parts = await self._book.list_parts_mirror(book_id)
        except BookClientError:
            # UNKNOWN, not empty. RAISE so the base retries; the backfill sweep is the backstop, silence
            # is not (reconcile-to-empty would archive every real part until the next event).
            logger.warning("parts-mirror: book %s parts unreadable — will retry", book_id)
            raise
        await reconcile_book_parts(self._pool, book_id, parts)
