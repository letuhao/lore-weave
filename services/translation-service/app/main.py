from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .config import settings
from .database import create_pool, close_pool, get_pool
from .migrate import run_migrations
from .routers import settings as settings_router
from .routers import jobs as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)

    # Startup recovery: mark stale jobs as failed
    await pool.execute("""
        UPDATE translation_jobs
        SET status = 'failed', error_message = 'server_restart', finished_at = now()
        WHERE status IN ('pending', 'running')
          AND created_at < now() - interval '1 hour'
    """)

    yield

    await close_pool()


app = FastAPI(title="translation-service", lifespan=lifespan)

app.include_router(settings_router.router)
app.include_router(jobs_router.router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
