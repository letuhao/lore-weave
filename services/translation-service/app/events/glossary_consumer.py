"""M5c — glossary-staleness consumer (Redis Streams).

Consumes ``loreweave:events:glossary`` and, on a ``glossary.entity_updated``
event, marks the book's translations stale (``is_glossary_stale=true``) so the
living book can flag translations that predate a glossary change.

Granularity is **coarse / book-level**: translation has no glossary-term→chunk
mapping, so any glossary change for book X flags all of X's chapter_translations.
The flag is a non-destructive hint — a fresh re-translation starts un-stale.

Mirrors the knowledge-service consumer's correctness-critical bits (a blocking
XREADGROUP needs ``socket_timeout=None``; BUSYGROUP-safe group create; process
pending on startup; ack on success; bounded retry then ack). No DLQ table here —
on retry exhaustion we log + ack (a missed coarse stale-flag is tolerable, and
glossary events recur). Best-effort: never crashes the service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import platform
from uuid import UUID

import redis.asyncio as aioredis

log = logging.getLogger(__name__)

STREAM = "loreweave:events:glossary"
GROUP_NAME = "translation-staleness"
GLOSSARY_CHANGE_EVENT = "glossary.entity_updated"
MAX_RETRIES = 3
BLOCK_MS = 5000


def parse_glossary_event(fields: dict) -> tuple[str, dict]:
    """(event_type, payload) from Redis Stream fields. Tolerant — bad JSON → {}."""
    event_type = fields.get("event_type", "")
    raw = fields.get("payload", "{}")
    try:
        payload = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return event_type, payload


async def handle_glossary_event(pool, event_type: str, payload: dict) -> bool:
    """Flag the book's translations stale on a glossary change. Returns True if a
    row update ran. Idempotent (only flips false→true); a missing/invalid book_id
    is a no-op (the event is still acked by the caller)."""
    if event_type != GLOSSARY_CHANGE_EVENT:
        return False
    book_id = payload.get("book_id")
    if not book_id:
        return False
    try:
        book_uuid = UUID(str(book_id))
    except (ValueError, TypeError):
        log.warning("glossary event with invalid book_id=%r — skipping", book_id)
        return False
    await pool.execute(
        "UPDATE chapter_translations SET is_glossary_stale = true "
        "WHERE book_id = $1 AND COALESCE(is_glossary_stale, false) = false",
        book_uuid,
    )
    log.info("M5c: flagged translations stale for book=%s (glossary changed)", book_uuid)
    return True


class GlossaryStaleConsumer:
    """Redis-Streams consumer; run() as a background task from the lifespan hook."""

    def __init__(self, redis_url: str, pool, *, consumer_name: str | None = None) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._consumer_name = consumer_name or f"transl-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            # socket_timeout=None is REQUIRED — a per-read timeout shorter than
            # BLOCK_MS would pre-empt the server-side BLOCK and wedge the loop
            # (knowledge-service consumer note).
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None,
            )
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            # id="$" — start from NEW events only. Staleness is forward-looking;
            # starting at "0" would replay the entire retained glossary backlog
            # (~200k events) on first deploy, mass-flagging every book that ever
            # changed. A missed event while down is a tolerable false-negative hint.
            await r.xgroup_create(STREAM, GROUP_NAME, id="$", mkstream=True)
            log.info("created consumer group %s on %s", GROUP_NAME, STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        self._running = True
        log.info("M5c glossary-staleness consumer starting (consumer=%s)", self._consumer_name)

        # Retry initial setup until Redis is reachable — a Redis blip at startup
        # must not permanently kill the consumer (it would otherwise raise out of
        # the bg task and never recover until a service restart).
        while self._running:
            try:
                await self._ensure_group()
                r = await self._ensure_redis()
                await self._drain(r, "0")  # unacked from a prior run
                break
            except asyncio.CancelledError:
                await self.close()
                return
            except Exception:
                log.warning("glossary consumer: Redis not ready, retry in 5s", exc_info=True)
                self._redis = None
                await asyncio.sleep(5)
        if not self._running:
            await self.close()
            return

        while self._running:
            try:
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, {STREAM: ">"},
                    count=10, block=BLOCK_MS,
                )
                for _stream, messages in results or []:
                    for msg_id, fields in messages:
                        await self._handle(r, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue  # idle long-poll
            except aioredis.ConnectionError:
                log.warning("redis connection lost; reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                log.exception("glossary consumer loop error; retrying in 2s")
                await asyncio.sleep(2)
        await self.close()

    async def _drain(self, r: aioredis.Redis, start_id: str) -> None:
        try:
            results = await r.xreadgroup(
                GROUP_NAME, self._consumer_name, {STREAM: start_id}, count=100,
            )
            for _stream, messages in results or []:
                for msg_id, fields in messages:
                    await self._handle(r, msg_id, fields)
        except Exception:
            log.exception("error draining pending glossary events")

    async def _handle(self, r: aioredis.Redis, msg_id: str, fields: dict) -> None:
        event_type, payload = parse_glossary_event(fields)
        try:
            await handle_glossary_event(self._pool, event_type, payload)
            await r.xack(STREAM, GROUP_NAME, msg_id)
        except Exception as exc:
            retry_key = f"transl:retry:{msg_id}"
            count = int(await r.incr(retry_key))
            await r.expire(retry_key, 3600)
            if count >= MAX_RETRIES:
                log.error("glossary event %s failed %d× — acking to stop redelivery: %s",
                          msg_id, count, exc)
                await r.xack(STREAM, GROUP_NAME, msg_id)
                await r.delete(retry_key)
            else:
                log.warning("glossary event %s failed (%d/%d): %s",
                            msg_id, count, MAX_RETRIES, exc)
                # leave unacked → redelivered

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
