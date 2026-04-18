import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients.book_client import close_book_client, get_book_client
from app.clients.glossary_client import close_glossary_client, init_glossary_client
from app.clients.provider_client import close_provider_client, get_provider_client
from app.config import settings
from app.db.migrate import run_migrations
from app.db.neo4j import close_neo4j_driver, get_neo4j_driver, init_neo4j_driver
from app.db.neo4j_schema import run_neo4j_schema
from app.db.pool import close_pools, create_pools, get_knowledge_pool
from app.logging_config import setup_logging, trace_id_var
from app.middleware.trace_id import TraceIdMiddleware
from app.routers import context, health, internal_extraction, metrics, ping
from app.routers.public import extraction as public_extraction
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
    # K16.2 — long-lived httpx client for book-service chapter counts.
    get_book_client()
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
    logger.info("knowledge-service started on port %d", settings.port)
    try:
        yield
    finally:
        # Phase 3 review issue 8: close in reverse dependency order.
        # ProviderClient is a leaf (nothing downstream depends on it)
        # so tear it down first, then glossary, then Neo4j, then DB
        # pools.
        await close_provider_client()
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
app.include_router(internal_extraction.router)
app.include_router(metrics.router)
app.include_router(public_extraction.router)
app.include_router(public_extraction.jobs_router)
app.include_router(public_projects.router)
app.include_router(public_summaries.router)
app.include_router(public_user_data.router)
