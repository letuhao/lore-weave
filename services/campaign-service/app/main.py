"""campaign-service — Auto-Draft Factory saga orchestrator (S1).

Lifespan wires the projection consumer + saga driver as background tasks. Both
are best-effort relative to the HTTP API: a Redis/driver failure must not stop
the service serving campaign CRUD.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import create_pool, close_pool
from .migrate import run_migrations
from .events.consumer import ProjectionConsumer
from .events.spend_consumer import SpendConsumer
from .saga.driver import SagaDriver, DispatchClients
from .clients.dispatch_clients import (
    TranslationDispatchClient,
    KnowledgeDispatchClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)

    # On restart, any campaign left mid-dispatch self-heals: the stateless driver
    # re-derives "what's next" from campaign_chapters (decision D). No pending-job
    # cleanup needed — the projection IS the state.

    consumer = ProjectionConsumer(settings.redis_url, pool)
    consumer_task = asyncio.create_task(consumer.run())

    # S4d — budget-cap spend consumer (loreweave:events:campaign_usage). Separate
    # group + flat-field parse + dedup; accumulates spent_usd and auto-pauses at cap.
    spend_consumer = SpendConsumer(settings.redis_url, pool)
    spend_task = asyncio.create_task(spend_consumer.run())

    clients = DispatchClients(
        translation=TranslationDispatchClient(
            settings.translation_service_internal_url,
            settings.internal_service_token,
            timeout_s=settings.dispatch_timeout_s,
        ),
        knowledge=KnowledgeDispatchClient(
            settings.knowledge_service_internal_url,
            settings.internal_service_token,
            timeout_s=settings.dispatch_timeout_s,
        ),
    )
    driver = SagaDriver(
        pool, clients,
        tick_seconds=settings.driver_tick_seconds,
        max_attempts=settings.max_stage_attempts,
        max_inflight=settings.driver_max_inflight_per_campaign,
    )
    driver_task = asyncio.create_task(driver.run())

    try:
        yield
    finally:
        await consumer.stop()
        await spend_consumer.stop()
        await driver.stop()
        consumer_task.cancel()
        spend_task.cancel()
        driver_task.cancel()
        for t in (consumer_task, spend_task, driver_task):
            with suppress(asyncio.CancelledError, Exception):
                await t
        with suppress(Exception):
            await consumer.close()
        with suppress(Exception):
            await spend_consumer.close()
        with suppress(Exception):
            await clients.translation.aclose()
        with suppress(Exception):
            await clients.knowledge.aclose()
        await close_pool()


app = FastAPI(title="campaign-service", lifespan=lifespan)

from .routers import campaigns as campaigns_router  # noqa: E402

app.include_router(campaigns_router.router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
