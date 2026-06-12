import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.api import eval as eval_api
from app.api import book_profile, compose, compose_tasks, gaps, jobs, observability, proposals, sources, templates, uploads
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool
from app.logging_config import setup_logging, trace_id_var
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
    logger.info("lore-enrichment-service started on port %d", settings.port)
    try:
        yield
    finally:
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
