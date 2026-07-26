import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loreweave_obs import setup_logging, setup_tracing

# Phase 5e-α: import settings at module load so missing required env
# vars (internal_service_token, minio_*, jwt_secret) fail FAST at process
# start rather than at first request. Mirrors translation-service pattern.
from .config import settings  # noqa: F401 — import for side-effect validation
from .db.migrate import run_migrations
from .db.pool import close_pool, create_pool
from .routers.generate import bootstrap_minio, router as generate_router
from .routers.internal_job_control import router as internal_job_control_router

# P2·A2a — shared JSON logging (video-gen had NO logging setup: it relied on the
# root logger's WARNING default + plain text). Structured JSON + dual trace ids now.
setup_logging("video-gen-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 5f G2+G4: ensure the media bucket exists + has a public-read
    # policy at startup, off the request hot path. Best-effort — a MinIO
    # outage here is logged, not fatal; ensure_bucket_ready self-heals on
    # the first request.
    bootstrap_minio()
    # LLM re-arch Phase 3 M5 — only the decoupled path needs the DB (the
    # submit endpoint persists a job row; the poll endpoint reads it). Flag
    # off → stay stateless (no pool, no migration) exactly as before.
    pool_up = False
    if settings.video_gen_decouple_enabled:
        pool = await create_pool(settings.video_gen_db_url)
        await run_migrations(pool)
        pool_up = True
    try:
        yield
    finally:
        if pool_up:
            await close_pool()


app = FastAPI(
    title="LoreWeave Video Generation Service",
    version="0.4.0",  # 5f: hardening (JWT verify + MinIO public-read bootstrap)
    description="Video generation via the unified LLM gateway.",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Phase 6c-γ — OpenTelemetry: instrument this app for SERVER spans + httpx
# for outbound CLIENT spans. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
# Called AFTER add_middleware so the OTel ASGI middleware lands OUTERMOST
# (Starlette prepends middleware) — the SERVER span then covers the full
# request, CORS included. /review-impl(6c-γ) LOW#4.
setup_tracing("video-gen-service", app=app)
app.include_router(generate_router, prefix="/v1/video-gen", tags=["video-gen"])
app.include_router(internal_job_control_router)  # Unified Job Control Plane P3


@app.get("/health")
async def health():
    # /review-impl(QC) LOW#5 — dropped `provider_configured` field which
    # was always True (Settings has a default URL). The migrated service
    # validates config at startup (Settings raises if internal_service_token
    # is missing — that env has no default), so if /health responds, the
    # service is configured. Provider connectivity is verified per-request
    # via the SDK; we don't probe it at /health to avoid hammering
    # provider-registry on health-check storms.
    return {
        "status": "ok",
        "service": "video-gen-service",
        "version": "0.4.0",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HTTP_PORT", "8088"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
