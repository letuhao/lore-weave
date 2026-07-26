"""jobs-service — the Unified Job Control Plane projection + read API (P2).

Lifespan wires the projection consumer as a background task. It is best-effort
relative to the HTTP API: a Redis failure must not stop the service serving the
`/v1/jobs` read API off the already-projected rows.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loreweave_obs import setup_logging

from .config import settings
from .database import close_pool, create_pool
from .mcp.server import build_mcp_app, mcp_server
from .migrate import run_migrations
from .projection.consumer import JobProjectionConsumer
from .reconcile import ReconcileSweeper
from .sse import make_notifier

setup_logging("jobs-service", level=settings.log_level)  # P2·A2a — shared JSON logging
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

    # MCP fan-out S-JOBS — run the /mcp StreamableHTTP session manager. The /mcp
    # sub-app is mounted at module level, but a mounted Starlette sub-app's
    # lifespan is NOT auto-run under FastAPI, so we enter its session manager here.
    # stateless_http=True → no per-session state survives between calls; scope
    # arrives in headers. Failure to start affects ONLY the /mcp path — the
    # bespoke /v1/jobs read API stays up regardless (dual-run).
    mcp_exit_stack: AsyncExitStack | None = None
    try:
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.enter_async_context(mcp_server.session_manager.run())
        logger.info("S-JOBS: MCP session manager started; /mcp facade live")
    except Exception:  # noqa: BLE001 — /mcp is best-effort relative to the REST API
        logger.warning(
            "S-JOBS: MCP session manager failed to start (non-fatal) — "
            "/mcp facade unavailable, /v1/jobs still serves",
            exc_info=True,
        )
        if mcp_exit_stack is not None:
            await mcp_exit_stack.aclose()
            mcp_exit_stack = None

    logger.info("jobs-service started on port %d", settings.port)

    try:
        yield
    finally:
        # Stop the MCP session manager first so in-flight tool calls are cancelled
        # before the pool they touch is closed.
        if mcp_exit_stack is not None:
            with suppress(Exception):
                await mcp_exit_stack.aclose()
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

# MCP fan-out S-JOBS — mount the /mcp facade. stateless_http=True + path="/" so
# this yields the endpoint at exactly "/mcp"; the session manager is run in the
# lifespan above (a mounted sub-app's lifespan is not auto-run under FastAPI).
app.mount("/mcp", build_mcp_app())


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
