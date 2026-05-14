"""video-gen-service config — Phase 5e-α.

Previously app/routers/generate.py read settings directly from os.environ.
This module centralizes them via pydantic-settings to match the pattern
used by chat-service, translation-service, and knowledge-service.

/review-impl(DESIGN) MED#2: the legacy `PROVIDER_REGISTRY_URL` env var
(used by the removed `resolve_credentials` flow) is intentionally NOT
included here. After 5e-α, no code in video-gen-service reads it;
retaining the field would invite drift before Phase 5f deletes the
service. The SDK uses `provider_registry_internal_url` only.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Where the SDK talks (provider-registry-service /internal/llm/jobs).
    provider_registry_internal_url: str = "http://provider-registry-service:8085"

    # X-Internal-Token for svc-to-svc auth (matches SDK auth_mode='internal').
    internal_service_token: str

    # Usage-billing record endpoint (best-effort POST).
    usage_billing_service_url: str = "http://usage-billing-service:8088"

    # MinIO storage for downloaded video bytes.
    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_external_url: str = "http://localhost:9123"


settings = Settings()
