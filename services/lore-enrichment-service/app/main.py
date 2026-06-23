import contextlib
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.api import eval as eval_api
from app.api import book_profile, compose, compose_tasks, gaps, internal_job_control, jobs, observability, proposals, sources, templates, uploads
from app.clients.grant_client import close_grant_client, init_grant_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool
from app.logging_config import setup_logging, trace_id_var
from app.mcp.server import build_mcp_app, mcp_server
from app.middleware.trace_id import TraceIdMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # C18 — install structured JSON logging before anything logs.
    setup_logging(settings.log_level)
    # Open the DB pool, then apply idempotent migrations (C2 owns schema).
    # Mirrors knowledge-service: run_migrations on every startup. NO
    # KG/glossary/book client wiring here (C1), NO redis/minio (later cycles).
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)
    # E0 grant authority (D-ENRICH-MCP-OWNER-GATE) — the auto-enrich tenancy gate
    # resolves (user, book) grants against book-service via this shared client.
    init_grant_client()
    logger.info("lore-enrichment-service started on port %d", settings.port)

    # MCP fan-out — run the /mcp StreamableHTTP session manager. The /mcp sub-app is
    # mounted at module level, but a mounted Starlette sub-app's lifespan is NOT
    # auto-run under FastAPI, so we enter its session manager here. Failure to start
    # affects ONLY the /mcp path — the bespoke REST API stays up regardless.
    mcp_exit_stack: AsyncExitStack | None = None
    try:
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.enter_async_context(mcp_server.session_manager.run())
        logger.info("lore-enrichment MCP session manager started; /mcp facade live")
    except Exception:  # noqa: BLE001 — /mcp is best-effort relative to the REST API
        logger.warning(
            "lore-enrichment MCP session manager failed to start (non-fatal) — "
            "/mcp facade unavailable, REST still serves", exc_info=True)
        if mcp_exit_stack is not None:
            await mcp_exit_stack.aclose()
            mcp_exit_stack = None

    try:
        yield
    finally:
        # Stop the MCP session manager first so in-flight tool calls are cancelled
        # before the pool they touch is closed.
        if mcp_exit_stack is not None:
            with contextlib.suppress(Exception):
                await mcp_exit_stack.aclose()
        await close_grant_client()
        await close_pool()


app = FastAPI(title="lore-enrichment-service", lifespan=lifespan)

# TraceIdMiddleware first so it ends up innermost (CORS wraps it): CORS
# preflight is handled by CORSMiddleware directly while every normal request
# flows through TraceIdMiddleware and carries X-Trace-Id.
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# C18 — OpenTelemetry: instrument this app for SERVER spans + httpx for
# outbound CLIENT spans (covers the provider-registry / knowledge-service
# clients). No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset (dev). Called AFTER
# add_middleware so the OTel ASGI middleware lands OUTERMOST — the SERVER span
# then covers the full request, CORS + TraceId middleware included.
setup_tracing("lore-enrichment-service", app=app)


@app.exception_handler(Exception)
async def _trace_id_500_handler(request: Request, exc: Exception) -> JSONResponse:
    """Emit BOTH the middleware trace_id (for log grep) AND the OTel trace id
    (for Tempo lookup) on an unhandled 500 — mirrors knowledge/chat-service so a
    single FE error surface can render either id. HTTPException keeps its own
    envelope via FastAPI's built-in handler (not caught here)."""
    logger.exception("unhandled exception (500): %s", exc)
    tid = trace_id_var.get()
    otel_tid = current_otel_trace_id()
    return JSONResponse(
        status_code=500,
        content={
            "detail": "internal server error",
            "trace_id": tid,
            "otel_trace_id": otel_tid,
        },
        headers={"X-Trace-Id": tid or ""},
    )


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    # Liveness probe — constant ok, NO DB access (matches platform convention).
    # DB-readiness is the separate /ready probe (DEFERRED-042). A DB blip must
    # NOT fail liveness (no crash-loop) — only readiness drains traffic.
    return "ok"


# C18 — observability + probes: /metrics (Prometheus) + /ready (DB-readiness).
app.include_router(observability.router)

# C3 contract-freeze stub routers (one per resource family). Behaviour ships in
# later cycles; these mount the frozen OpenAPI surface as 200/501 stubs.
app.include_router(jobs.router)
app.include_router(gaps.router)  # D1 — gap auto-detection (read-only triage)
app.include_router(compose.router)  # Compose — unified async input modes (gap|draft|context|files)
app.include_router(compose_tasks.router)  # Phase 3 M2 — poll one-shot compose tasks (suggest/intent)
app.include_router(uploads.router)  # Compose slice 3 — mode F file uploads (async extract+OCR)
app.include_router(proposals.router)
app.include_router(sources.router)
app.include_router(sources.books_router)  # de-bias C2 T6 — chapter-selection grounding ingest
app.include_router(book_profile.router)  # de-bias C3 — per-book profile authoring (GET/PUT/suggest)
app.include_router(book_profile.internal_router)  # wiki-llm M1 — S2S profile read (knowledge-service)
app.include_router(templates.router)

# C15 — internal eval-gate status route (P2/P3 gate signal for C16/C17).
app.include_router(eval_api.router)

# Unified Job Control Plane P3 — S2S job_id-keyed control (cancel/pause/resume).
app.include_router(internal_job_control.router)

# MCP fan-out — mount the /mcp facade. stateless_http=True + path="/" so this
# yields the endpoint at exactly "/mcp"; the session manager is run in the lifespan
# above (a mounted sub-app's lifespan is not auto-run under FastAPI).
app.mount("/mcp", build_mcp_app())
