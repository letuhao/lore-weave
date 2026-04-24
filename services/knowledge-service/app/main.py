import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients.book_client import close_book_client, get_book_client
from app.clients.embedding_client import close_embedding_client, get_embedding_client
from app.clients.glossary_client import close_glossary_client, init_glossary_client
from app.clients.provider_client import close_provider_client, get_provider_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.neo4j import close_neo4j_driver, get_neo4j_driver, init_neo4j_driver
from app.db.neo4j_schema import run_neo4j_schema
from app.db.pool import close_pools, create_pools, get_knowledge_pool
from app.logging_config import setup_logging, trace_id_var
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import (
    context,
    health,
    internal_benchmark,
    internal_extraction,
    internal_summarize,
    metrics,
    ping,
)
from app.routers.public import costs as public_costs
from app.routers.public import drawers as public_drawers
from app.routers.public import entities as public_entities
from app.routers.public import extraction as public_extraction
from app.routers.public import logs as public_logs
from app.routers.public import projects as public_projects
from app.routers.public import summaries as public_summaries
from app.routers.public.summaries import close_cooldown_client
from app.routers.public import timeline as public_timeline
from app.routers.public import user_data as public_user_data

logger = logging.getLogger(__name__)


async def _close_all_startup_resources() -> None:
    """D-K11.3-01 (session 46) — partial-startup cleanup.

    If any pre-yield step raises, this runs every close_* that is
    safe to call regardless of whether the corresponding init
    actually completed. close_* functions are idempotent / no-op
    when the resource is None or already closed.

    Teardown order mirrors the post-yield block (reverse dependency).
    """
    for close_fn_name, close_fn in (
        ("cooldown_client", close_cooldown_client),
        ("provider_client", close_provider_client),
        ("embedding_client", close_embedding_client),
        ("book_client", close_book_client),
        ("glossary_client", close_glossary_client),
        ("neo4j_driver", close_neo4j_driver),
        ("pools", close_pools),
    ):
        try:
            await close_fn()
        except Exception:
            logger.warning(
                "startup cleanup: failed to close %s (non-fatal)",
                close_fn_name, exc_info=True,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    # D-K11.3-01: wrap startup so a failure mid-init closes what DID
    # initialize. Without this the post-yield cleanup only runs when
    # the yield is reached, leaking pools/drivers/clients on any
    # startup exception.
    try:
        # Fail-fast: if either pool cannot be created, raise and stop startup.
        await create_pools(settings.knowledge_db_url, settings.glossary_db_url)
        await run_migrations(get_knowledge_pool())
        # Long-lived httpx client for glossary-service calls (K4b).
        init_glossary_client()
        # K16.2 — long-lived httpx client for book-service chapter counts.
        get_book_client()
        # K12.2 — long-lived httpx client for embedding calls.
        get_embedding_client()
        # K17.2 — long-lived httpx client for provider-registry BYOK LLM
        # calls. Singleton is lazy-constructed by the first get_provider_client
        # call, but we touch it here so a misconfigured base URL surfaces at
        # startup rather than at first extraction job.
        get_provider_client()
        # K11.2 — Neo4j driver. No-op in Track 1 mode (NEO4J_URI empty);
        # fail-fast on unreachable Neo4j when configured.
        await init_neo4j_driver()
        # K11.3 — apply the Cypher schema (constraints + indexes +
        # vector indexes) on every startup. Idempotent. Only runs when
        # the K11.2 driver init actually configured a connection;
        # Track 1 mode skips this entirely.
        if settings.neo4j_uri:
            await run_neo4j_schema(get_neo4j_driver())
    except Exception:
        logger.exception(
            "lifespan startup failed before yield — running partial cleanup"
        )
        await _close_all_startup_resources()
        raise
    # K14.1 — start event consumer as background task.
    # Imports inline to avoid circular imports (consumer needs pool).
    consumer_task = None
    try:
        from app.events.consumer import EventConsumer
        from app.events.dispatcher import EventDispatcher
        from app.events.handlers import (
            handle_chat_turn,
            handle_chapter_saved,
            handle_chapter_deleted,
        )

        dispatcher = EventDispatcher()
        dispatcher.register("chat.turn_completed", handle_chat_turn)
        dispatcher.register("chapter.saved", handle_chapter_saved)
        dispatcher.register("chapter.deleted", handle_chapter_deleted)

        consumer = EventConsumer(
            redis_url=settings.redis_url,
            pool=get_knowledge_pool(),
            dispatcher=dispatcher,
        )
        consumer_task = asyncio.create_task(consumer.run())
        logger.info("K14.1: event consumer started as background task")
    except Exception:
        logger.warning("K14.1: event consumer failed to start (non-fatal)", exc_info=True)

    # K13.1 — start nightly anchor_score refresh loop as background task.
    # Skipped in Track 1 / no-Neo4j mode since recompute_anchor_score has
    # nothing to do without a graph.
    refresh_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.jobs.anchor_refresh_loop import run_anchor_refresh_loop

            def _anchor_session_factory():
                return neo4j_session()

            refresh_task = asyncio.create_task(
                run_anchor_refresh_loop(
                    get_knowledge_pool(),
                    _anchor_session_factory,
                )
            )
            logger.info("K13.1: anchor-refresh loop started as background task")
        except Exception:
            logger.warning(
                "K13.1: anchor-refresh loop failed to start (non-fatal)",
                exc_info=True,
            )

    # K20.3 — scheduled project summary regeneration. Skipped in
    # Track 1 / no-Neo4j mode since the regen helper reads raw
    # :Passage nodes from the graph — with no graph there's nothing
    # to regenerate from.
    #
    # Construction pattern matches K13.1's anchor_refresh_loop wire
    # just above: pool + session factory passed positionally,
    # downstream collaborators constructed inline here rather than
    # via the async `get_*_repo()` factories in deps.py. Those
    # factories exist for FastAPI `Depends()` integration; calling
    # them here would create a throwaway coroutine for a pure
    # pass-through. Consistency with the neighbor scheduler wins
    # over consistency with router DI.
    summary_regen_task = None
    global_regen_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.db.repositories.summaries import SummariesRepo
            from app.jobs.summary_regen_scheduler import (
                run_global_regen_loop,
                run_project_regen_loop,
            )

            def _summary_session_factory():
                return neo4j_session()

            # K20.3 α — project-scope (L1) regen, daily cadence.
            summary_regen_task = asyncio.create_task(
                run_project_regen_loop(
                    get_knowledge_pool(),
                    _summary_session_factory,
                    get_provider_client(),
                    SummariesRepo(get_knowledge_pool()),
                )
            )
            logger.info(
                "K20.3: project summary regen loop started as background task"
            )

            # K20.3 β — global-scope (L0) regen, weekly cadence with
            # 15-min offset so it doesn't start simultaneously with
            # the project loop on first boot.
            global_regen_task = asyncio.create_task(
                run_global_regen_loop(
                    get_knowledge_pool(),
                    _summary_session_factory,
                    get_provider_client(),
                    SummariesRepo(get_knowledge_pool()),
                )
            )
            logger.info(
                "K20.3: global summary regen loop started as background task"
            )
        except Exception:
            logger.warning(
                "K20.3: summary regen loops failed to start (non-fatal)",
                exc_info=True,
            )

    # C14a — reconcile-evidence-count + quarantine-cleanup schedulers.
    # Both wrap existing per-user/global Neo4j functions (K11.9 + K15.10)
    # in periodic sweeps. Gated on neo4j_uri same as summary regen
    # loops (both need working Cypher sessions). Advisory-lock keys
    # 20_310_004 (reconcile) + 20_310_005 (quarantine) distinct from
    # 001-003 so all schedulers can run concurrently without blocking.
    reconcile_sweep_task = None
    quarantine_sweep_task = None
    if settings.neo4j_uri:
        try:
            from app.db.neo4j import neo4j_session
            from app.jobs.reconcile_evidence_count_scheduler import (
                run_reconcile_loop,
            )
            from app.jobs.quarantine_cleanup_scheduler import (
                run_quarantine_loop,
            )

            def _scheduler_session_factory():
                return neo4j_session()

            reconcile_sweep_task = asyncio.create_task(
                run_reconcile_loop(
                    get_knowledge_pool(),
                    _scheduler_session_factory,
                )
            )
            logger.info(
                "C14a: reconcile-evidence-count loop started as background task"
            )

            quarantine_sweep_task = asyncio.create_task(
                run_quarantine_loop(
                    get_knowledge_pool(),
                    _scheduler_session_factory,
                )
            )
            logger.info(
                "C14a: quarantine-cleanup loop started as background task"
            )
        except Exception:
            logger.warning(
                "C14a: reconcile/quarantine loops failed to start (non-fatal)",
                exc_info=True,
            )

    # C3 (D-K19b.8-01) — job_logs retention cron. Not gated on
    # neo4j_uri because retention only needs the knowledge-service
    # Postgres pool. 20-min startup offset from the K20.3 loops'
    # 10/15-min windows so the three schedulers don't converge at boot.
    job_logs_retention_task = None
    try:
        from app.jobs.job_logs_retention import run_job_logs_retention_loop

        job_logs_retention_task = asyncio.create_task(
            run_job_logs_retention_loop(get_knowledge_pool())
        )
        logger.info(
            "C3: job_logs retention loop started as background task"
        )
    except Exception:
        logger.warning(
            "C3: job_logs retention loop failed to start (non-fatal)",
            exc_info=True,
        )

    # D-T2-04 — cross-process cache invalidator via Redis pub/sub.
    # Only installed when redis_url is configured; Track 1 single-
    # worker deploys stay local-only.
    cache_invalidator = None
    if settings.redis_url:
        try:
            from app.context import cache as cache_module
            from app.context.cache_invalidation import CacheInvalidator

            cache_invalidator = CacheInvalidator(settings.redis_url)
            await cache_invalidator.start()
            cache_module.set_invalidator(cache_invalidator)
            logger.info(
                "D-T2-04: cache invalidator registered (cross-process pub/sub active)"
            )
        except Exception:
            logger.warning(
                "D-T2-04: cache invalidator failed to start (non-fatal) — "
                "falling back to local-only invalidation",
                exc_info=True,
            )

    logger.info("knowledge-service started on port %d", settings.port)
    try:
        yield
    finally:
        # Stop cache invalidator first so in-flight publishes drain
        # before we close the Redis client.
        if cache_invalidator is not None:
            try:
                from app.context import cache as cache_module
                cache_module.set_invalidator(None)
                await cache_invalidator.stop()
            except Exception:
                logger.warning(
                    "Error stopping cache invalidator", exc_info=True,
                )

        # Stop anchor-refresh loop next (quick cancel).
        if refresh_task is not None:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning("Error stopping anchor-refresh loop", exc_info=True)

        # K20.3: stop summary regen loops (project first, then global).
        if summary_regen_task is not None:
            summary_regen_task.cancel()
            try:
                await summary_regen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "K20.3: error stopping project regen loop",
                    exc_info=True,
                )
        if global_regen_task is not None:
            global_regen_task.cancel()
            try:
                await global_regen_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "K20.3: error stopping global regen loop",
                    exc_info=True,
                )

        # C3: stop job_logs retention loop.
        if job_logs_retention_task is not None:
            job_logs_retention_task.cancel()
            try:
                await job_logs_retention_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C3: error stopping job_logs retention loop",
                    exc_info=True,
                )

        # C14a: stop reconcile + quarantine sweepers.
        if reconcile_sweep_task is not None:
            reconcile_sweep_task.cancel()
            try:
                await reconcile_sweep_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C14a: error stopping reconcile sweep loop",
                    exc_info=True,
                )
        if quarantine_sweep_task is not None:
            quarantine_sweep_task.cancel()
            try:
                await quarantine_sweep_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "C14a: error stopping quarantine sweep loop",
                    exc_info=True,
                )

        # Stop event consumer next.
        if consumer_task is not None:
            try:
                await consumer.stop()
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.warning("Error stopping event consumer", exc_info=True)

        # Phase 3 review issue 8: close in reverse dependency order.
        # C2: close the cooldown Redis client ahead of other resources
        # since it's self-contained (no inbound dependencies).
        await close_cooldown_client()
        await close_provider_client()
        await close_embedding_client()
        await close_book_client()
        await close_glossary_client()
        await close_neo4j_driver()
        await close_pools()
        logger.info("knowledge-service stopped")


app = FastAPI(title="knowledge-service", lifespan=lifespan)

app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def _trace_id_500_handler(request: Request, exc: Exception) -> JSONResponse:
    """K7e: include the trace id in the 500 body so a caller staring
    at an error in the UI can grep it straight to this service's
    logs. Starlette's default handler returns plain text; overriding
    it is the standard FastAPI pattern.

    HTTPException (4xx + explicit 5xx from handlers) is NOT caught
    here — FastAPI's built-in HTTPException handler runs first and
    keeps its own envelope.
    """
    logger.exception("unhandled exception (500): %s", exc)
    tid = trace_id_var.get()
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "trace_id": tid},
        headers={"X-Trace-Id": tid or ""},
    )


app.include_router(health.router)
app.include_router(ping.public_router)
app.include_router(ping.internal_router)
app.include_router(context.router)
app.include_router(internal_benchmark.router)
app.include_router(internal_extraction.router)
app.include_router(internal_summarize.router)
app.include_router(metrics.router)
app.include_router(public_costs.router)
app.include_router(public_drawers.router)
app.include_router(public_entities.router)
app.include_router(public_entities.entities_router)
app.include_router(public_extraction.router)
app.include_router(public_extraction.jobs_router)
app.include_router(public_logs.router)
app.include_router(public_projects.router)
app.include_router(public_summaries.router)
app.include_router(public_timeline.timeline_router)
app.include_router(public_user_data.router)
