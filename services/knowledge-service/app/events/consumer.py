"""K14.1 + K14.2 + K14.8 — Redis Streams consumer.

Main event consumer loop for knowledge-service. Reads from Redis Streams via XREADGROUP,
dispatches to handlers, handles DLQ.

Streams consumed:
  - loreweave:events:chapter  (chapter.saved, chapter.deleted)
  - loreweave:events:chat     (chat.turn_completed)
  - loreweave:events:glossary (glossary.entity_updated, etc.)

Consumer group: "knowledge-extractor"

Unified Job Control Plane P1 — the Redis transport (multi-stream BUSYGROUP-safe groups at
id="0", socket_timeout=None blocking loop, redis-py-8 idle TimeoutError, startup PEL drain,
periodic XAUTOCLAIM reclaim, bounded retry → DLQ) now lives in the shared
``loreweave_jobs.BaseProjectionConsumer``; this module supplies only the parse + dispatch
fold (``handle``) and the service's durable dead-letter sink (``on_dlq`` →
``dead_letter_events``). The reclaim is the D-PLATFORM-CONSUMER-RECLAIM-KNOWLEDGE fix
(a handler failure leaves a message pending that XREADGROUP ">" never returns, so its retry
counter never advances toward the DLQ without a timed reclaim).
"""

from __future__ import annotations

import json
import logging

import asyncpg

from loreweave_jobs import BaseProjectionConsumer

from app.events.dispatcher import EventData, EventDispatcher

__all__ = ["EventConsumer"]

logger = logging.getLogger(__name__)

STREAMS = [
    "loreweave:events:chapter",
    "loreweave:events:chat",
    "loreweave:events:glossary",
    # KG-ML M2 — translation.published (dual-index a chapter's active translation).
    "loreweave:events:translation",
]
GROUP_NAME = "knowledge-extractor"
MAX_RETRIES = 3
BLOCK_MS = 5000  # 5s blocking read
RECLAIM_EVERY_N_LOOPS = 12   # ~ every 60s at BLOCK_MS=5s
RECLAIM_MIN_IDLE_MS = 30000  # only reclaim messages idle ≥30s


class EventConsumer(BaseProjectionConsumer):
    """Multi-stream knowledge collector on the shared projection scaffold. Create one per
    process; run() as a background asyncio task from the lifespan hook. Business fold =
    ``handle`` (parse → dispatch); dead-letter sink = ``on_dlq`` (dead_letter_events)."""

    streams = STREAMS
    group = GROUP_NAME
    max_retries = MAX_RETRIES
    block_ms = BLOCK_MS
    reclaim_every_n_loops = RECLAIM_EVERY_N_LOOPS
    reclaim_min_idle_ms = RECLAIM_MIN_IDLE_MS
    consumer_name_prefix = "ks"
    retry_prefix = "ks:retry"

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        dispatcher: EventDispatcher,
        *,
        consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._dispatcher = dispatcher

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        """Parse + dispatch. An unparseable event returns (ack, no retry); a handler
        exception propagates to the base retry → DLQ policy. Ack on success happens in the
        base regardless of whether a handler matched (parity with the prior behaviour)."""
        event = self._parse_event(stream, msg_id, fields)
        if event is None:
            return  # unparseable — ack and move on
        await self._dispatcher.dispatch(event, pool=self._pool)

    async def on_dlq(self, stream: str, msg_id: str, fields: dict, exc: Exception) -> None:
        """K14.8 — persist the dead letter after MAX_RETRIES. Re-parses the event for its
        type/aggregate/payload (the event is parseable here — an unparseable one would have
        acked in ``handle``, never reaching the DLQ)."""
        event = self._parse_event(stream, msg_id, fields)
        event_type = event.event_type if event else fields.get("event_type", "")
        aggregate_id = event.aggregate_id if event else fields.get("aggregate_id", "")
        payload = event.payload if event else {}
        await self._pool.execute(
            """
            INSERT INTO dead_letter_events
              (stream, message_id, event_type, aggregate_id, payload, error, retry_count)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            ON CONFLICT DO NOTHING
            """,
            stream, msg_id, event_type, aggregate_id,
            json.dumps(payload), str(exc)[:2000], self.max_retries,
        )

    def _parse_event(self, stream: str, msg_id: str, fields: dict[str, str]) -> EventData | None:
        """Parse Redis Stream fields into EventData."""
        event_type = fields.get("event_type")
        if not event_type:
            logger.warning("Event missing event_type: stream=%s id=%s", stream, msg_id)
            return None

        payload = {}
        raw_payload = fields.get("payload", "{}")
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            logger.warning("Invalid JSON payload: stream=%s id=%s", stream, msg_id)

        return EventData(
            stream=stream,
            message_id=msg_id,
            event_type=event_type,
            aggregate_id=fields.get("aggregate_id", ""),
            payload=payload,
            source=fields.get("source", ""),
            raw=fields,
        )
