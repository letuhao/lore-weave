# video-gen-service

FastAPI service in the LoreWeave monorepo that exposes a **gateway-facing** route for video generation (see `api-gateway-bff` → `/v1/video-gen/*`). It is a permanent thin domain BFF — it verifies the user JWT, calls the unified LLM gateway via the `loreweave_llm` SDK, persists the result to MinIO, and records usage billing.

## ComfyUI implementation (sibling repository)

The heavy generation stack—**ComfyUI**, workflow graphs, GPU scheduling, and model packs—is developed in a separate repository: **`local-image-generator-service`**.

That stack is aimed to support (among others):

- **Base model families:** SD 1.5, SDXL, Illustrious, Flux 1 / Flux 2, Qwen Image, Wan, LTX Video  
- **Game-oriented workflows:** general game assets, **object / sprite sheets**, and **animation** outputs via custom Comfy pipelines  

Keep deployment and environment variables aligned between this service and `local-image-generator-service` as integration hardens.

## This repo

- `app/main.py` — FastAPI app  
- `app/routers/generate.py` — `/v1/video-gen/generate` route + `/health`  
- `Dockerfile` — container build for compose  

For architecture context, see [design-drafts/loreweave-technical-architecture-and-pipelines.html](../../design-drafts/loreweave-technical-architecture-and-pipelines.html) and the root [README.md](../../README.md).
