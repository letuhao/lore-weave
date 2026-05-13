# video-gen-service

FastAPI service in the LoreWeave monorepo that exposes **gateway-facing** routes for image/video generation (see `api-gateway-bff` → `/v1/video-gen/*`).

## ComfyUI implementation (sibling repository)

The heavy generation stack—**ComfyUI**, workflow graphs, GPU scheduling, and model packs—is developed in a separate repository: **`local-image-generator-service`**.

That stack is aimed to support (among others):

- **Base model families:** SD 1.5, SDXL, Illustrious, Flux 1 / Flux 2, Qwen Image, Wan, LTX Video  
- **Game-oriented workflows:** general game assets, **object / sprite sheets**, and **animation** outputs via custom Comfy pipelines  

Keep deployment and environment variables aligned between this service and `local-image-generator-service` as integration hardens.

## This repo

- `app/main.py` — FastAPI app  
- `app/routers/generate.py` — generation / health / models routes  
- `Dockerfile` — container build for compose  

For architecture context, see [design-drafts/loreweave-technical-architecture-and-pipelines.html](../../design-drafts/loreweave-technical-architecture-and-pipelines.html) and the root [README.md](../../README.md).
