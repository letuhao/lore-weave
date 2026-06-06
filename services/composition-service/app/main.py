"""composition-service entrypoint (LOOM Composition V0 — M0 skeleton).

Lifespan: create_pool → run_migrations → yield → close_pool. M0 boots the
HTTP skeleton (health/ping/metrics) wired to loreweave_composition; schema,
repos, clients, packer, engine, and the real /v1/composition/* endpoints land
in M1–M6. Mirrors knowledge-service house style (ASGI trace middleware, JSON
logging, OTel-optional, terse 500 envelope).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loreweave_obs import current_otel_trace_id, setup_tracing

from app.clients.book_client import close_book_client
from app.clients.glossary_client import close_glossary_client
from app.clients.knowledge_client import close_knowledge_client
from app.clients.llm_client import close_llm_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool, get_pool
from app.logging_config import setup_logging, trace_id_var
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import (
    canon, engine, grounding, health, metrics, outline, ping, plan, prose, works,
)

logger = logging.getLogger(__name__)


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
    try:
        yield
    finally:
        await close_knowledge_client()
        await close_book_client()
        await close_glossary_client()
        await close_llm_client()
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
app.include_router(grounding.router)
app.include_router(engine.router)
app.include_router(outline.router)
app.include_router(plan.router)
app.include_router(canon.router)
