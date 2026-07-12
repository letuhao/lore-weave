"""SC11 amendment Phase 2 — composition's FIRST domain-event consumer.

Composition has never listened to another service's domain events. It consumed its own job stream
and a grant-revoke cache-bust fan-out, and that was all. This is the seam that makes the
written-verdict mirror live: book-service says "this chapter's spec back-links may have changed",
composition re-reads that chapter and reconciles.

THE EVENT CARRIES NO DATA, AND THAT IS THE DESIGN. `{book_id, chapter_id}` and nothing else. The
relay is at-least-once and un-ordered, so a payload-carrying event would let a stale redelivery
overwrite newer state. A re-read cannot: whatever book-service says NOW is what the mirror becomes.
Every handler here is therefore idempotent and order-insensitive — replay it a hundred times, in any
order, and the mirror lands in the same place.

⚠ THE FAILURE THIS FILE IS BUILT TO AVOID. knowledge-service's own wiring comment names it: an
UNREGISTERED event_type is dropped at DEBUG and ACKED — *"the event is acked into the void. A perfect
silent success."* If `chapter.scenes_linked` were emitted and never registered here, every publish
would look healthy from both ends while the mirror silently went stale, and the Plan Hub would render
a written book as unwritten with nobody ever seeing an error. `REQUIRED_EVENTS` + its test exist so
that cannot happen: a handler that is depended upon but not registered is a RED TEST, not a quiet
afternoon.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID

import asyncpg
from loreweave_jobs import BaseProjectionConsumer

from app.db.repositories.written_verdict import WrittenVerdictRepo
from app.engine.scene_decompile import BookSceneFetchError
from app.mcp.service_bearer import mint_service_bearer
from app.services.written_verdict_service import reconcile_one_chapter

logger = logging.getLogger(__name__)

CHAPTER_STREAM = "loreweave:events:chapter"
GROUP_NAME = "composition-mirror"

# The written-verdict mirror is only correct if ALL of these are handled.
#   * scenes_linked — the link changed (a re-parse, an import, the IX-12 write-back).
#   * trashed/deleted — the PROSE VANISHED without `source_scene_id` ever being touched (spec §5.2b).
#     Miss these and the mirror keeps claiming prose the author has deleted.
REQUIRED_EVENTS = frozenset({
    "chapter.scenes_linked",
    "chapter.trashed",
    "chapter.deleted",
})


@dataclass
class EventData:
    stream: str
    message_id: str
    event_type: str
    aggregate_id: str
    payload: dict[str, Any]


Handler = Callable[..., Awaitable[None]]


class CompositionEventConsumer(BaseProjectionConsumer):
    """Reconciles the written-verdict mirror from book-service's chapter events."""

    streams = [CHAPTER_STREAM]
    group = GROUP_NAME
    max_retries = 3
    block_ms = 5000
    reclaim_every_n_loops = 12
    reclaim_min_idle_ms = 30000
    consumer_name_prefix = "cs"
    retry_prefix = "cs:retry"

    def __init__(
        self, redis_url: str, pool: asyncpg.Pool, *,
        book_base_url: str, jwt_secret: str, consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._book_base_url = book_base_url
        self._jwt_secret = jwt_secret
        self._handlers: dict[str, Handler] = {
            "chapter.scenes_linked": self._on_scenes_linked,
            "chapter.trashed": self._on_prose_gone,
            "chapter.deleted": self._on_prose_gone,
        }
        missing = REQUIRED_EVENTS - set(self._handlers)
        if missing:  # fail LOUDLY at construction, never silently at runtime
            raise RuntimeError(f"written-verdict mirror has no handler for {sorted(missing)}")

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        event = _parse(stream, msg_id, fields)
        if event is None:
            return  # unparseable — ack, nothing we can do with it
        handler = self._handlers.get(event.event_type)
        if handler is None:
            # This stream carries chapter.created/saved/published/… too. Ignoring THOSE is correct;
            # ignoring one we depend on is the silent-success bug, and REQUIRED_EVENTS is what stops
            # it from ever getting here.
            return
        await handler(event)

    # ── handlers ────────────────────────────────────────────────────────────────────────────

    async def _book_and_chapter(self, event: EventData) -> tuple[UUID, UUID] | None:
        book = event.payload.get("book_id")
        chapter = event.payload.get("chapter_id") or event.aggregate_id
        if not book or not chapter:
            logger.warning("scenes_linked: event without book_id/chapter_id: %s", event.payload)
            return None
        return UUID(str(book)), UUID(str(chapter))

    async def _on_scenes_linked(self, event: EventData) -> None:
        ids = await self._book_and_chapter(event)
        if ids is None:
            return
        book_id, chapter_id = ids

        owner = await self._owner_of(book_id)
        if owner is None:
            # No Work ⇒ no spec nodes ⇒ nothing to mirror. A Work-less book is a legitimate no-op,
            # not an error (SC11: "a Work-less book still browses").
            return

        try:
            res = await reconcile_one_chapter(
                self._pool, book_id, chapter_id,
                book_base_url=self._book_base_url,
                bearer=mint_service_bearer(owner, self._jwt_secret),
            )
        except BookSceneFetchError:
            # UNKNOWN, not empty. RAISE so the base retries and (after max_retries) dead-letters —
            # never swallow it into a reconcile-to-empty, which would blank a written chapter on a
            # transient blip. The sweeper is the backstop; silence is not.
            logger.warning("scenes_linked: book %s chapter %s unreadable — will retry",
                           book_id, chapter_id)
            raise

        logger.info("written-verdict: chapter %s reconciled (linked=%d cleared=%d)",
                    chapter_id, res["linked"], res["cleared"])

    async def _on_prose_gone(self, event: EventData) -> None:
        """spec §5.2b — the chapter's prose is GONE. Its scenes went with it, so every node they
        backed is unwritten. `source_scene_id` was never touched, so no scenes_linked fires: without
        this handler the mirror would keep claiming prose the author deleted."""
        ids = await self._book_and_chapter(event)
        if ids is None:
            return
        book_id, chapter_id = ids
        cleared = await WrittenVerdictRepo(self._pool).clear_chapter(book_id, chapter_id)
        if cleared:
            logger.info("written-verdict: chapter %s prose gone — %d node(s) cleared",
                        chapter_id, cleared)

    async def _owner_of(self, book_id: UUID) -> UUID | None:
        async with self._pool.acquire() as c:
            return await c.fetchval(
                "SELECT created_by FROM composition_work WHERE book_id = $1 "
                "ORDER BY created_at LIMIT 1",
                book_id,
            )


def _parse(stream: str, msg_id: str, fields: dict[str, str]) -> EventData | None:
    event_type = fields.get("event_type")
    if not event_type:
        return None
    try:
        payload = json.loads(fields.get("payload") or "{}")
    except (TypeError, ValueError):
        payload = {}
    return EventData(
        stream=stream, message_id=msg_id, event_type=event_type,
        aggregate_id=fields.get("aggregate_id", ""), payload=payload,
    )
