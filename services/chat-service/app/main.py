from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool, get_pool
from app.routers import messages, outputs, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    await run_migrations(pool)
    yield
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


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"
