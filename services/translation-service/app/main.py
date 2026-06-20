import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import create_pool, close_pool
from .llm_client import close_llm_client, get_llm_client
from .migrate import run_migrations
from .broker import connect_broker, close_broker
from .events.glossary_consumer import GlossaryStaleConsumer
from .events.llm_terminal_consumer import LLMTerminalConsumer
from .broker import publish_event
from .grant_client import init_grant_client, close_grant_client

log = logging.getLogger(__name__)
from .routers import settings as settings_router
from .routers import jobs as jobs_router
from .routers import versions as versions_router
from .routers import coverage as coverage_router
from .routers import translate as translate_router
from .routers import extraction as extraction_router
from .routers import glossary_translate as glossary_translate_router
from .routers import internal_dispatch as internal_dispatch_router
from .routers import actions as actions_router
# MCP fan-out S-TRANSL — the /mcp provider facade (mounted below; its session
# manager is run inside the lifespan, like S-JOBS).
from .mcp.server import build_mcp_app, mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)

    # Startup recovery: mark stale pending jobs as failed (workers are separate now)
    await pool.execute("""
        UPDATE translation_jobs
        SET status = 'failed', error_message = 'server_restart', finished_at = now()
        WHERE status = 'pending'
          AND created_at < now() - interval '10 minutes'
    """)

    await connect_broker()

    # Phase 4c-α: loreweave_llm SDK wrapper. Touched here so SDK
    # construction errors (bad base_url, missing internal_token)
    # surface at startup. 4c-β/γ migrate the actual translation
    # workers to use this client.
    get_llm_client()

    # E0-4a: the grant client (book-service /access authority). Constructed at
    # startup so its httpx client shares the app lifecycle.
    init_grant_client()
    # D-GRANT-INSTANT-REVOKE — tail book-service grant revokes (Redis) → drop the
    # cached grant on the spot (vs the 45s TTL). Best-effort; no redis → TTL only.
    if settings.redis_url:
        init_grant_client().start_revoke_consumer(settings.redis_url)

    # M5c: consume glossary change events → flag stale translations. Best-effort
    # background task; a Redis hiccup must never take down the API.
    consumer = GlossaryStaleConsumer(settings.redis_url, pool)
    consumer_task = asyncio.create_task(consumer.run())

    # LLM re-arch Phase 2b-T2: resume decoupled TEXT translations off the durable
    # terminal-event stream. Started only when the decouple flag is on (inert
    # otherwise — no decoupled chapters exist so every event would just ack+ignore).
    llm_consumer = None
    llm_consumer_task = None
    llm_sweeper_task = None
    if settings.translation_decouple_enabled:
        llm_consumer = LLMTerminalConsumer(
            settings.redis_url, pool, get_llm_client(), publish_event,
        )
        llm_consumer_task = asyncio.create_task(llm_consumer.run())
        # Wave 2a — the stuck-resume sweeper (runtime backstop for a stranded
        # resume_state: consumer poison, lost terminal event, or a submit→persist gap).
        if settings.translation_resume_sweep_interval_s > 0:
            llm_sweeper_task = asyncio.create_task(llm_consumer.run_sweeper(
                interval_s=settings.translation_resume_sweep_interval_s,
                timeout_s=settings.translation_resume_sweep_timeout_s,
                batch=settings.translation_resume_sweep_batch,
            ))

    # MCP fan-out S-TRANSL — run the /mcp StreamableHTTP session manager. The /mcp
    # sub-app is mounted at module level, but a mounted Starlette sub-app's lifespan
    # is NOT auto-run under FastAPI, so we enter its session manager here. Best-effort:
    # failure affects ONLY /mcp; the bespoke /v1/translation REST API stays up.
    mcp_exit_stack: AsyncExitStack | None = None
    try:
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.enter_async_context(mcp_server.session_manager.run())
        log.info("S-TRANSL: MCP session manager started; /mcp facade live")
    except Exception:  # noqa: BLE001 — /mcp is best-effort relative to the REST API
        log.warning(
            "S-TRANSL: MCP session manager failed to start (non-fatal) — "
            "/mcp facade unavailable, /v1/translation still serves",
            exc_info=True,
        )
        if mcp_exit_stack is not None:
            await mcp_exit_stack.aclose()
            mcp_exit_stack = None

    yield

    if mcp_exit_stack is not None:
        with suppress(Exception):
            await mcp_exit_stack.aclose()
    await consumer.stop()
    consumer_task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await consumer_task
    await consumer.close()
    if llm_sweeper_task is not None:
        llm_sweeper_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await llm_sweeper_task
    if llm_consumer is not None:
        await llm_consumer.stop()
        llm_consumer_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await llm_consumer_task
        await llm_consumer.close()
    await close_llm_client()
    await close_grant_client()
    await close_broker()
    await close_pool()


app = FastAPI(title="translation-service", lifespan=lifespan)

app.include_router(settings_router.router)
app.include_router(jobs_router.router)
app.include_router(versions_router.router)
app.include_router(coverage_router.router)
app.include_router(translate_router.router)
app.include_router(extraction_router.router)
app.include_router(glossary_translate_router.router)
app.include_router(internal_dispatch_router.router)
app.include_router(actions_router.router)

# MCP fan-out S-TRANSL — mount the /mcp facade. stateless_http=True + path="/" so
# this yields the endpoint at exactly "/mcp"; the session manager is run in the
# lifespan above (a mounted sub-app's lifespan is not auto-run under FastAPI).
app.mount("/mcp", build_mcp_app())


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


# ── Internal endpoints (no auth — service-to-service only) ─────────────────

from uuid import UUID
from typing import List
from fastapi import Depends
from pydantic import BaseModel
from .database import get_pool
import asyncpg


class LanguageInfo(BaseModel):
    language: str
    chapter_count: int


class BookLanguagesResponse(BaseModel):
    book_id: str
    languages: List[LanguageInfo]


@app.get("/internal/books/{book_id}/languages", response_model=BookLanguagesResponse)
async def get_book_languages(book_id: UUID, db: asyncpg.Pool = Depends(get_pool)):
    """Return list of target languages that have at least one completed translation."""
    rows = await db.fetch(
        """
        SELECT target_language, COUNT(DISTINCT chapter_id) AS chapter_count
        FROM chapter_translations
        WHERE book_id = $1 AND status = 'completed'
        GROUP BY target_language
        ORDER BY target_language
        """,
        book_id,
    )
    return BookLanguagesResponse(
        book_id=str(book_id),
        languages=[
            LanguageInfo(language=r["target_language"], chapter_count=r["chapter_count"])
            for r in rows
        ],
    )
