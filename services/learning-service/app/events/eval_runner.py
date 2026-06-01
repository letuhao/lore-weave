"""eval-runner — online structural eval consumer (track phase Q4).

A SECOND Redis consumer group on ``loreweave:events:knowledge`` (distinct from
``learning-collector``), so it samples ``extraction_run_completed`` events WITHOUT
perturbing the corrections/telemetry delivery — Redis fan-out delivers a copy to
each group.

BEST-EFFORT by design: an online eval sample is droppable (unlike a correction,
which is durable history), so there is NO DLQ/retry. Every message is XACKed —
sampled-out events immediately, so they never linger in the PEL (no XAUTOCLAIM
churn). The group is created at ``$`` (new messages only); online eval is
forward-looking, not a backlog re-eval.

The structural path needs no LLM, so it processes inline. The LLM-judge path
(Q4b) — host-orchestrated via provider-registry, with a sorted-set paced queue
as the cost governor — plugs in here when ``save_raw_extraction`` projects exist.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform

import asyncpg
import redis.asyncio as aioredis

from app.db.online_eval import (
    extract_run_fields,
    get_active_rule,
    persist_online_eval,
    should_sample,
    structural_completeness,
)

logger = logging.getLogger(__name__)

STREAM = "loreweave:events:knowledge"
GROUP_NAME = "eval-runner"
BLOCK_MS = 5000
_RUN_COMPLETED = "knowledge.extraction_run_completed"


class EvalRunner:
    """Online-eval sampler. One per process; run() as a background task."""

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._consumer_name = consumer_name or f"eval-runner-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            await r.xgroup_create(STREAM, GROUP_NAME, id="$", mkstream=True)
            logger.info("Created consumer group %s on %s", GROUP_NAME, STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        await self._ensure_group()
        self._running = True
        r = await self._ensure_redis()
        logger.info(
            "eval-runner started (group=%s consumer=%s)", GROUP_NAME, self._consumer_name
        )
        while self._running:
            try:
                results = await r.xreadgroup(
                    GROUP_NAME, self._consumer_name, {STREAM: ">"}, count=20, block=BLOCK_MS
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        await self._handle(r, msg_id, fields)
            except asyncio.CancelledError:
                logger.info("eval-runner cancelled, shutting down")
                break
            except aioredis.ConnectionError:
                logger.warning("eval-runner redis lost; reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                logger.exception("eval-runner loop error; retry in 2s")
                await asyncio.sleep(2)
        await self.close()

    async def _handle(self, r: aioredis.Redis, msg_id: str, fields: dict[str, str]) -> None:
        # Best-effort: ALWAYS ack (sampled-out / errored events must not linger
        # in the PEL — eval samples are droppable, no retry).
        try:
            if fields.get("event_type") == _RUN_COMPLETED:
                await self._maybe_eval(fields)
        except Exception:
            logger.exception("eval-runner handle error id=%s", msg_id)
        finally:
            await r.xack(STREAM, GROUP_NAME, msg_id)

    async def _maybe_eval(self, fields: dict[str, str]) -> None:
        rule = await get_active_rule(self._pool)
        if not rule:
            return  # no active rule -> sample nothing
        try:
            payload = json.loads(fields.get("payload", "{}") or "{}")
        except json.JSONDecodeError:
            return
        run = extract_run_fields(payload)
        if run is None:
            return
        if not should_sample(run["run_id"], float(rule["sampling_rate"])):
            return
        completeness = structural_completeness(run["metrics"])
        await persist_online_eval(
            self._pool,
            run_id=run["run_id"],
            user_id=run["user_id"],
            project_id=run["project_id"],
            book_id=run["book_id"],
            config_hash=run["config_hash"],
            completeness=completeness,
            origin_event_id=fields.get("outbox_id") or None,
        )
        logger.debug(
            "online eval persisted run=%s completeness=%.2f", run["run_id"], completeness
        )

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
