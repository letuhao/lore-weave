from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration. Required secrets have NO default, so module-load
    `settings = Settings()` raises (container crashes) if any is missing —
    CLAUDE.md "services fail to start if missing". Read-dependency URLs default
    to the in-compose service names; override via env for other environments.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required — fail-fast on missing.
    database_url: str = Field(validation_alias="LORE_ENRICHMENT_DB_URL")
    jwt_secret: str = Field(validation_alias="JWT_SECRET")
    internal_service_token: str = Field(validation_alias="INTERNAL_SERVICE_TOKEN")

    # Read-dependency URLs (C1 wires the clients; defaults point at compose svc names).
    knowledge_service_url: str = "http://knowledge-service:8092"
    glossary_service_url: str = "http://glossary-service:8088"
    book_service_url: str = "http://book-service:8082"
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    redis_url: str = "redis://redis:6379"

    # Max age (seconds) of a PASSING eval run before the P2/P3 gate treats it as
    # STALE → LOCKED (WARN-2 / DEFERRED-055, fail-closed on staleness). A passing
    # run older than this no longer unlocks the higher-cost tier — the eval must
    # be re-run against the current corpus. Default 7 days. 0 disables the bound
    # (any passing run stays valid — NOT recommended in production).
    gate_max_age_seconds: float = Field(
        default=7 * 24 * 3600.0,
        validation_alias="LORE_ENRICHMENT_GATE_MAX_AGE_SECONDS",
    )

    # C2 / LE-056 — judge-ensemble κ (Fleiss inter-rater agreement) floor. An eval
    # run is only `acceptable` (unlocks P2/P3) when ≥2 DISTINCT judge families voted
    # AND κ ≥ this floor. Default 0.0 = reject only BELOW-CHANCE agreement (judges
    # actively disagree); raise toward 0.2 to also reject merely-slight agreement.
    judge_kappa_floor: float = Field(
        default=0.0, validation_alias="LORE_ENRICHMENT_JUDGE_KAPPA_FLOOR"
    )

    port: int = 8093

    # C18 — structured-logging level. INFO in prod; DEBUG locally via env.
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")


settings = Settings()
