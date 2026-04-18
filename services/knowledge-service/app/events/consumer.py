"""K14.1 + K14.2 + K14.8 — Redis Streams consumer.

Main event consumer loop for knowledge-service. Reads from Redis
Streams via XREADGROUP, dispatches to handlers, handles DLQ.

Streams consumed:
  - loreweave:events:chapter  (chapter.saved, chapter.deleted)
  - loreweave:events:chat     (chat.turn_completed)
  - loreweave:events:glossary (glossary.entity_updated, etc.)

Consumer group: "knowledge-extractor"
Consumer name: hostname-based for multi-instance disambiguation.

K14.2: on startup, if the consumer group doesn't exist, creates it
from "0" (beginning). If Redis has evicted old events (MAXLEN trim),
the consumer processes what's available — the event_log fallback
ensures no events are permanently lost.

K14.8: on handler exception, retries up to MAX_RETRIES. After
exhaustion, logs to dead_letter_events and acks (preventing infinite
retry loops).
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
from typing import Any

import asyncpg
import redis.asyncio as aioredis

from app.events.dispatcher import EventData, EventDispatcher

__all__ = ["EventConsumer"]

logger = logging.getLogger(__name__)

STREAMS = [
    "loreweave:events:chapter",
    "loreweave:events:chat",
    "loreweave:events:glossary",
]
GROUP_NAME = "knowledge-extractor"
MAX_RETRIES = 3
BLOCK_MS = 5000  # 5s blocking read


class EventConsumer:
    """Redis Streams consumer with XREADGROUP.

    Create one instance per knowledge-service process. Call `run()`
    as a background asyncio task from the lifespan hook.
    """

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        dispatcher: EventDispatcher,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._dispatcher = dispatcher
        self._consumer_name = consumer_name or f"ks-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True,
            )
        return self._redis

    async def _ensure_groups(self) -> None:
        """Create consumer groups if they don't exist.

        MKSTREAM creates the stream if it doesn't exist yet (no events
        published). Group starts from "0" (process all existing events).
        """
        r = await self._ensure_redis()
        for stream in STREAMS:
            try:
                await r.xgroup_create(
                    stream, GROUP_NAME, id="0", mkstream=True,
                )
                logger.info("Created consumer group %s on %s", GROUP_NAME, stream)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    pass  # group already exists
                else:
                    raise

    async def run(self) -> None:
        """Main consumer loop. Blocks until stopped."""
        await self._ensure_groups()
        self._running = True
        r = await self._ensure_redis()

        logger.info(
            "K14.1: event consumer started (group=%s, consumer=%s, streams=%s)",
            GROUP_NAME, self._consumer_name, STREAMS,
        )

        # First: process any pending (unacked) messages from previous runs
        await self._process_pending(r)

        # Then: read new messages
        while self._running:
            try:
                streams_dict = {s: ">" for s in STREAMS}
                results = await r.xreadgroup(
                    GROUP_NAME,
                    self._consumer_name,
                    streams_dict,
                    count=10,
                    block=BLOCK_MS,
                )
                if not results:
                    continue

                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)

            except asyncio.CancelledError:
                logger.info("Consumer loop cancelled, shutting down")
                break
            except aioredis.ConnectionError:
                logger.warning("Redis connection lost, reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                logger.exception("Consumer loop error, retrying in 2s")
                await asyncio.sleep(2)

        await self.close()

    async def _process_pending(self, r: aioredis.Redis) -> None:
        """K14.2: on startup, process any unacked messages from previous runs.

        XREADGROUP with id="0" returns pending messages. This handles
        the catch-up case where the consumer crashed mid-processing.
        """
        for stream in STREAMS:
            try:
                results = await r.xreadgroup(
                    GROUP_NAME,
                    self._consumer_name,
                    {stream: "0"},
                    count=100,
                )
                if not results:
                    continue
                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except Exception:
                logger.exception("Error processing pending messages for %s", stream)

    async def _handle_message(
        self, r: aioredis.Redis, stream: str, msg_id: str, fields: dict[str, str],
    ) -> None:
        """Process a single message: parse → dispatch → ack or DLQ."""
        event = self._parse_event(stream, msg_id, fields)
        if event is None:
            # Unparseable — ack and move on
            await r.xack(stream, GROUP_NAME, msg_id)
            return

        try:
            handled = await self._dispatcher.dispatch(
                event, pool=self._pool,
            )
            # Ack regardless of whether a handler was found
            await r.xack(stream, GROUP_NAME, msg_id)

            if handled:
                logger.debug(
                    "Event handled: type=%s stream=%s id=%s",
                    event.event_type, stream, msg_id,
                )
        except Exception as exc:
            # K14.8: DLQ handling
            await self._handle_failure(r, stream, msg_id, event, exc)

    async def _handle_failure(
        self, r: aioredis.Redis, stream: str, msg_id: str,
        event: EventData, exc: Exception,
    ) -> None:
        """K14.8: retry or send to DLQ.

        Tracks retry count in a Redis key per message. After MAX_RETRIES,
        inserts into dead_letter_events and acks.
        """
        retry_key = f"ks:retry:{stream}:{msg_id}"
        retry_count = int(await r.incr(retry_key))
        await r.expire(retry_key, 3600)  # TTL 1h

        if retry_count < MAX_RETRIES:
            logger.warning(
                "Event handler failed (attempt %d/%d): type=%s id=%s error=%s",
                retry_count, MAX_RETRIES, event.event_type, msg_id, exc,
            )
            # Don't ack — message stays pending for redelivery
            return

        # Exhausted retries — DLQ
        logger.error(
            "Event sent to DLQ after %d retries: type=%s id=%s error=%s",
            MAX_RETRIES, event.event_type, msg_id, exc,
        )

        try:
            await self._pool.execute(
                """
                INSERT INTO dead_letter_events
                  (stream, message_id, event_type, aggregate_id, payload, error, retry_count)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                stream, msg_id, event.event_type, event.aggregate_id,
                json.dumps(event.payload), str(exc)[:2000], retry_count,
            )
        except Exception:
            logger.exception("Failed to write to DLQ table")

        # Ack to stop redelivery
        await r.xack(stream, GROUP_NAME, msg_id)
        await r.delete(retry_key)

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

    async def stop(self) -> None:
        """Signal the consumer to stop after the current cycle."""
        self._running = False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
