"""Redis Streams consumer for learning-service.

Consumes the correction event spine and dispatches to handlers that persist to
`corrections`.

Streams consumed:
  - loreweave:events:glossary    (glossary.entity_updated — filtered to actor=user)
  - loreweave:events:knowledge   (knowledge.*_corrected)
  - loreweave:events:chat        (chat.message_feedback)
  - loreweave:events:composition (composition.generation_corrected)
  - loreweave:events:translation (translation.quality — V3 verifier rollup)

Consumer group: "learning-collector" — DISTINCT from knowledge-service's
"knowledge-extractor" (Redis delivers a copy of every message to each group).

`_parse_event` reads the `outbox_id` field the relay XADDs (§4.0) — the end-to-end dedup
key the corrections handler uses for `ON CONFLICT`.

Unified Job Control Plane P1 — the Redis transport (multi-stream BUSYGROUP groups at id=0,
socket_timeout=None blocking loop, redis-py-8 idle TimeoutError, startup PEL drain, periodic
XAUTOCLAIM reclaim, bounded retry → DLQ) now lives in the shared
`loreweave_jobs.BaseProjectionConsumer`; this module supplies only the parse + dispatch fold
(`handle`) and the durable dead-letter sink (`on_dlq` → `dead_letter_events`). Corrections
are append-only history, so the retry→DLQ policy (not ack-on-error) is used.
"""

from __future__ import annotations

import json
import logging

import asyncpg

from loreweave_jobs import BaseProjectionConsumer

from app.events.dispatcher import EventData, EventDispatcher

__all__ = ["EventConsumer", "STREAMS", "GROUP_NAME"]

logger = logging.getLogger(__name__)

STREAMS = [
    "loreweave:events:glossary",
    "loreweave:events:knowledge",
    "loreweave:events:chat",
    "loreweave:events:composition",
    "loreweave:events:translation",
]
GROUP_NAME = "learning-collector"
MAX_RETRIES = 3
BLOCK_MS = 5000
RECLAIM_EVERY_N_LOOPS = 12          # ~ every 60s at BLOCK_MS=5s
RECLAIM_MIN_IDLE_MS = 30000         # only reclaim messages idle ≥30s


class EventConsumer(BaseProjectionConsumer):
    """Multi-stream correction collector on the shared projection scaffold. One per
    process; run() as a background task from the lifespan hook. Business fold = `handle`
    (parse → dispatch); dead-letter sink = `on_dlq` (dead_letter_events)."""

    streams = STREAMS
    group = GROUP_NAME
    max_retries = MAX_RETRIES
    block_ms = BLOCK_MS
    reclaim_every_n_loops = RECLAIM_EVERY_N_LOOPS
    reclaim_min_idle_ms = RECLAIM_MIN_IDLE_MS
    consumer_name_prefix = "learning"
    retry_prefix = "learning:retry"

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
        event = self._parse_event(stream, msg_id, fields)
        if event is None:
            return  # unparseable — ack
        await self._dispatcher.dispatch(event, pool=self._pool)

    async def on_dlq(self, stream: str, msg_id: str, fields: dict, exc: Exception) -> None:
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

    def _parse_event(
        self, stream: str, msg_id: str, fields: dict[str, str],
    ) -> EventData | None:
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
            outbox_id=fields.get("outbox_id", ""),
        )
