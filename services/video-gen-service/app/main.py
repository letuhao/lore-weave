import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers.generate import router as generate_router

app = FastAPI(
    title="LoreWeave Video Generation Service",
    version="0.2.0",
    description="Video generation from text prompts via BYOK provider credentials.",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(generate_router, prefix="/v1/video-gen", tags=["video-gen"])


@app.get("/health")
async def health():
    provider_configured = bool(os.getenv("PROVIDER_REGISTRY_URL"))
    return {
        "status": "ok",
        "service": "video-gen-service",
        "version": "0.2.0",
        "provider_connected": provider_configured,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HTTP_PORT", "8088"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
