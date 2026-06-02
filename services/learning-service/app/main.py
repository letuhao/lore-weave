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

from app.config import settings
from app.db.eval_repo import ensure_score_configs
from app.db.migrate import run_migrations
from app.db.online_eval import ensure_default_online_eval_rule
from app.db.pool import close_pool, create_pool, get_pool
from app.events.consumer import EventConsumer
from app.events.eval_runner import EvalRunner
from app.events.dispatcher import EventDispatcher
from app.events.handlers import (
    handle_chat_feedback,
    handle_config_adjusted,
    handle_glossary_entity_updated,
    handle_knowledge_corrected,
    handle_run_completed,
)
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import corrections, eval as eval_routes, mining

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dispatcher() -> EventDispatcher:
    """Register correction event handlers. Extracted for unit-testability."""
    dispatcher = EventDispatcher()
    dispatcher.register("glossary.entity_updated", handle_glossary_entity_updated)
    dispatcher.register("knowledge.entity_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.relation_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.event_corrected", handle_knowledge_corrected)
    dispatcher.register("knowledge.extraction_run_completed", handle_run_completed)
    dispatcher.register("knowledge.config_adjusted", handle_config_adjusted)
    dispatcher.register("chat.message_feedback", handle_chat_feedback)  # Q3
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


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
