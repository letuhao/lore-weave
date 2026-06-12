"""LLM re-arch Phase 3 M1 — llm-job terminal-event consumer for online judges.

Consumes ``loreweave:events:llm_job_terminal`` (the durable terminal-event stream
the provider-registry relay XADDs on every job's terminal transition) under its OWN
group ``learning-judge-resume`` (distinct from translation's ``translation-llm-resume``
— Redis fan-out delivers a copy to each group). For each terminal event it folds the
finished judge batch and dispatches the next / finalizes (see ``decoupled_judge``).

Any terminal event that isn't a running judge (a translation job, an extraction job,
or a judge already finalized/superseded) finds no matching ``llm_judges`` row → acked
+ ignored. Best-effort: never crashes the service; bounded retry then ack.

Mirrors translation's ``LLMTerminalConsumer`` for the correctness-critical Redis bits
(blocking XREADGROUP needs ``socket_timeout=None``; BUSYGROUP-safe group; drain pending
on startup; ack on success; bounded retry then ack) + the stuck-resume sweeper.
"""

from __future__ import annotations

import asyncio
import logging
import platform

import redis.asyncio as aioredis

from app.judges import decoupled_judge

log = logging.getLogger(__name__)

STREAM = "loreweave:events:llm_job_terminal"
GROUP_NAME = "learning-judge-resume"
MAX_RETRIES = 3
BLOCK_MS = 5000


class LLMJudgeConsumer:
    """Redis-Streams consumer; run() as a background task from the lifespan hook.

    `sdk` is the long-lived loreweave_llm Client used for get_job (the consumer's
    own auth identity per-call comes from the terminal event's owner_user_id) and the
    next-batch submits inside ``decoupled_judge.resume``."""

    def __init__(
        self, redis_url: str, pool, sdk, *, consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._sdk = sdk
        self._consumer_name = consumer_name or f"learn-judge-{platform.node()}"
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
            # id="$" — new events only. A judge in flight at first deploy doesn't
            # exist (the inline path had no row); after creation the group persists
            # + redelivers a crash-window event.
            await r.xgroup_create(STREAM, GROUP_NAME, id="$", mkstream=True)
            log.info("created consumer group %s on %s", GROUP_NAME, STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        self._running = True
        log.info("LLM-judge terminal-resume consumer starting (consumer=%s)", self._consumer_name)

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
                log.warning("llm-judge consumer: Redis not ready, retry in 5s", exc_info=True)
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
                log.exception("llm-judge consumer loop error; retrying in 2s")
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
            log.exception("error draining pending llm-judge events")

    async def _handle(self, r: aioredis.Redis, msg_id: str, fields: dict) -> None:
        job_id = fields.get("job_id")
        owner_user_id = fields.get("owner_user_id") or None
        if not job_id:
            await r.xack(STREAM, GROUP_NAME, msg_id)
            return
        try:
            loaded = await decoupled_judge.load_for_job(self._pool, job_id)
            if loaded is None:
                # Not a running judge (a translation/extraction job, or finalized).
                await r.xack(STREAM, GROUP_NAME, msg_id)
                return
            _row_id, billing_user_id = loaded
            job = await self._sdk.get_job(job_id, user_id=owner_user_id or billing_user_id)
            await decoupled_judge.resume(self._pool, self._sdk, job)
            await r.xack(STREAM, GROUP_NAME, msg_id)
        except Exception as exc:
            retry_key = f"learn:judgeresume:retry:{msg_id}"
            count = int(await r.incr(retry_key))
            await r.expire(retry_key, 3600)
            if count >= MAX_RETRIES:
                log.error("llm-judge event %s (job=%s) failed %d× — acking to stop "
                          "redelivery: %s", msg_id, job_id, count, exc)
                await r.xack(STREAM, GROUP_NAME, msg_id)
                await r.delete(retry_key)
            else:
                log.warning("llm-judge event %s (job=%s) failed (%d/%d): %s",
                            msg_id, job_id, count, MAX_RETRIES, exc)
                # leave unacked → redelivered

    async def run_sweeper(self, *, interval_s: int, timeout_s: int, batch: int) -> None:
        """Long-running periodic stuck-resume sweeper. interval_s <= 0 ⇒ disabled."""
        if interval_s <= 0:
            log.info("learning judge sweeper disabled (interval<=0)")
            return
        log.info("learning judge sweeper started (interval=%ds timeout=%ds batch=%d)",
                 interval_s, timeout_s, batch)
        while True:
            try:
                n = await decoupled_judge.sweep_once(
                    self._pool, self._sdk, timeout_s=timeout_s, batch=batch,
                )
                if n:
                    log.info("judge-sweep: re-drove %d stranded judge(s)", n)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick mustn't kill the loop
                log.exception("learning judge sweeper tick failed")
            await asyncio.sleep(interval_s)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
