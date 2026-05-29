import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.db.pool import close_pool, create_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # C0 skeleton: open the DB pool only. NO migrations (C2 owns schema),
    # NO KG/glossary/book clients (C1), NO redis/minio (later cycles).
    await create_pool(settings.database_url)
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="lore-enrichment-service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
