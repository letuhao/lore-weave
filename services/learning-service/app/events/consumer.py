"""Redis Streams consumer for learning-service.

Cloned from knowledge-service/app/events/consumer.py. Consumes the correction
event spine and dispatches to handlers that persist to `corrections`.

Streams consumed:
  - loreweave:events:glossary   (glossary.entity_updated — filtered to actor=user)
  - loreweave:events:knowledge  (knowledge.*_corrected — added in BUILD sub-session B)

Consumer group: "learning-collector" — DISTINCT from knowledge-service's
"knowledge-extractor". Redis delivers a copy of every message to each group, so
adding this group does NOT perturb knowledge-service's glossary_sync delivery.

`_parse_event` reads the `outbox_id` field the relay now XADDs (§4.0) — the
end-to-end dedup key the corrections handler uses for `ON CONFLICT`.

DLQ: on handler exception, retry up to MAX_RETRIES then write to
`dead_letter_events` and ack (no infinite retry loop).
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform

import asyncpg
import redis.asyncio as aioredis

from app.events.dispatcher import EventData, EventDispatcher

__all__ = ["EventConsumer", "STREAMS", "GROUP_NAME"]

logger = logging.getLogger(__name__)

STREAMS = [
    "loreweave:events:glossary",
    "loreweave:events:knowledge",
    "loreweave:events:chat",  # Q3 — chat.message_feedback (user thumbs/regenerate)
]
GROUP_NAME = "learning-collector"
MAX_RETRIES = 3
BLOCK_MS = 5000
# Periodic PEL reclaim. A handler failure leaves the message pending (not
# acked) for redelivery — but XREADGROUP ">" only returns NEW messages, so
# without an explicit reclaim a failed correction would sit in the PEL until
# the next restart (retry counter never advances → never DLQs). XAUTOCLAIM on a
# timer re-delivers stale-pending messages so the retry→DLQ path actually works
# in steady state (durability matters: corrections are append-only history).
RECLAIM_EVERY_N_LOOPS = 12          # ~ every 60s at BLOCK_MS=5s
RECLAIM_MIN_IDLE_MS = 30000         # only reclaim messages idle ≥30s


class EventConsumer:
    """Redis Streams consumer with XREADGROUP. One per process; run() as a
    background task from the lifespan hook."""

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
        self._consumer_name = consumer_name or f"learning-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def _ensure_groups(self) -> None:
        r = await self._ensure_redis()
        for stream in STREAMS:
            try:
                await r.xgroup_create(stream, GROUP_NAME, id="0", mkstream=True)
                logger.info("Created consumer group %s on %s", GROUP_NAME, stream)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    pass
                else:
                    raise

    async def run(self) -> None:
        await self._ensure_groups()
        self._running = True
        r = await self._ensure_redis()
        logger.info(
            "event consumer started (group=%s, consumer=%s, streams=%s)",
            GROUP_NAME, self._consumer_name, STREAMS,
        )
        await self._process_pending(r)

        loop_count = 0
        while self._running:
            try:
                loop_count += 1
                if loop_count % RECLAIM_EVERY_N_LOOPS == 0:
                    await self._reclaim_stale_pending(r)

                streams_dict = {s: ">" for s in STREAMS}
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, streams_dict,
                    count=10, block=BLOCK_MS,
                )
                if not results:
                    continue
                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except asyncio.CancelledError:
                logger.info("Consumer loop cancelled, shutting down")
                break
            except aioredis.TimeoutError:
                # redis-py 8: a blocking XREADGROUP that returns no data within
                # `block` raises TimeoutError (5.x returned empty). That is normal
                # idle, not an error — re-block without a scary traceback/backoff.
                continue
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
        for stream in STREAMS:
            try:
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, {stream: "0"}, count=100,
                )
                if not results:
                    continue
                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except Exception:
                logger.exception("Error processing pending messages for %s", stream)

    async def _reclaim_stale_pending(self, r: aioredis.Redis) -> None:
        """Re-deliver messages stuck in the PEL (a prior handler failure left
        them pending). XREADGROUP ">" never returns these, so without this a
        failed correction would only retry on restart. XAUTOCLAIM hands stale
        messages to this consumer; reprocessing advances the retry counter so
        the retry→DLQ path works in steady state (F-A1)."""
        for stream in STREAMS:
            try:
                start = "0-0"
                while True:
                    next_start, claimed, _deleted = await r.xautoclaim(
                        stream, GROUP_NAME, self._consumer_name,
                        min_idle_time=RECLAIM_MIN_IDLE_MS, start_id=start, count=50,
                    )
                    for msg_id, fields in claimed:
                        # A tombstoned (XDEL'd) message reclaims with empty
                        # fields — ack it to drain the PEL rather than loop.
                        if not fields:
                            await r.xack(stream, GROUP_NAME, msg_id)
                            continue
                        await self._handle_message(r, stream, msg_id, fields)
                    if not next_start or next_start == "0-0":
                        break
                    start = next_start
            except aioredis.ResponseError:
                # NOGROUP / stream not yet created — nothing to reclaim.
                pass
            except Exception:
                logger.exception("Error reclaiming pending messages for %s", stream)

    async def _handle_message(
        self, r: aioredis.Redis, stream: str, msg_id: str, fields: dict[str, str],
    ) -> None:
        event = self._parse_event(stream, msg_id, fields)
        if event is None:
            await r.xack(stream, GROUP_NAME, msg_id)
            return
        try:
            handled = await self._dispatcher.dispatch(event, pool=self._pool)
            await r.xack(stream, GROUP_NAME, msg_id)
            if handled:
                logger.debug(
                    "Event handled: type=%s stream=%s id=%s",
                    event.event_type, stream, msg_id,
                )
        except Exception as exc:
            await self._handle_failure(r, stream, msg_id, event, exc)

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

    async def _handle_failure(
        self, r: aioredis.Redis, stream: str, msg_id: str,
        event: EventData, exc: Exception,
    ) -> None:
        retry_key = f"learning:retry:{stream}:{msg_id}"
        retry_count = int(await r.incr(retry_key))
        await r.expire(retry_key, 3600)

        if retry_count < MAX_RETRIES:
            logger.warning(
                "Event handler failed (attempt %d/%d): type=%s id=%s error=%s",
                retry_count, MAX_RETRIES, event.event_type, msg_id, exc,
            )
            return  # leave pending for redelivery

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

        await r.xack(stream, GROUP_NAME, msg_id)
        await r.delete(retry_key)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
