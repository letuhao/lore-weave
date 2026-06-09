"""campaign-service settings (Auto-Draft Factory S1).

Fail-fast on missing secrets: `database_url`, `jwt_secret`, and
`internal_service_token` have no defaults — the service will not start
without them (CLAUDE.md: "No hardcoded secrets").
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    internal_service_token: str

    # Downstream service URLs (internal-token S2S). Defaults match the
    # docker-compose container DNS names + ports.
    book_service_internal_url: str = "http://book-service:8082"
    translation_service_internal_url: str = "http://translation-service:8087"
    knowledge_service_internal_url: str = "http://knowledge-service:8092"

    # Redis Streams — the projection consumer reads the existing event spine.
    redis_url: str = "redis://redis:6379"

    port: int = 8095

    # Saga driver tunables. S1 keeps reliability simple — a bounded in-flight
    # window per campaign (real rate-limit governor + circuit-breaker + budget
    # pause land in S3). The reconcile loop re-derives state from the projection
    # every `driver_tick_seconds`.
    driver_tick_seconds: float = 5.0
    driver_max_inflight_per_campaign: int = 20
    # Per-(chapter, stage) dispatch attempt cap before the row is marked failed.
    max_stage_attempts: int = 3
    # HTTP timeout for internal dispatch calls.
    dispatch_timeout_s: float = 10.0

    class Config:
        env_file = ".env"


settings = Settings()
