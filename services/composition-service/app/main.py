"""composition-service entrypoint (LOOM Composition V0 — M0 skeleton).

Lifespan: create_pool → run_migrations → yield → close_pool. M0 boots the
HTTP skeleton (health/ping/metrics) wired to loreweave_composition; schema,
repos, clients, packer, engine, and the real /v1/composition/* endpoints land
in M1–M6. Mirrors knowledge-service house style (ASGI trace middleware, JSON
logging, OTel-optional, terse 500 envelope).
"""

import asyncio
import contextlib
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.clients.book_client import close_book_client
from app.clients.embedding_client import close_embedding_client
from app.clients.glossary_client import close_glossary_client
from app.clients.kal_client import close_kal_client
from app.clients.knowledge_client import close_knowledge_client
from app.clients.llm_client import close_llm_client
from app.clients.web_search_client import close_web_search_client
from app.grant_client import close_grant_client, get_grant_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool, get_pool
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.worker.operations import SUPPORTED_OPERATIONS
from app.logging_config import setup_logging, trace_id_var
from app.mcp.server import build_mcp_app, mcp_server
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import (
    actions, approve, arc, authoring_runs, canon, conformance, engine, grounding, health,
    import_source, internal_eval, internal_job_control, internal_model_settings,
    internal_plan_state, internal_structure_state, metrics,
    motif, motif_sync, narrative_threads, outline, ping, plan, plan_bootstrap, plan_forge,
    plan_overlay, progress, prose, references, style_voice, works,
)

logger = logging.getLogger(__name__)


async def _reap_stale_jobs_loop() -> None:
    """Periodic backstop for D-COMP-CHAPTER-INFLIGHT-REAPER: every
    `job_reaper_sweep_secs`, mark jobs orphaned in `running`/`pending` past
    `chapter_inflight_stale_secs` as failed (a crash/kill leaves no producer to
    terminate them). The guard reaps per-chapter opportunistically; this catches
    never-re-requested chapters + per-scene orphans. A transient DB blip is logged
    and retried next interval — it never kills the loop."""
    interval = settings.job_reaper_sweep_secs
    window = settings.chapter_inflight_stale_secs
    repo = GenerationJobsRepo(get_pool())
    # D-M4-REAPER-WORKER-CONFLICT: when the worker is on it resumes its own jobs
    # via the updated_at-based stuck-job sweeper, so this created_at reaper must
    # NOT fail a worker op whose legitimate wall-clock exceeds the window. Exclude
    # the worker-op set; flag-off keeps the original "reap everything" behavior.
    exclude_ops = (
        list(SUPPORTED_OPERATIONS) if settings.composition_worker_enabled else None
    )
    while True:
        try:
            await asyncio.sleep(interval)
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
            reaped = await repo.reap_stale_jobs(cutoff, exclude_operations=exclude_ops)
            if reaped:
                logger.info("job reaper: marked %d stale job(s) failed", reaped)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("job reaper sweep failed (retrying next interval)", exc_info=True)


async def _authoring_sweep_loop() -> None:
    """RAID Wave D4 — restart durability for autonomous authoring runs. At
    startup (first pass runs immediately) + every `authoring_sweep_secs`,
    guarded-claim `running` runs whose driver heartbeat is stale (a restart
    killed their in-process driver task, or a start was deferred at the
    DRIVER_MAX_INFLIGHT cap) and resume each from current_unit. The claim is a
    guarded UPDATE (campaign-service claim_active_campaigns pattern) so
    concurrent replicas take disjoint runs. A transient failure is logged and
    retried next interval — it never kills the loop."""
    from app.deps import get_authoring_run_service

    interval = settings.authoring_sweep_secs
    while True:
        try:
            svc = await get_authoring_run_service()
            claimed = await svc.sweep_stale_runs()
            if claimed:
                logger.info(
                    "authoring sweep: re-claimed %d stale run(s): %s",
                    len(claimed), [str(r.run_id) for r in claimed],
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "authoring sweep failed (retrying next interval)", exc_info=True,
            )
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    try:
        # Fail-fast: a missing/unreachable DB stops startup.
        await create_pool(settings.composition_db_url)
        await run_migrations(get_pool())
    except Exception:
        logger.exception("composition-service startup failed before yield")
        await close_pool()
        raise
    reaper_task = (
        asyncio.create_task(_reap_stale_jobs_loop())
        if settings.job_reaper_sweep_secs > 0
        else None
    )
    # RAID Wave D4 — authoring-run durability sweep (startup + periodic).
    authoring_sweep_task = (
        asyncio.create_task(_authoring_sweep_loop())
        if settings.authoring_sweep_secs > 0
        else None
    )
    # D-GRANT-INSTANT-REVOKE — tail book-service grant revokes (Redis) → drop the
    # cached grant on the spot (vs the 45s TTL). Best-effort; close_grant_client stops it.
    if settings.redis_url:
        get_grant_client().start_revoke_consumer(settings.redis_url)

    # MCP fan-out S-COMPOSE — run the /mcp StreamableHTTP session manager. The /mcp
    # sub-app is mounted at module level, but a mounted Starlette sub-app's lifespan
    # is NOT auto-run under FastAPI, so we enter its session manager here.
    # stateless_http=True → scope arrives in headers, no per-session state. Failure
    # to start affects ONLY the /mcp path — the bespoke /v1/composition REST API
    # stays up regardless (dual-run).
    mcp_exit_stack: AsyncExitStack | None = None
    try:
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.enter_async_context(mcp_server.session_manager.run())
        logger.info("S-COMPOSE: MCP session manager started; /mcp facade live")
    except Exception:  # noqa: BLE001 — /mcp is best-effort relative to the REST API
        logger.warning(
            "S-COMPOSE: MCP session manager failed to start (non-fatal) — "
            "/mcp facade unavailable, /v1/composition still serves",
            exc_info=True,
        )
        if mcp_exit_stack is not None:
            await mcp_exit_stack.aclose()
            mcp_exit_stack = None

    try:
        yield
    finally:
        # Stop the MCP session manager first so in-flight tool calls are cancelled
        # before the pool/clients they touch are closed.
        if mcp_exit_stack is not None:
            with contextlib.suppress(Exception):
                await mcp_exit_stack.aclose()
        if reaper_task is not None:
            reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper_task
        if authoring_sweep_task is not None:
            authoring_sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await authoring_sweep_task
        await close_knowledge_client()
        await close_book_client()
        await close_glossary_client()
        await close_kal_client()
        await close_embedding_client()
        await close_web_search_client()
        await close_llm_client()
        await close_grant_client()  # E0-4c
        await close_pool()


app = FastAPI(title="composition-service", lifespan=lifespan)

app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OTel SERVER + httpx CLIENT spans. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
# is unset. Added after add_middleware so the OTel ASGI layer lands outermost.
setup_tracing("composition-service", app=app)


@app.exception_handler(Exception)
async def _trace_id_500_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception (500): %s", exc)
    tid = trace_id_var.get()
    return JSONResponse(
        status_code=500,
        content={
            "detail": "internal server error",
            "trace_id": tid,
            "otel_trace_id": current_otel_trace_id(),
        },
        headers={"X-Trace-Id": tid or ""},
    )


app.include_router(health.router)
app.include_router(ping.public_router)
app.include_router(ping.internal_router)
app.include_router(metrics.router)
app.include_router(works.router)
app.include_router(prose.router)
app.include_router(approve.router)
app.include_router(grounding.router)
app.include_router(progress.router)  # LOOM T4.2 — writing-progress stats
app.include_router(style_voice.router)  # LOOM T3.5 — style & voice steering
app.include_router(references.router)  # LOOM T3.6 — author reference shelf + retrieval
app.include_router(motif.router)  # Narrative motif library W1 — CRUD/adopt/publish/catalog
app.include_router(motif_sync.router)  # W11 — publish/adopt sync (upstream-diff + apply-merge)
app.include_router(arc.router)  # W10 — arc-template CRUD/adopt/catalog + apply-preview
app.include_router(import_source.router)  # W9 — import_source CRUD (per-user deconstruct input)
app.include_router(engine.router)
app.include_router(outline.router)
app.include_router(outline.internal_router)  # 22 SC6/B4 — scene decompiler (internal token)
app.include_router(plan.router)
app.include_router(plan_overlay.router)  # 24 Plan Hub v2 H1.3 — decorations aggregate (read surface #3)
app.include_router(plan_forge.router)
app.include_router(plan_bootstrap.router)  # PlanForge auto-bootstrap gate POC
app.include_router(authoring_runs.router)  # RAID Wave D2 — autonomy-dial run FSM
app.include_router(internal_eval.router)
app.include_router(internal_job_control.router)  # Unified Job Control Plane P3
app.include_router(internal_model_settings.router)  # D-CHATAI-M1B — Book tier model-settings read
app.include_router(internal_plan_state.router)  # per-turn "does this book have an arc plan?" probe
app.include_router(internal_structure_state.router)  # Phase G · G0 — per-turn "did a compile write linked structure?" probe
app.include_router(canon.router)
app.include_router(narrative_threads.router)
app.include_router(conformance.router)  # W5 — motif-conformance trace read (advisory)
app.include_router(actions.router)  # MCP fan-out S-COMPOSE Tier-W confirm/preview

# MCP fan-out S-COMPOSE — mount the /mcp facade. stateless_http=True + path="/" so
# this yields the endpoint at exactly "/mcp"; the session manager is run in the
# lifespan above (a mounted sub-app's lifespan is not auto-run under FastAPI).
app.mount("/mcp", build_mcp_app())
