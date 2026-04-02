import os
from fastapi import FastAPI
from .routers.generate import router as generate_router

app = FastAPI(
    title="LoreWeave Video Generation Service",
    version="0.1.0",
    description="Video generation from text prompts. Skeleton service — returns placeholder responses until a provider is connected.",
)

app.include_router(generate_router, prefix="/v1/video-gen", tags=["video-gen"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "video-gen-service",
        "version": "0.1.0",
        "provider_connected": False,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HTTP_PORT", "8088"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
