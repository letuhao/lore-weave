"""P3 (book-structure-pipeline spec 2026-07-20 §4.6, Option C) — composition's book-lifecycle mirror.

book-service emits ``book.lifecycle_changed`` {book_id} on every trash / restore / purge. This consumer
mirrors that lifecycle onto the ``book_lifecycle`` column of the two manuscript-structure ANCHOR tables
(structure_node = parts/arcs, composition_work = the Work), so a trashed / purge_pending book's structure is
soft-hidden from composition reads (``list_tree``, ``resolve_by_book``) WITHOUT overloading ``is_archived`` /
``status`` — those are USER-archive flags, and overloading them for book-trash would un-archive a user's
manually-archived acts on restore (the symmetric-un-archive-orphan bug).

WHY IT RE-READS rather than trusting the payload. The relay is at-least-once + UNORDERED, so a
trashed→restored→trashed redelivery in the wrong order could land the mirror on a stale value. The event
carries only {book_id}; this consumer RE-READS book-service's projection for the book's CURRENT lifecycle and
sets that — always converging to the truth NOW (the same design as the written-verdict mirror's re-read).

THE SILENT-SUCCESS FAILURE this guards against (knowledge-service's own comment names it): an UNREGISTERED
event_type dropped at DEBUG and ACKED — "acked into the void, a perfect silent success". REQUIRED_EVENTS + its
test make a depended-on-but-unhandled event a RED TEST, not a quiet afternoon of a silently stale mirror.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg
from loreweave_jobs import BaseProjectionConsumer

from app.clients.book_client import BookClient

logger = logging.getLogger(__name__)

#: The book-aggregate stream (platform convention loreweave:events:<aggregate>). book-service's outbox
#: relay auto-publishes aggregate_type='book' rows here (no relay config needed).
BOOK_STREAM = "loreweave:events:book"
GROUP_NAME = "composition-book-lifecycle"

#: The mirror is only correct if this event is handled. A depended-on event with no handler is the
#: silent-ack-into-void bug — REQUIRED_EVENTS + its unit test make that a RED TEST at construction.
REQUIRED_EVENTS = frozenset({"book.lifecycle_changed"})


class BookLifecycleConsumer(BaseProjectionConsumer):
    """Mirrors book-service's lifecycle_state onto composition's book_lifecycle anchor columns."""

    streams = [BOOK_STREAM]
    group = GROUP_NAME
    max_retries = 3
    block_ms = 5000
    reclaim_every_n_loops = 12
    reclaim_min_idle_ms = 30000
    consumer_name_prefix = "bl"
    retry_prefix = "bl:retry"

    def __init__(
        self, redis_url: str, pool: asyncpg.Pool, *,
        book_client: BookClient, consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._book_client = book_client
        # Parity with the written-verdict mirror: fail LOUDLY if a required event has no route.
        handled = {"book.lifecycle_changed"}
        missing = REQUIRED_EVENTS - handled
        if missing:
            raise RuntimeError(f"book-lifecycle mirror has no handler for {sorted(missing)}")

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        event_type = fields.get("event_type")
        if event_type not in REQUIRED_EVENTS:
            # loreweave:events:book may carry other book.* events later; ignoring THOSE is correct.
            # Ignoring one we depend on is the silent-success bug — REQUIRED_EVENTS stops it here.
            return
        payload = _parse_payload(fields)
        book_raw = payload.get("book_id") or fields.get("aggregate_id")
        if not book_raw:
            logger.warning("book.lifecycle_changed without book_id: %s", fields)
            return  # unrecoverable — ack, nothing to mirror
        book_id = UUID(str(book_raw))
        # Re-read the CURRENT lifecycle (order-/replay-safe). A transport/5xx RAISES BookClientError →
        # the base retries and (after max_retries) dead-letters — never silently mislabel a book live.
        lifecycle = await self._book_client.get_book_lifecycle(book_id)
        await self._apply(book_id, lifecycle)

    async def _apply(self, book_id: UUID, lifecycle: str) -> None:
        """Idempotent: `IS DISTINCT FROM` skips a no-op write, and the value is the re-read truth, so a
        replay in any order converges. Both anchor tables move together in one tx."""
        async with self._pool.acquire() as c:
            async with c.transaction():
                sn = await c.execute(
                    "UPDATE structure_node SET book_lifecycle = $2 "
                    "WHERE book_id = $1 AND book_lifecycle IS DISTINCT FROM $2",
                    book_id, lifecycle,
                )
                cw = await c.execute(
                    "UPDATE composition_work SET book_lifecycle = $2 "
                    "WHERE book_id = $1 AND book_lifecycle IS DISTINCT FROM $2",
                    book_id, lifecycle,
                )
        logger.info("book_lifecycle mirror: book %s → %s (structure_node=%s composition_work=%s)",
                    book_id, lifecycle, sn, cw)


def _parse_payload(fields: dict) -> dict:
    try:
        return json.loads(fields.get("payload") or "{}")
    except (TypeError, ValueError):
        return {}
