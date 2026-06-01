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
        self._judge_client = None  # lazily built (Q4b)
        self._knowledge_client = None  # lazily built (Q4b-feed)

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
            except aioredis.TimeoutError:
                # redis-py 8: a blocking XREADGROUP with no data within `block`
                # raises TimeoutError (5.x returned empty). Normal idle — re-block.
                continue
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
        # Q4b — LLM-as-judge, only for opted-in runs that carry items + source.
        await self._maybe_judge(rule, run, payload)

    async def _ensure_judge_client(self):
        if self._judge_client is None:
            from app.clients.llm_client import build_judge_client
            from app.config import settings
            self._judge_client = build_judge_client(
                base_url=settings.provider_registry_internal_url,
                internal_token=settings.internal_service_token,
            )
        return self._judge_client

    async def _ensure_knowledge_client(self):
        if self._knowledge_client is None:
            from app.clients.knowledge_client import build_knowledge_client
            from app.config import settings
            self._knowledge_client = build_knowledge_client(
                base_url=settings.knowledge_internal_url,
                internal_token=settings.internal_service_token,
            )
        return self._knowledge_client

    async def _resolve_items_source(
        self, run: dict, payload: dict,
    ) -> tuple[dict | None, str | None]:
        """Get the extracted items + source for judging.

        `save_raw_extraction` is the UNCONDITIONAL consent gate (/review-impl
        LOW#2): no novel content is judged for a non-opted run, whether the
        items arrive inline or via fetch. For an opted-in run, two sources, in
        order:
          1. INLINE on the event (test/demo override) — `payload.items` +
             `payload.source_text`. Production events never carry these
             (redact-by-default keeps novel content off the broker).
          2. Q4b-feed FETCH — pull the run-sample from knowledge-service by
             run_id. None on 404 / error → structural-only.
        """
        if not payload.get("save_raw_extraction"):
            return None, None  # consent gate: no judging without raw-retention opt-in
        items = payload.get("items")
        source_text = payload.get("source_text")
        if isinstance(items, dict) and source_text:
            return items, source_text  # inline override (test/demo)
        client = await self._ensure_knowledge_client()
        sample = await client.fetch_run_sample(run["run_id"])
        if not sample:
            return None, None
        s_items = sample.get("items")
        s_source = sample.get("source_text")
        if not isinstance(s_items, dict) or not s_source:
            return None, None
        return s_items, s_source

    async def _maybe_judge(self, rule: dict, run: dict, payload: dict) -> None:
        """Run the online LLM judge when (a) a judge panel is configured on the
        rule, (b) online judging is enabled + a judge model is set, and (c) the
        run's extracted items + source text are resolvable — inline on the event
        (test/demo) or fetched from knowledge-service for an opted-in run
        (Q4b-feed). Non-opted / unfetchable → structural-only."""
        from app.config import settings
        from app.db.online_judge import persist_online_judge, run_online_judge

        if not (settings.online_judge_enabled and rule.get("judge_panel_id")):
            return
        if not (settings.online_judge_model_ref and settings.online_judge_user_id):
            return
        items, source_text = await self._resolve_items_source(run, payload)
        if not isinstance(items, dict) or not source_text:
            return  # structural-only

        client = await self._ensure_judge_client()
        result = await run_online_judge(
            client,
            source_text=source_text,
            items_by_category=items,
            judge_model=settings.online_judge_model_ref,
            model_source=settings.online_judge_model_source,
            user_id=settings.online_judge_user_id,
        )
        await persist_online_judge(
            self._pool,
            run_id=run["run_id"],
            user_id=run["user_id"],
            judge_model=settings.online_judge_model_ref,
            judge_result=result,
            project_id=run["project_id"],
            book_id=run["book_id"],
            config_hash=run["config_hash"],
        )
        logger.info(
            "online judge: run=%s precision=%s", run["run_id"], result.get("overall_precision")
        )

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
        if self._judge_client is not None:
            await self._judge_client.aclose()
