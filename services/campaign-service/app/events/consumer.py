"""Projection consumer — builds the campaign_chapters projection from the
existing event spine (gap G7).

Consumes per-chapter completion events and advances the matching projection rows
across every active campaign on that (book, user):

  | stream                        | event_type                  | stage advanced |
  |-------------------------------|-----------------------------|----------------|
  | loreweave:events:knowledge    | knowledge.chapter_extracted | knowledge      |
  | loreweave:events:chapter      | chapter.translated          | translation    |
  | loreweave:events:translation  | translation.quality         | eval           |

Consumer group `campaign-collector` — DISTINCT from learning-service's
`learning-collector` and knowledge-service's `knowledge-extractor`. Redis
delivers a copy of every message to each group, so adding this consumer does not
perturb the existing ones.

`handle_event` is convergent + idempotent (sets a status to 'done'), so
at-least-once delivery is safe; no DLQ is needed in S1 (a dropped completion
event self-heals — the driver re-dispatches a still-`dispatched` row only after
the S3 stuck-timeout reconcile; until then the chapter shows in-flight).
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

from .. import repositories as repo

logger = logging.getLogger(__name__)

__all__ = ["EVENT_STAGE", "STREAMS", "GROUP_NAME", "handle_event", "ProjectionConsumer"]

# event_type → projection stage to advance.
EVENT_STAGE = {
    "knowledge.chapter_extracted": "knowledge",
    "chapter.translated": "translation",
    # S2: translation idempotency emits this when a chapter is already current
    # (skipped, no re-spend). Same done-signal for the projection so a resumed
    # campaign converges; statistics-service ignores it (stats-neutral).
    "chapter.translation_skipped": "translation",
    "translation.quality": "eval",
}

STREAMS = [
    "loreweave:events:knowledge",
    "loreweave:events:chapter",
    "loreweave:events:translation",
]
GROUP_NAME = "campaign-collector"
BLOCK_MS = 5000


async def handle_event(pool: asyncpg.Pool, event_type: str, payload: dict) -> bool:
    """Advance the projection for one inbound event. Returns True if it mapped to
    a stage and was applied, False if ignored (unknown type / missing ids)."""
    stage = EVENT_STAGE.get(event_type)
    if stage is None:
        return False
    try:
        user_id = payload["user_id"]
        book_id = payload["book_id"]
        chapter_id = payload["chapter_id"]
    except (KeyError, TypeError):
        logger.warning("event %s missing user_id/book_id/chapter_id", event_type)
        return False
    if not user_id or not book_id or not chapter_id:
        return False
    # Language guard for the language-specific stages: translation/eval events
    # carry `target_language`; knowledge.chapter_extracted has no such key, so
    # `.get` yields None = no filter (knowledge is language-agnostic).
    target_language = payload.get("target_language")
    try:
        await repo.mark_stage_done_by_chapter(
            pool,
            owner_user_id=UUID(str(user_id)),
            book_id=UUID(str(book_id)),
            chapter_id=UUID(str(chapter_id)),
            stage=stage,
            target_language=target_language,
        )
    except (ValueError, TypeError):
        logger.warning("event %s has malformed UUID(s)", event_type)
        return False
    return True


class ProjectionConsumer:
    """Redis Streams consumer; run() as a lifespan background task."""

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._consumer_name = consumer_name or f"campaign-{platform.node()}"
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
                logger.info("created consumer group %s on %s", GROUP_NAME, stream)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def run(self) -> None:
        await self._ensure_groups()
        self._running = True
        r = await self._ensure_redis()
        logger.info(
            "projection consumer started (group=%s, consumer=%s)",
            GROUP_NAME, self._consumer_name,
        )
        while self._running:
            try:
                streams_dict = {s: ">" for s in STREAMS}
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, streams_dict,
                    count=20, block=BLOCK_MS,
                )
                if not results:
                    continue
                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue
            except aioredis.ConnectionError:
                logger.warning("redis connection lost, reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                logger.exception("projection consumer loop error, retrying in 2s")
                await asyncio.sleep(2)
        await self.close()

    async def _handle_message(
        self, r: aioredis.Redis, stream: str, msg_id: str, fields: dict[str, str],
    ) -> None:
        event_type = fields.get("event_type", "")
        raw_payload = fields.get("payload", "{}")
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            payload = {}
            logger.warning("invalid JSON payload: stream=%s id=%s", stream, msg_id)
        try:
            await handle_event(self._pool, event_type, payload)
            # Idempotent + convergent → always ack (a failed advance self-heals
            # via the S3 stuck-timeout reconcile; no poison-message loop in S1).
            await r.xack(stream, GROUP_NAME, msg_id)
        except Exception:
            logger.exception(
                "projection handler error: stream=%s id=%s type=%s", stream, msg_id, event_type
            )
            await r.xack(stream, GROUP_NAME, msg_id)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
