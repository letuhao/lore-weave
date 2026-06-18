"""video-gen-service config — Phase 5e-α.

Previously app/routers/generate.py read settings directly from os.environ.
This module centralizes them via pydantic-settings to match the pattern
used by chat-service, translation-service, and knowledge-service.

/review-impl(DESIGN) MED#2: the legacy `PROVIDER_REGISTRY_URL` env var
(used by the removed `resolve_credentials` flow) is intentionally NOT
included here. After 5e-α, no code in video-gen-service reads it;
retaining the field would invite drift. The SDK uses
`provider_registry_internal_url` only.

Phase 5f: video-gen-service is a permanent thin domain BFF for video
generation (it is NOT deleted — see LLM_PIPELINE_PHASE5F_DESIGN.md §1).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Where the SDK talks (provider-registry-service /internal/llm/jobs).
    provider_registry_internal_url: str = "http://provider-registry-service:8085"

    # X-Internal-Token for svc-to-svc auth (matches SDK auth_mode='internal').
    internal_service_token: str

    # Shared HS256 secret for verifying incoming user JWTs (Phase 5f G3).
    # Required, no default — the service fails fast at startup if unset.
    # Must match auth-service's JWT_SECRET (docker-compose wires the same
    # ${JWT_SECRET} into every service). Mirrors chat-service Settings.
    jwt_secret: str

    # Usage-billing record endpoint (best-effort POST).
    usage_billing_service_url: str = "http://usage-billing-service:8088"

    # MinIO storage for downloaded video bytes.
    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_external_url: str = "http://localhost:9123"

    # ── LLM re-arch Phase 3 M5 — decoupled video-gen (job-row + terminal-event).
    # When VIDEO_GEN_DECOUPLE_ENABLED, POST /generate submits the gateway job
    # (submit_job, NOT generate_video — don't block) → persists a video_gen_jobs
    # row → returns 202; a separate `python -m app.worker` consumes
    # loreweave:events:llm_job_terminal, downloads the finished video → MinIO →
    # marks the row done; GET /v1/video-gen/jobs/{id} polls. Default False →
    # today's inline 201 path verbatim (zero contract change until the FE adopts
    # 202 + poll). The DSN has a dev default (only used when the flag is on) so
    # the inline path + the existing test suite start without the new env.
    video_gen_db_url: str = (
        "postgresql://loreweave:loreweave_dev@postgres:5432/loreweave_video_gen"
    )
    redis_url: str = "redis://redis:6379"
    video_gen_decouple_enabled: bool = False
    # Stuck-job sweeper (the worker's runtime backstop — a Redis stream gives no
    # post-ACK redelivery, so a lost terminal event / consumer crash needs a
    # time-based re-drive). Timeout must exceed the worst-case video wall-clock
    # (ComfyUI Wan/LTX 5-20 min) so a slow job isn't mistaken for stuck.
    video_gen_job_sweep_secs: int = 120
    video_gen_job_sweep_timeout_secs: int = 1800


settings = Settings()
