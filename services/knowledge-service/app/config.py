from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — service fails to start if any of these are missing.
    knowledge_db_url: str
    glossary_db_url: str
    internal_service_token: str
    jwt_secret: str

    # Optional with defaults.
    redis_url: str = "redis://redis:6379"
    log_level: str = "INFO"
    port: int = 8092

    # K4b — glossary-service HTTP client for Mode 2 fallback selector.
    glossary_service_url: str = "http://glossary-service:8088"
    glossary_client_timeout_s: float = 0.5
    glossary_client_retries: int = 1

    # K4c — cross-layer dedup tunable. Number of distinct keyword tokens
    # that must overlap between an L1 summary and a glossary entity for
    # the entity to be dropped as redundant. Lower = more aggressive
    # dedup. 2 is the conservative default; raise to 3 if you find the
    # dedup is dropping entries it shouldn't.
    dedup_min_overlap: int = 2

    # K6.1 — per-layer timeouts inside the context builder. If any
    # layer exceeds its budget the builder skips that layer and
    # continues with the remaining pieces. Total ceiling defaults to
    # L0 + L1 + glossary = 400ms because layers run sequentially.
    context_l0_timeout_s: float = 0.1
    context_l1_timeout_s: float = 0.1
    context_glossary_timeout_s: float = 0.2


settings = Settings()
