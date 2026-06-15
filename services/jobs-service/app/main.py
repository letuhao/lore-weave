"""jobs-service — the Unified Job Control Plane projection + read API (P2).

Lifespan wires the projection consumer as a background task. It is best-effort
relative to the HTTP API: a Redis failure must not stop the service serving the
`/v1/jobs` read API off the already-projected rows.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import close_pool, create_pool
from .migrate import run_migrations
from .projection.consumer import JobProjectionConsumer
from .reconcile import ReconcileSweeper
from .sse import make_notifier

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)

    # Dedicated publisher connection for the SSE pub/sub fan-out (the consumer's
    # own connection is blocked in xreadgroup). Best-effort: a publish failure
    # never fails the projection (the consumer swallows notify errors).
    publisher = aioredis.from_url(settings.redis_url, decode_responses=True)
    consumer = JobProjectionConsumer(settings.redis_url, pool, notify=make_notifier(publisher))
    consumer_task = asyncio.create_task(consumer.run())

    # Reconcile sweep (H1 backstop) — best-effort, off by default. `run()` no-ops
    # immediately when reconcile_enabled is false, so the task is cheap to always create.
    sweeper = ReconcileSweeper(pool)
    sweeper_task = asyncio.create_task(sweeper.run())
    logger.info("jobs-service started on port %d", settings.port)

    try:
        yield
    finally:
        await consumer.stop()
        await sweeper.stop()
        consumer_task.cancel()
        sweeper_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await consumer_task
        with suppress(asyncio.CancelledError, Exception):
            await sweeper_task
        with suppress(Exception):
            await consumer.close()
        with suppress(Exception):
            await publisher.aclose()
        await close_pool()


app = FastAPI(title="jobs-service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import jobs as jobs_router  # noqa: E402

app.include_router(jobs_router.router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
