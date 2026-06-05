"""composition-service settings (LOOM Composition V0 — M0).

pydantic-settings BaseSettings — the service fails to start if any
required secret/DSN is missing (CLAUDE.md: no hardcoded secrets).
Mirrors knowledge-service's config shape; single DB (loreweave_composition).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — service fails to start if any of these are missing.
    composition_db_url: str
    internal_service_token: str
    jwt_secret: str

    # Optional with defaults.
    redis_url: str = "redis://redis:6379"
    log_level: str = "INFO"
    port: int = 8093

    # Internal service URLs — consumed by the M3 client wrappers.
    knowledge_internal_url: str = "http://knowledge-service:8092"
    glossary_internal_url: str = "http://glossary-service:8088"
    book_internal_url: str = "http://book-service:8082"
    llm_gateway_internal_url: str = "http://provider-registry-service:8085"

    # Packer budget knobs (M4) — declared here so config is stable across
    # milestones; unused until the packer lands.
    pack_token_budget: int = 6000


settings = Settings()  # type: ignore[call-arg]
