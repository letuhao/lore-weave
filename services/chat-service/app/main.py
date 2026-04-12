import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool, get_pool
from app.routers import messages, outputs, sessions, voice
from app.storage.minio_client import delete_object, ensure_bucket

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL = 4 * 3600  # 4 hours
_AUDIO_TTL = "48 hours"


async def _audio_cleanup_loop():
    """Periodically delete expired voice audio segments (48h TTL)."""
    from app.db.pool import get_pool
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        try:
            pool = get_pool()
            rows = await pool.fetch(
                f"DELETE FROM message_audio_segments WHERE created_at < now() - interval '{_AUDIO_TTL}' RETURNING object_key",
            )
            for r in rows:
                try:
                    await delete_object(r["object_key"])
                except Exception:
                    pass  # S3 lifecycle is safety net
            if rows:
                logger.info("audio cleanup: deleted %d expired segments", len(rows))
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
    # Start background cleanup task
    cleanup_task = asyncio.create_task(_audio_cleanup_loop())
    yield
    cleanup_task.cancel()
    await close_pool()


app = FastAPI(title="chat-service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(messages.router)
app.include_router(outputs.router)
app.include_router(voice.router)
app.include_router(voice.voice_mgmt_router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
