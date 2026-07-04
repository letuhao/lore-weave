from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    usage_billing_service_url: str = "http://usage-billing-service:8086"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "loreweave"
    minio_secret_key: str
    minio_bucket: str = "lw-chat"
    minio_use_ssl: bool = False
    minio_external_url: str = ""  # Browser-accessible MinIO URL for presigned URLs
    audio_ttl_hours: int = 48         # Voice audio retention period
    audio_cleanup_interval_hours: int = 4  # How often to run cleanup
    internal_service_token: str
    statistics_service_internal_url: str = "http://statistics-service:8089"
    redis_url: str = "redis://redis:6379"
    port: int = 8090

    # LLM streaming idle-read timeout (seconds) — the longest SILENT gap between
    # SSE frames before the stream is treated as stalled. Default 0 = UNBOUNDED
    # (no cap): a slow reasoning model may think silently for minutes before its
    # first token, and an idle cap would ReadTimeout mid-thought (as Gemma-4 26B
    # at high effort did). Set a positive value (env LLM_STREAM_IDLE_READ_TIMEOUT_S,
    # e.g. 300) to cap it. The SDK Client honours <=0 as read=None.
    llm_stream_idle_read_timeout_s: float = 0.0

    # K5 — knowledge-service integration. Optional/tunable via env so we can
    # raise the timeout if knowledge-service ever becomes a real bottleneck.
    knowledge_service_url: str = "http://knowledge-service:8092"
    knowledge_client_timeout_s: float = 0.5      # 500ms total per Track1 doc
    knowledge_client_retries: int = 1            # one retry on 5xx/transport
    # K21-B — execute_tool runs a real memory tool (memory_remember does
    # injection-neutralisation + a Neo4j write) and routinely exceeds the
    # build_context budget above. Tool execution gets its own, longer
    # per-call timeout so a slow write doesn't ReadTimeout (D-K21B-06).
    knowledge_tool_timeout_s: float = 30.0

    # ai-gateway P0 (2026-06-10) — TOOLS now go through the ai-gateway (MCP
    # federation), NOT knowledge directly. Hard cutover: tool definitions + MCP
    # execution target this URL; build_context (grounding) STAYS on
    # knowledge_service_url (gateway grounding is P6, not P0).
    ai_gateway_url: str = "http://ai-gateway:8210"

    # RAID C1 (DR-C1) — per-book steering. book-service serves the enabled
    # entries via GET /internal/books/{id}/steering; failures degrade to []
    # (the turn proceeds steering-free), so the timeout stays tight.
    book_service_url: str = "http://book-service:8082"
    book_steering_timeout_s: float = 2.0

    # T5 (Context Budget Law D2) — entity-presence intent gate. chat-service reads
    # the book's known-entity token set from glossary-service's internal route and
    # caches it in-process (A3: no new table). Used ONLY to decide whether a turn's
    # message references book lore → whether the expensive grounding pull is worth
    # it. Failure degrades to "gate open" (bias-to-include), so the turn is never
    # harmed by a glossary outage.
    glossary_service_url: str = "http://glossary-service:8088"
    known_entities_timeout_s: float = 2.0
    known_entities_cache_ttl_s: float = 300.0
    # T5 kill-switch. False ⇒ grounding is ALWAYS pulled (pre-T5 behavior) — the
    # baseline arm of the quality-gate A/B, and the escape hatch if the gate ever
    # regresses answer-correctness in production. Default True (the gate is on).
    t5_intent_gate_enabled: bool = True

    # Agent Extensibility Registry (P1) — user/book prompt-only skills. chat-service
    # reads /internal/skills and injects them alongside the built-in SYSTEM_SKILLS,
    # honouring per-user disable + shadow. EVERY failure degrades to "constants only"
    # (the built-in skills still work), so a registry outage never breaks a turn.
    agent_registry_url: str = "http://agent-registry-service:8099"
    agent_registry_timeout_s: float = 2.0

    # ARCH-1 C3 — default stream event format when a request sends no
    # x-loreweave-stream-format header. "legacy" (LoreWeave SSE vocabulary) or
    # "agui" (AG-UI protocol). Per-request header overrides this; the default
    # stays "legacy" until the AG-UI frontend (C4) ships.
    default_stream_format: str = "legacy"

    # D-T2-03 — degraded-mode fallback when knowledge-service is unreachable
    # or returns an error. Must agree with knowledge-service's Mode 1 + Mode 2
    # `recent_message_count` (which also defaults to 50). Both services read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync.
    recent_message_count: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
