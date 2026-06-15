"""jobs-service settings (Unified Job Control Plane P2).

Fail-fast on missing secrets: `database_url`, `jwt_secret`, and
`internal_service_token` have no defaults — the service will not start without
them (CLAUDE.md: "No hardcoded secrets"). The owner-scoped read API VERIFIES the
JWT signature (a cross-tenant job leak is the spec's load-bearing invariant), so
`jwt_secret` is genuinely required, not decorative.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    internal_service_token: str

    # Redis Streams — the projection consumer reads loreweave:events:jobs; the
    # SSE bridge publishes/subscribes per-user notify channels. Reconnect loop
    # tolerates redis startup races, so redis is NOT a hard depends_on.
    redis_url: str = "redis://redis:6379"

    port: int = 8096

    # ── Reconcile sweep (H1 backstop) ────────────────────────────────────────
    # The projection is a mirror of the per-service job rows (SSOT). The outbox
    # emit (P1) is the primary path; this periodic sweep re-reads each service's
    # `GET /internal/jobs?since=` and upserts to heal residual drift (outbox lag,
    # a projection-service outage). The cross-service endpoints land in P3
    # (D-JOBS-P2-RECONCILE-CROSS-SVC) — the scaffold ships here, disabled until a
    # source is configured. interval<=0 disables the loop.
    reconcile_interval_s: float = 300.0
    reconcile_enabled: bool = False
    # First-sweep lookback: on startup (or after a restart wipes the in-memory
    # watermark) the sweep re-reads each source's rows updated within this window.
    # The upsert is idempotent+monotonic, so a generous overlap is harmless.
    reconcile_lookback_s: float = 3600.0

    # Per-service internal URLs the reconcile sweep (P3) + control routing (P3)
    # target. Defaults match the docker-compose container DNS names.
    # Ports = each service's IN-CONTAINER listen port (compose service DNS name),
    # NOT its host-mapped port. Verified against infra/docker-compose.yml + live-smoke
    # (composition PORT=8093, video-gen HTTP_PORT=8088 — the P3-2 smoke caught the
    # earlier 8090/8200 guesses as 502-unreachable).
    knowledge_service_internal_url: str = "http://knowledge-service:8092"
    translation_service_internal_url: str = "http://translation-service:8087"
    composition_service_internal_url: str = "http://composition-service:8093"
    campaign_service_internal_url: str = "http://campaign-service:8095"
    lore_enrichment_service_internal_url: str = "http://lore-enrichment-service:8093"
    video_gen_service_internal_url: str = "http://video-gen-service:8088"

    log_level: str = "INFO"


settings = Settings()
