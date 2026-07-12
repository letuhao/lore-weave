"""worker-ai configuration.

All settings via environment variables. Service fails to start if
required vars are missing (no defaults for DB URLs or tokens).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — worker cannot function without these.
    knowledge_db_url: str
    internal_service_token: str

    # Service URLs for HTTP calls.
    knowledge_service_url: str = "http://knowledge-service:8092"
    book_service_url: str = "http://book-service:8082"
    chat_service_url: str = "http://chat-service:8090"  # FD-2: chat-turn text fetch
    # C12c-a: glossary-service URL for the paginated entity list the
    # scope='glossary_sync' worker branch iterates.
    glossary_service_url: str = "http://glossary-service:8082"
    # Phase 4b-γ: provider-registry's internal LLM gateway. Worker-ai
    # calls submit_job through the loreweave_llm SDK; the SDK posts
    # to this base URL with the X-Internal-Token header.
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    # WS-2.8: usage-billing internal API — the distiller reads the user's daily spend guardrail to
    # degrade the BACKGROUND memory path when the daily cap is exhausted (foreground chat is unaffected).
    # Port 8086 (usage-billing's HTTP_ADDR; the canonical USAGE_BILLING_SERVICE_URL in docker-compose).
    usage_billing_service_url: str = "http://usage-billing-service:8086"

    # Timeouts (seconds).
    # Phase 4b-γ: extract_item_timeout_s is now used ONLY for the thin
    # persist-pass2 HTTP call (Neo4j write — fast, bounded). The LLM
    # wait happens inside the SDK's wait_terminal poll loop, which has
    # no overall timeout (gateway controls per-job lifetime).
    persist_pass2_timeout_s: float = 30.0  # Neo4j writes are seconds, not minutes
    extract_item_timeout_s: float = 120.0  # back-compat — to be removed in Phase 4d
    book_client_timeout_s: float = 10.0
    chat_client_timeout_s: float = 10.0  # FD-2: chat-turn text fetch (cheap read)
    # C12c-a: glossary list is cheap pagination (no LLM) — shorter
    # timeout than the book client's chapter fetch.
    glossary_client_timeout_s: float = 10.0
    # FD-27: provider-registry model-info fetch for the reasoning-model
    # advisory — a tiny metadata read, runs once per job. Best-effort.
    provider_registry_client_timeout_s: float = 5.0
    # WS-2.8: the daily-cap pre-check is a tiny indexed read; a short timeout, and it FAILS OPEN on
    # timeout/error (the provider-gateway reserve is the hard backstop), so a slow read never stalls
    # or silently pauses a user's memory.
    usage_billing_client_timeout_s: float = 5.0

    # Poll interval (seconds) — how often to check for running jobs.
    poll_interval_s: float = 5.0

    # FD-22 — block on a knowledge-service wake signal instead of a blind sleep
    # between poll cycles, so a freshly started job is picked up immediately.
    # The poll stays the source-of-truth; this only shortens the wait. Disabled
    # (or no redis_url) → plain sleep = pure polling. Stream name MUST match the
    # producer's `EXTRACTION_WAKE_STREAM` in knowledge-service.
    extraction_wake_enabled: bool = True
    extraction_wake_stream: str = "extraction.wake"

    # LLM re-arch Phase 2b WX (worker-ai extraction decouple): opt-in event-driven
    # decouple of extract_pass2 (submit→release→resume on the job's terminal event
    # instead of pinning a worker coroutine for the whole chapter). OFF ⇒ the
    # synchronous extract_pass2 path is unchanged. Wired by WX-T3 (the decoupled
    # orchestrator + an llm_job_terminal consumer); WX-T1/T2 are additive scaffolding
    # + the SDK pure-seam refactor that leave this dormant.
    extraction_decouple_enabled: bool = False

    # Unified Job Control Plane P1 — flip the decoupled-extraction terminal consumer onto
    # the shared loreweave_jobs.BaseTerminalConsumer (ExtractTerminalConsumer). Default
    # FALSE = the proven functional consume_llm_terminal_stream (money-path fallback); set
    # TRUE only after a live extraction E2E confirms the migrated path (no double-spend).
    extraction_consumer_use_sdk: bool = False

    # WX Wave 1b — stuck-resume sweeper. The decoupled finalize is a STRICT tx (no
    # best-effort fallback) and a Redis stream gives no redelivery after ack, so a
    # consumer crash/poison or a submit→persist gap can strand an extraction_jobs row
    # with resume_state set + no runtime recovery. This periodic loop re-drives any
    # such row idle longer than the timeout by re-checking each in-flight
    # provider_job_id's terminal status and replaying the consumer's idempotent
    # `_resume`. Only runs when the decouple flag is on. interval 0 ⇒ off.
    extraction_resume_sweep_interval_s: int = 60
    extraction_resume_sweep_timeout_s: int = 900
    extraction_resume_sweep_batch: int = 20

    # D-EXTRACTION-SILENT-NOOP gap #3 — generic STALL backstop. The resume-sweeper
    # above only re-drives DECOUPLED rows with resume_state (+ it's off by default);
    # a NON-decoupled job whose runner/provider died mid-loop sits 'running' forever,
    # looking healthy. This catch-all fails a job with NO progress (updated_at is
    # bumped on every cursor advance / stage / count change) for this many minutes.
    # Generous (> the 15-min resume timeout) so a recoverable row is re-driven first
    # and a long-but-live LLM call isn't wrongly failed. 0 ⇒ off.
    extraction_stall_minutes: int = 30

    # Max items to process per poll cycle before re-checking job status.
    # Lower = more responsive to pause/cancel, higher = less DB overhead.
    items_per_status_check: int = 1

    # ── P3 D-P3-WORKER-AI-CONSUMER-WIRING ──────────────────────────
    # Redis Stream consumer for the extraction.summarize job feed.
    # When `summary_consumer_enabled=False` the consumer task does not
    # start (useful for local dev without Redis OR rolling stack ups
    # where summarize-message can't yet be served).
    redis_url: str = "redis://redis:6379"
    summary_consumer_enabled: bool = True
    summary_consumer_group: str = "worker-ai-summarize"
    summary_consumer_name: str = "worker-ai-1"

    # A1 / P-10 — the assistant.distill ("End my day") consumer.
    distill_consumer_enabled: bool = True
    distill_consumer_group: str = "worker-ai-distill"
    distill_consumer_name: str = "worker-ai-1"
    # XREADGROUP BLOCK timeout (ms). Short enough to react to shutdown
    # promptly; long enough to avoid CPU spin when idle.
    summary_consumer_block_ms: int = 5000
    # Per-dispatch HTTP timeout for the knowledge-service summarize-
    # message endpoint. Summary processing is one LLM call + one embed
    # + Postgres + Neo4j writes — minutes worst-case on a cold model.
    summary_dispatch_timeout_s: float = 300.0

    log_level: str = "INFO"

    # ── Cycle 73h D-WORKER-AI-METRICS-INFRA ────────────────────────
    # Prometheus /metrics scrape endpoint. Worker-ai has no FastAPI
    # surface; metrics live on a dedicated port served by the
    # prometheus_client built-in WSGI server (daemon thread). Set to
    # 0 to disable (tests + dev runs without Prometheus).
    metrics_port: int = 8094


settings = Settings()
