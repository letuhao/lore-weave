import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.client.book_steering_client import close_book_steering_client, init_book_steering_client
from app.client.glossary_capture_client import (
    close_canon_capture_client,
    init_canon_capture_client,
)
from app.client.known_entities_client import (
    close_known_entities_client,
    init_known_entities_client,
)
from app.client.user_skills_client import close_user_skills_client, init_user_skills_client
from app.client.registry_workflows_client import close_workflows_client, init_workflows_client
from app.client.registry_commands_client import close_commands_client, init_commands_client
from app.client.registry_hooks_client import close_hooks_client, init_hooks_client
from app.client.registry_subagents_client import (
    close_subagents_client,
    init_subagents_client,
)
from app.client.knowledge_client import close_knowledge_client, init_knowledge_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool, get_pool
from app.middleware.trace_id import TraceIdMiddleware, current_trace_id
from app.routers import (
    ai_settings, catalog, evaluate, feedback, internal, messages, outputs,
    sessions, tool_permissions, voice,
)
from app.storage.minio_client import delete_object, ensure_bucket

logger = logging.getLogger(__name__)

# Optional per-deploy log level for the app loggers (default WARNING). Set LOG_LEVEL=INFO to
# surface the step-runner's per-hop decisions + the agent-behavior monitor (advertised tool
# surface, tool decisions) when diagnosing a turn.
#
# OBSERVABILITY FIX: setting only the LOGGER level was a silent no-op — the "app" logger has
# no handler, so its records propagate to root, whose only emitter is `logging.lastResort`
# (a WARNING-level stderr handler). So `logger.warning` surfaced but every `logger.info`
# diagnostic (47 of them) was dropped, and LOG_LEVEL=INFO did nothing. Attach a stdout
# handler AT the requested level on "app" so the diagnostic logs actually emit.
import os as _os
_lvl = _os.getenv("LOG_LEVEL", "").upper()
if _lvl in ("DEBUG", "INFO", "WARNING", "ERROR"):
    _level = getattr(logging, _lvl)
    _app_logger = logging.getLogger("app")
    _app_logger.setLevel(_level)
    if not any(isinstance(h, logging.StreamHandler) for h in _app_logger.handlers):
        _h = logging.StreamHandler()
        _h.setLevel(_level)
        _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
        _app_logger.addHandler(_h)
        _app_logger.propagate = False  # emit once via our handler, not again via root

async def _audio_cleanup_loop():
    """Periodically delete expired voice audio segments. AUDIO_TTL_HOURS is the deploy
    CEILING; each user's effective TTL is resolved per-segment (WS-4.3). Interval via
    AUDIO_CLEANUP_INTERVAL_HOURS."""
    from app.db.pool import get_pool
    from app.services.audio_retention import delete_expired_audio
    interval = settings.audio_cleanup_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            pool = get_pool()
            object_keys = await delete_expired_audio(pool, settings.audio_ttl_hours)
            for key in object_keys:
                try:
                    await delete_object(key)
                except Exception:
                    pass  # S3 lifecycle is safety net
            if object_keys:
                logger.info("audio cleanup: deleted %d expired segments", len(object_keys))
        except Exception:
            logger.warning("audio cleanup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)
    try:
        await ensure_bucket()
    except Exception:
        pass  # MinIO may not be running in dev; don't block startup
    # K5: initialise the long-lived knowledge-service HTTP client.
    init_knowledge_client()
    # RAID C1: long-lived book-service steering client (degrades to [] when down).
    init_book_steering_client()
    # T5 (D2): long-lived known-entities client for the intent gate (degrades to
    # an empty set → gate opens, bias-to-include).
    init_known_entities_client()
    # WS-4C Half A: long-lived glossary canon-capture client (degrades to a skipped
    # capture; the post-turn task swallows every failure).
    init_canon_capture_client()
    # REG-P1-05: long-lived agent-registry user-skills client (degrades to constants).
    init_user_skills_client()
    # WS-2b: long-lived agent-registry workflows client (degrades to no curated workflows).
    init_workflows_client()
    # REG-P4-01: long-lived agent-registry commands client (degrades to pass-through).
    init_commands_client()
    # REG-P4-03: long-lived agent-registry hooks client (degrades to unhooked turn).
    init_hooks_client()
    # REG-P5-01: long-lived agent-registry subagents client (degrades to no delegation).
    init_subagents_client()
    # Start background cleanup task
    cleanup_task = asyncio.create_task(_audio_cleanup_loop())
    yield
    cleanup_task.cancel()
    await close_knowledge_client()
    await close_book_steering_client()
    await close_known_entities_client()
    await close_canon_capture_client()
    await close_user_skills_client()
    await close_workflows_client()
    await close_commands_client()
    await close_hooks_client()
    await close_subagents_client()
    await close_pool()


app = FastAPI(title="chat-service", lifespan=lifespan)

# TraceIdMiddleware is added first so it ends up innermost in
# Starlette's stack — CORS wraps it, which is what we want: CORS
# preflight OPTIONS responses are handled by CORSMiddleware directly
# (no trace id needed), while every normal request/response still
# flows through TraceIdMiddleware and carries X-Trace-Id.
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 6c-γ — OpenTelemetry: instrument this app for SERVER spans + httpx
# for outbound CLIENT spans. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
# Called AFTER add_middleware so the OTel ASGI middleware lands OUTERMOST
# (Starlette prepends middleware) — the SERVER span then covers the full
# request, CORS + TraceId middleware included. /review-impl(6c-γ) LOW#4.
setup_tracing("chat-service", app=app)

@app.exception_handler(Exception)
async def _trace_id_500_handler(request: Request, exc: Exception) -> JSONResponse:
    """K7e + D-PHASE6C-TRACE-ID-UNIFY: emit BOTH the middleware's
    trace_id (for log grep) AND the OTel trace id (for Tempo lookup).
    See knowledge-service's matching handler for the rationale —
    both services keep the same response shape so a single FE error
    surface can render either id when present.
    HTTPException keeps its own envelope via FastAPI's built-in handler."""
    logger.exception("unhandled exception (500): %s", exc)
    tid = current_trace_id()
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


app.include_router(sessions.router)
app.include_router(catalog.router)
# /v1/chat/templates* retired 2026-06-24 — scripts + start moved to
# roleplay-service (/v1/roleplay). /evaluate (M6 debrief), the internal
# session-create, and the turn loop stay here (reused by roleplay-service).
app.include_router(messages.router)
app.include_router(outputs.router)
app.include_router(evaluate.router)  # M6: interview-practice scorecard
app.include_router(voice.router)
app.include_router(voice.voice_mgmt_router)
app.include_router(feedback.router)
app.include_router(internal.router)  # FD-2: chat-turn text fetch for KG extraction
app.include_router(internal.telemetry_router)  # W1: /internal/tool-health telemetry
app.include_router(ai_settings.prefs_router)  # Chat & AI settings — per-user prefs blob
app.include_router(ai_settings.effective_router)  # Chat & AI settings — resolved cascade
app.include_router(ai_settings.capabilities_router)  # Deploy-tier capability ceilings (D-WS4C-EFFECTIVE-VALUE)
app.include_router(tool_permissions.router)  # Track C WS-3: view/revoke/deny the tool-consent allowlist


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
