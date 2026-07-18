"""learning-service — FastAPI app.

Phase B (Axis-1 correction capture): consumes the correction event spine
(glossary.entity_updated [user-only] + knowledge.*_corrected) off Redis Streams
and persists to the `corrections` log; exposes a read API at /v1/learning/*.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loreweave_obs import setup_logging

from app.config import settings
from app.db.eval_repo import ensure_score_configs
from app.db.migrate import run_migrations
from app.db.online_eval import ensure_default_online_eval_rule
from app.db.pool import close_pool, create_pool, get_pool
from app.clients.llm_client import build_judge_sdk
from app.events.consumer import EventConsumer
from app.events.correction_contract import CORRECTION_EVENT_TYPES
from app.events.eval_runner import EvalRunner
from app.events.dispatcher import EventDispatcher
from app.events.llm_judge_consumer import LLMJudgeConsumer
from app.events.handlers import (
    handle_chat_feedback,
    handle_config_adjusted,
    handle_generation_corrected,
    handle_glossary_entity_merged,
    handle_glossary_entity_updated,
    handle_knowledge_corrected,
    handle_name_confirmed,
    handle_run_completed,
    handle_translation_corrected,
    handle_translation_quality,
    handle_translation_reviewed,
    handle_wiki_corrected,
    handle_wiki_suggestion_reviewed,
)
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import corrections, eval as eval_routes, mining, wiki_judge

setup_logging("learning-service")  # P2·A2a — shared JSON logging + dual trace ids
logger = logging.getLogger(__name__)


def build_dispatcher() -> EventDispatcher:
    """Register correction event handlers. Extracted for unit-testability."""
    dispatcher = EventDispatcher()
    dispatcher.register("glossary.entity_updated", handle_glossary_entity_updated)
    dispatcher.register("glossary.entity_merged", handle_glossary_entity_merged)  # D-LEARN-ENTITY-MERGED
    dispatcher.register("knowledge.entity_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.relation_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.event_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.fact_corrected", handle_knowledge_corrected)  # S-05
    dispatcher.register("knowledge.extraction_run_completed", handle_run_completed)
    dispatcher.register("knowledge.config_adjusted", handle_config_adjusted)
    dispatcher.register("chat.message_feedback", handle_chat_feedback)  # Q3
    dispatcher.register("composition.generation_corrected", handle_generation_corrected)  # V1 slice 2
    dispatcher.register("translation.quality", handle_translation_quality)  # M7a
    dispatcher.register("translation.reviewed", handle_translation_reviewed)  # M7b
    dispatcher.register("translation.corrected", handle_translation_corrected)  # M7c-1
    dispatcher.register("glossary.name_confirmed", handle_name_confirmed)  # M7c-3
    dispatcher.register("wiki.corrected", handle_wiki_corrected)  # D-WIKI-M8
    dispatcher.register("wiki.suggestion_reviewed", handle_wiki_suggestion_reviewed)  # D-WIKI-M8
    # No-silent-drop (compile/CI half): fail-fast at startup if a DECLARED correction
    # type has no handler — catches CONSUMER-side drift (a register() deleted, or a
    # contract row added without a handler). A PRODUCER rename / producer-side new
    # correction type is not visible here (the contract is consumer-owned) — that is
    # surfaced at runtime by EventDispatcher.dispatch's correction-marker WARN.
    missing = CORRECTION_EVENT_TYPES - set(dispatcher.registered_types)
    if missing:
        raise RuntimeError(
            "build_dispatcher does not cover the correction-event contract: missing handlers "
            f"for {sorted(missing)} (app/events/correction_contract.py). A correction event with "
            "no handler is silently dropped — register it or remove it from the contract."
        )
    return dispatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.learning_db_url)
    await run_migrations(pool)
    await ensure_score_configs(pool)  # Q1 — seed the metric-of-record score_config rows
    dispatcher = build_dispatcher()
    consumer = EventConsumer(settings.redis_url, pool, dispatcher)
    consumer_task = asyncio.create_task(consumer.run())
    logger.info("learning-service started (consumer group=learning-collector)")

    # Q4 — online-eval sampler (second consumer group). Best-effort, droppable.
    eval_runner: EvalRunner | None = None
    eval_runner_task = None
    if settings.online_eval_enabled:
        await ensure_default_online_eval_rule(pool)
        eval_runner = EvalRunner(settings.redis_url, pool)
        eval_runner_task = asyncio.create_task(eval_runner.run())
        logger.info("online-eval sampler started (consumer group=eval-runner)")

    # M1 — decoupled online-judge terminal-event consumer (+ stuck-resume sweeper).
    # Runs unconditionally: a campaign-chosen translation judge can fire even when the
    # service-wide judge flags are off, so the resume path must always be live. Idle
    # when no judge rows exist (every terminal event finds no row → ack + ignore).
    judge_sdk = build_judge_sdk(
        base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    judge_consumer = LLMJudgeConsumer(settings.redis_url, pool, judge_sdk)
    judge_consumer_task = asyncio.create_task(judge_consumer.run())
    judge_sweeper_task = asyncio.create_task(
        judge_consumer.run_sweeper(
            interval_s=settings.llm_judge_resume_sweep_interval_s,
            timeout_s=settings.llm_judge_resume_sweep_timeout_s,
            batch=settings.llm_judge_resume_sweep_batch,
        )
    )
    logger.info("llm-judge resume consumer started (consumer group=learning-judge-resume)")
    try:
        yield
    finally:
        await consumer.stop()
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        if eval_runner is not None and eval_runner_task is not None:
            await eval_runner.stop()
            eval_runner_task.cancel()
            try:
                await eval_runner_task
            except asyncio.CancelledError:
                pass
        await judge_consumer.stop()
        for task in (judge_consumer_task, judge_sweeper_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await judge_sdk.aclose()
        await close_pool()


app = FastAPI(title="learning-service", lifespan=lifespan)

app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(corrections.router)
app.include_router(mining.router)
app.include_router(eval_routes.router)
app.include_router(wiki_judge.router)  # D-WIKI-M8-EVAL-PLUS — internal groundedness judge


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
