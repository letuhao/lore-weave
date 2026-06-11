"""LLM re-arch Phase 2b-T2 — llm-job terminal-event consumer (Redis Streams).

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event stream
the provider-registry relay XADDs on every job's terminal transition) and resumes
the decoupled TEXT translate state machine for the chapter whose in-flight job just
finished. So a worker coroutine is NOT pinned for a whole chapter — it submits the
first chunk + releases, and this consumer drives every subsequent chunk / compaction
/ finalize off the terminal events.

Only fires for chapters in the decoupled path (``chapter_translations.provider_job_id``
set). Any other terminal event (a non-translation job, or a chapter already
finalized) finds no matching row → acked + ignored.

**At-least-once safe.** The relay is at-least-once; this consumer dedups two ways:
- A superseded chunk's duplicate event finds no row (resume advanced
  ``provider_job_id`` to the next chunk's job) → ignored.
- The FINAL event's duplicate is absorbed by ``_finalize_chapter``'s
  ``status <> 'completed'`` idempotency guard.

Mirrors ``GlossaryStaleConsumer`` for the correctness-critical Redis bits (blocking
XREADGROUP needs ``socket_timeout=None``; BUSYGROUP-safe group; drain pending on
startup; ack on success; bounded retry then ack). Best-effort: never crashes the
service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import platform
from uuid import UUID

import redis.asyncio as aioredis

from ..llm_client import LLMClient, set_campaign_id
from ..workers import decoupled_block_translate, decoupled_translate

log = logging.getLogger(__name__)

STREAM = "loreweave:events:llm_job_terminal"
GROUP_NAME = "translation-llm-resume"
MAX_RETRIES = 3
BLOCK_MS = 5000


async def _load_for_job(pool, provider_job_id: str) -> tuple[UUID, dict] | None:
    """(chapter_translation_id, resume_state) for the chapter whose in-flight job is
    ``provider_job_id`` — or None if no decoupled chapter is awaiting it (a
    non-translation job, or one already finalized/superseded)."""
    try:
        job_uuid = UUID(provider_job_id)
    except (ValueError, TypeError):
        return None
    row = await pool.fetchrow(
        "SELECT id, resume_state FROM chapter_translations WHERE provider_job_id = $1",
        job_uuid,
    )
    if not row or row["resume_state"] is None:
        return None
    rs = row["resume_state"]
    rs = rs if isinstance(rs, dict) else json.loads(rs)
    return row["id"], rs


class LLMTerminalConsumer:
    """Redis-Streams consumer; run() as a background task from the lifespan hook.
    `publish_event` is the broker emitter the finalize hook uses for chapter_done /
    job-completion events (the same function the worker uses)."""

    def __init__(
        self, redis_url: str, pool, llm_client: LLMClient, publish_event,
        *, consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._llm_client = llm_client
        self._publish_event = publish_event
        self._consumer_name = consumer_name or f"transl-resume-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None,
            )
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            # id="$" — start from NEW events. A decoupled job in flight at first
            # deploy doesn't exist (the flag was off), so nothing is missed; after
            # creation the group persists + tracks delivery (pending redelivers a
            # crash-window event).
            await r.xgroup_create(STREAM, GROUP_NAME, id="$", mkstream=True)
            log.info("created consumer group %s on %s", GROUP_NAME, STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        self._running = True
        log.info("LLM terminal-resume consumer starting (consumer=%s)", self._consumer_name)

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
                log.warning("llm-terminal consumer: Redis not ready, retry in 5s", exc_info=True)
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
                log.exception("llm-terminal consumer loop error; retrying in 2s")
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
            log.exception("error draining pending llm-terminal events")

    async def _handle(self, r: aioredis.Redis, msg_id: str, fields: dict) -> None:
        job_id = fields.get("job_id")
        owner_user_id = fields.get("owner_user_id") or None
        if not job_id:
            await r.xack(STREAM, GROUP_NAME, msg_id)
            return
        try:
            loaded = await _load_for_job(self._pool, job_id)
            if loaded is None:
                # Not a decoupled translation job (or already finalized/superseded).
                await r.xack(STREAM, GROUP_NAME, msg_id)
                return
            ct_id, rs = loaded
            msg = rs["msg"]
            # Resume may submit the next chunk/compaction — bind the owning campaign
            # so those provider jobs keep their attribution (the same contextvar the
            # worker set on the first submit). Cleared in finally.
            set_campaign_id(msg.get("campaign_id"))
            job = await self._llm_client.sdk.get_job(
                job_id, user_id=owner_user_id or msg.get("user_id"),
            )
            # Dispatch by the engine that owns this chapter's resume_state.
            if rs.get("mode") == "block":
                await decoupled_block_translate.resume(
                    pool=self._pool, llm_client=self._llm_client, job=job,
                    chapter_translation_id=ct_id,
                    finalize_cb=self._make_block_finalize_cb(msg, ct_id, rs),
                )
            else:
                await decoupled_translate.resume(
                    pool=self._pool, llm_client=self._llm_client, job=job,
                    chapter_translation_id=ct_id,
                    finalize_cb=self._make_finalize_cb(msg, ct_id, rs),
                )
            await r.xack(STREAM, GROUP_NAME, msg_id)
        except Exception as exc:
            retry_key = f"transl:llmresume:retry:{msg_id}"
            count = int(await r.incr(retry_key))
            await r.expire(retry_key, 3600)
            if count >= MAX_RETRIES:
                log.error("llm-terminal event %s (job=%s) failed %d× — acking to stop "
                          "redelivery: %s", msg_id, job_id, count, exc)
                await r.xack(STREAM, GROUP_NAME, msg_id)
                await r.delete(retry_key)
            else:
                log.warning("llm-terminal event %s (job=%s) failed (%d/%d): %s",
                            msg_id, job_id, count, MAX_RETRIES, exc)
                # leave unacked → redelivered
        finally:
            set_campaign_id(None)

    def _make_finalize_cb(self, msg: dict, ct_id: UUID, rs: dict):
        """Build the finalize hook the decoupled engine calls when all chunks are
        done. Reconstructs the full finalize context from the persisted ``msg`` +
        ``resume_state`` (the consumer only saw a job_id). TEXT path ⇒ body is text,
        json=None, format='text', memo_text=body."""
        from ..workers.chapter_worker import _finalize_chapter

        async def _cb(body: str, in_tok: int, out_tok: int) -> None:
            await _finalize_chapter(
                pool=self._pool, publish_event=self._publish_event, msg=msg,
                job_id=UUID(str(msg["job_id"])), chapter_id=UUID(str(msg["chapter_id"])),
                user_id=msg["user_id"], chapter_translation_id=ct_id,
                pipeline_version=msg.get("pipeline_version", "v2"),
                chapter_index=msg.get("chapter_index", 0),
                target_language=msg.get("target_language", ""),
                source_lang=rs.get("source_lang", "unknown"),
                chapter_text=rs.get("chapter_text", ""),
                translated_body_text=body, translated_body_json=None,
                translated_body_format="text", memo_text=body,
                input_tokens=in_tok, output_tokens=out_tok,
            )

        return _cb

    def _make_block_finalize_cb(self, msg: dict, ct_id: UUID, rs: dict):
        """Block-path finalize hook (2b-T3a). The engine rebuilt the Tiptap body →
        `body_json` (format='json'), with `memo_text` = translated-only text."""
        from ..workers.chapter_worker import _finalize_chapter

        async def _cb(body_json: str, in_tok: int, out_tok: int, memo_text: str) -> None:
            await _finalize_chapter(
                pool=self._pool, publish_event=self._publish_event, msg=msg,
                job_id=UUID(str(msg["job_id"])), chapter_id=UUID(str(msg["chapter_id"])),
                user_id=msg["user_id"], chapter_translation_id=ct_id,
                pipeline_version=msg.get("pipeline_version", "v2"),
                chapter_index=msg.get("chapter_index", 0),
                target_language=msg.get("target_language", ""),
                source_lang=rs.get("source_lang", "unknown"),
                chapter_text=rs.get("chapter_text", ""),
                translated_body_text=None, translated_body_json=body_json,
                translated_body_format="json", memo_text=memo_text,
                input_tokens=in_tok, output_tokens=out_tok,
            )

        return _cb

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
