import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients.glossary_client import close_glossary_client, init_glossary_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pools, create_pools, get_knowledge_pool
from app.logging_config import setup_logging, trace_id_var
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import context, health, metrics, ping
from app.routers.public import projects as public_projects
from app.routers.public import summaries as public_summaries
from app.routers.public import user_data as public_user_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    # Fail-fast: if either pool cannot be created, raise and stop startup.
    await create_pools(settings.knowledge_db_url, settings.glossary_db_url)
    await run_migrations(get_knowledge_pool())
    # Long-lived httpx client for glossary-service calls (K4b).
    init_glossary_client()
    logger.info("knowledge-service started on port %d", settings.port)
    try:
        yield
    finally:
        await close_glossary_client()
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
app.include_router(metrics.router)
app.include_router(public_projects.router)
app.include_router(public_summaries.router)
app.include_router(public_user_data.router)
