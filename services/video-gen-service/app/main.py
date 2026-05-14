import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Phase 5e-α: import settings at module load so missing required env
# vars (internal_service_token, minio_*) fail FAST at process start
# rather than at first request. Mirrors translation-service pattern.
from .config import settings  # noqa: F401 — import for side-effect validation
from .routers.generate import router as generate_router

app = FastAPI(
    title="LoreWeave Video Generation Service",
    version="0.3.0",  # 5e-α: SDK-based gateway integration
    description="Video generation via the unified LLM gateway (Phase 5e-α).",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(generate_router, prefix="/v1/video-gen", tags=["video-gen"])


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
        "version": "0.3.0",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HTTP_PORT", "8088"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
