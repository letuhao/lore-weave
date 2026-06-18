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

import json
import logging

import asyncpg

from loreweave_jobs import BaseProjectionConsumer

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


class EvalRunner(BaseProjectionConsumer):
    """Online-eval sampler on the shared projection scaffold. Single forward-looking
    stream (``start_id="$"`` — eval samples are droppable, no backlog replay); best-effort
    ``ack_on_error`` (a sampled-out / errored event must not linger in the PEL, no retry);
    so no DLQ and no reclaim. One per process; run() as a background task."""

    streams = [STREAM]
    group = GROUP_NAME
    start_id = "$"
    ack_on_error = True
    reclaim_every_n_loops = 0
    count = 20
    block_ms = BLOCK_MS
    consumer_name_prefix = "eval-runner"

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        *,
        consumer_name: str | None = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._judge_sdk = None  # lazily built raw SDK for the decoupled judge (Q4b / M1)
        self._knowledge_client = None  # lazily built (Q4b-feed)

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        # Only run-completed events sample; everything else is a no-op (acked). A handler
        # error is acked by the ack_on_error policy (eval samples are droppable).
        if fields.get("event_type") == _RUN_COMPLETED:
            await self._maybe_eval(fields)

    async def close(self) -> None:
        await super().close()  # closes the Redis client
        if self._judge_sdk is not None:
            await self._judge_sdk.aclose()
            self._judge_sdk = None

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

    async def _ensure_judge_sdk(self):
        if self._judge_sdk is None:
            from app.clients.llm_client import build_judge_sdk
            from app.config import settings
            self._judge_sdk = build_judge_sdk(
                base_url=settings.provider_registry_internal_url,
                internal_token=settings.internal_service_token,
            )
        return self._judge_sdk

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
        """START the decoupled online LLM judge when (a) a judge panel is configured
        on the rule, (b) online judging is enabled + a judge model is set, and (c) the
        run's extracted items + source text are resolvable — inline on the event
        (test/demo) or fetched from knowledge-service for an opted-in run
        (Q4b-feed). Non-opted / unfetchable → structural-only.

        M1: submits the FIRST precision batch + persists a durable ``llm_judges``
        row, then returns — the llm-job terminal-event consumer drives the remaining
        batches + finalizes (was an inline ``submit_and_wait`` that pinned this
        consumer coroutine for the whole multi-batch judge)."""
        from app.config import settings
        from app.judges.decoupled_judge import start_extraction_judge

        if not (settings.online_judge_enabled and rule.get("judge_panel_id")):
            return
        if not settings.online_judge_model_ref:
            return
        # D-EVAL-JUDGE-PER-USER: bill the BYOK judge to the extraction's OWNER
        # (run["user_id"]) rather than the operator env id, so a multi-tenant
        # batch attributes judge cost correctly. Env id is the fallback only.
        judge_user_id = str(run["user_id"]) if run.get("user_id") else settings.online_judge_user_id
        if not judge_user_id:
            return  # no owner and no env fallback → cannot resolve a BYOK model
        items, source_text = await self._resolve_items_source(run, payload)
        if not isinstance(items, dict) or not source_text:
            return  # structural-only

        sdk = await self._ensure_judge_sdk()
        started = await start_extraction_judge(
            self._pool,
            sdk,
            run_id=str(run["run_id"]),
            owner_user_id=run["user_id"],
            billing_user_id=judge_user_id,
            project_id=run["project_id"],
            book_id=run["book_id"],
            config_hash=run["config_hash"],
            judge_model=settings.online_judge_model_ref,
            judge_model_source=settings.online_judge_model_source,
            source_text=source_text,
            items_by_category=items,
        )
        if started:
            logger.info("online judge: run=%s started (decoupled)", run["run_id"])
