from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import create_pool, close_pool
from .migrate import run_migrations
from .broker import connect_broker, close_broker
from .routers import settings as settings_router
from .routers import jobs as jobs_router
from .routers import versions as versions_router
from .routers import coverage as coverage_router
from .routers import translate as translate_router


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

    yield

    await close_broker()
    await close_pool()


app = FastAPI(title="translation-service", lifespan=lifespan)

app.include_router(settings_router.router)
app.include_router(jobs_router.router)
app.include_router(versions_router.router)
app.include_router(coverage_router.router)
app.include_router(translate_router.router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
