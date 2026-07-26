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
    # X2 (temporal-knowledge) — the Knowledge Access Layer (KAL / knowledge-gateway)
    # is the single versioned read boundary for entity/lore/KG knowledge (INV-KAL).
    # Entity-knowledge READS the KAL covers (roster/facts/canonical/search) route
    # here instead of glossary/knowledge `/internal/*` directly.
    knowledge_gateway_url: str = Field(
        default="http://knowledge-gateway:3000",
        validation_alias="KNOWLEDGE_GATEWAY_URL",
    )
    redis_url: str = "redis://redis:6379"

    # Unified Job Control Plane P5 — fair scheduling / per-tenant concurrency. Lore-
    # enrichment runs each job SYNCHRONOUSLY in the API handler (no PUSH fan-out), so the
    # fairness lever is a per-owner CONCURRENT-JOB cap: `create_job` acquires a slot
    # (lane `lore-enrichment:job`, owner=user_id) before running and releases it after; at
    # cap → 429. Flag-gated (default OFF) + fail-open on a redis blip. The lease TTL is the
    # crash-leak backstop (must exceed the longest job runtime; release-in-finally is the
    # fast path).
    p5_sched_enabled: bool = Field(default=False, validation_alias="P5_SCHED_ENABLED")
    p5_owner_cap: int = Field(default=5, validation_alias="P5_OWNER_CAP")
    p5_lease_ttl_ms: int = Field(default=3_600_000, validation_alias="P5_LEASE_TTL_MS")

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

    # Compose slice 3 (mode F) — MinIO object storage for uploaded files. The
    # compose stack provides MINIO_* for the python services; bucket is per-service.
    minio_endpoint: str = Field(default="minio:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="loreweave", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="loreweave_dev_minio_secret", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="lore-enrichment-uploads", validation_alias="MINIO_BUCKET")
    minio_use_ssl: bool = Field(default=False, validation_alias="MINIO_USE_SSL")
    # Per-file upload caps (mode F). Bound the synchronous read + the OCR fan-out.
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, validation_alias="LORE_ENRICHMENT_UPLOAD_MAX_BYTES")
    upload_max_pages: int = Field(default=300, validation_alias="LORE_ENRICHMENT_UPLOAD_MAX_PAGES")

    # Reaper (D-COMPOSE-S3-UPLOAD-REAPER + D-COMPOSE-CONTEXT-CORPUS-SCOPE) — a
    # periodic background sweep on the worker that (1) fails uploads stuck in
    # 'processing' past a service restart, (2) deletes orphan MinIO objects whose
    # row never landed, (3) garbage-collects compose-ephemeral grounding corpora by
    # TTL. All advisory cleanup — never touches canon. Disable via env in a stack
    # where the worker doesn't run.
    reaper_enabled: bool = Field(default=True, validation_alias="LORE_ENRICHMENT_REAPER_ENABLED")
    reaper_interval_s: float = Field(default=3600.0, validation_alias="LORE_ENRICHMENT_REAPER_INTERVAL_S")
    # An upload still 'processing' older than this lost its background task (e.g. a
    # service restart mid-extract) → fail it so the files branch stops 409-ing forever.
    # MUST exceed the worst-case LIVE extraction time, or the reaper (worker process)
    # would falsely-fail a slow-but-running extraction (API process) cross-process: a
    # full `upload_max_pages` scanned-PDF OCR (CJK Tesseract ~seconds/page) can run
    # tens of minutes. 2h gives generous headroom; a genuine orphan (restart) is still
    # caught, just later. (A late success self-heals — the bg task's final
    # SET status='ready' is unconditional — but a transient 'failed' is avoided.)
    upload_stale_processing_s: float = Field(default=2 * 3600.0, validation_alias="LORE_ENRICHMENT_UPLOAD_STALE_S")
    # Only delete an orphan object (no row) once it is older than this grace window,
    # so an object mid-upload (row INSERT in flight) is never raced into deletion.
    upload_orphan_grace_s: float = Field(default=60 * 60.0, validation_alias="LORE_ENRICHMENT_UPLOAD_ORPHAN_GRACE_S")
    # Compose-ephemeral grounding corpora (mode-C pastes + mode-F files) older than
    # this are reaped. Generous default (30d) so a recent paste still re-grounds.
    context_corpus_ttl_s: float = Field(default=30 * 24 * 3600.0, validation_alias="LORE_ENRICHMENT_CONTEXT_CORPUS_TTL_S")

    # Compose-task stuck sweeper (D-M2-COMPOSE-TASK-RACE + D-M2-COMPOSE-TASK-SWEEPER) —
    # a periodic worker sweep that re-drives `enrichment_compose_task` rows stranded in
    # ('pending','running') past a timeout (a redis-miss at submit, or a worker that
    # crashed mid-compute leaving a 'running' row no event will re-deliver). Mirrors
    # worker-ai's Wave-1b resume sweeper. The timeout DOUBLES as the active-worker idle
    # window for the FOR-UPDATE claim: a 'running' row touched MORE recently than the
    # timeout is assumed live (another worker is on it) and is left alone; a staler row
    # is fair game to re-drive. So the timeout MUST exceed the worst-case single-task
    # compute (book metadata + sample-chapter fetch + ONE LLM call) — 900s (15m) gives
    # generous headroom. interval<=0 disables the loop.
    compose_task_sweep_interval_s: float = Field(
        default=60.0, validation_alias="LORE_ENRICHMENT_COMPOSE_TASK_SWEEP_INTERVAL_S"
    )
    compose_task_sweep_timeout_s: float = Field(
        default=900.0, validation_alias="LORE_ENRICHMENT_COMPOSE_TASK_SWEEP_TIMEOUT_S"
    )
    compose_task_sweep_batch: int = Field(
        default=20, validation_alias="LORE_ENRICHMENT_COMPOSE_TASK_SWEEP_BATCH"
    )

    port: int = 8093

    # C18 — structured-logging level. INFO in prod; DEBUG locally via env.
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")


settings = Settings()
