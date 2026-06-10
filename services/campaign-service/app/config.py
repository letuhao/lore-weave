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
    # S5a — the pricing oracle (POST /internal/billing/estimate).
    provider_registry_internal_url: str = "http://provider-registry-service:8085"

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
    # D-CAMPAIGN-BESTEFFORT-EMIT-REDIS — stuck-`dispatched` self-heal. A stage that
    # has sat in `dispatched` longer than this (no completion event arrived — the
    # best-effort emit was lost, or the relay/consumer dropped it) is reconciled
    # against downstream ground-truth: marked `done` if the work actually finished,
    # else reset to `failed` for re-dispatch. Generous default so a genuinely
    # in-flight per-chapter job is never reconciled mid-flight (15 min ≫ a chapter
    # extraction or translation).
    stuck_dispatch_timeout_s: int = 900

    # ── S5a cost/time estimate heuristics (the wizard's pre-launch review) ──
    # The estimate is a deliberately rough, upper-leaning BAND — these knobs let
    # ops tune it without a redeploy. Tokens are derived from real chapter
    # byte_size (CJK-tuned): tokens ≈ bytes / est_bytes_per_token.
    est_bytes_per_token: float = 3.0            # CJK UTF-8 ≈ 3 bytes/char ≈ 1 tok/char
    est_fallback_chars_per_chapter: int = 3000  # used when byte_size is unavailable
    est_extraction_output_per_chapter: int = 400
    est_translation_output_ratio: float = 1.5   # target-language expansion (mirrors estimate.go)
    est_judge_output_per_chapter: int = 200     # verify + eval judge output
    est_low_factor: float = 0.5                 # band low = high × this (skips/cache/shorter outputs)
    est_seconds_per_stage_call: float = 20.0    # rough per-(chapter,stage) provider latency
    est_concurrency: int = 4                    # assumed effective parallelism

    class Config:
        env_file = ".env"


settings = Settings()
