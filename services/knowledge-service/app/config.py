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

    # D-T2-03 — Mode 1 + Mode 2 `recent_message_count` returned in the
    # context response. chat-service replays the last N messages of the
    # session when this many are requested. PAIR: chat-service's
    # `settings.recent_message_count` has the same default; both read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync. Mode 3 has
    # its own tighter constant (20) in full.py — by design.
    recent_message_count: int = 50

    # K6.1 — per-layer timeouts inside the context builder. If any
    # layer exceeds its budget the builder skips that layer and
    # continues with the remaining pieces. Total ceiling defaults to
    # L0 + L1 + glossary = 400ms because layers run sequentially.
    context_l0_timeout_s: float = 0.1
    context_l1_timeout_s: float = 0.1
    context_glossary_timeout_s: float = 0.2
    # K18.1 — Mode 3 L2 fact selector budget. Neo4j 1-hop + optional
    # 2-hop + negation listing. Tighter than glossary because the L2
    # queries run against an indexed graph, not an HTTP service.
    context_l2_timeout_s: float = 0.3
    # K18.3 — Mode 3 L3 passage selector budget. Embed(1 text) via
    # provider-registry + Neo4j vector query + MMR. The embed call
    # dominates; 2s leaves headroom for local LM Studio on small
    # chunks while still capping a pathologically slow cloud model.
    context_l3_timeout_s: float = 2.0
    # K18.7 — Mode 3 memory-block token budget. The full L0+L1+glossary
    # +facts+passages+absences payload can easily exceed useful limits
    # on a small-context model. When over budget, the Mode 3 builder
    # drops in reverse-priority order: passages (lowest score first)
    # → absences → background facts → glossary trimmed. L0, project
    # instructions, L1 summary, negative facts, and the CoT
    # instructions block are protected.
    mode3_token_budget: int = 6000

    # K16.2 — book-service HTTP client for chapter counts in cost estimation.
    book_service_url: str = "http://book-service:8082"
    book_client_timeout_s: float = 5.0

    # K17.2 — provider-registry BYOK client for LLM extraction calls.
    # Calls provider-registry's /internal/proxy/v1/chat/completions
    # endpoint, which resolves the user's BYOK model from
    # (user_id, model_source, model_ref) and forwards to the upstream
    # provider with credentials injected server-side. Knowledge-service
    # never sees the provider API key.
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    # LLMs are slow. 60s is the plan-row budget; extractors that need
    # longer should split their work rather than raise this.
    provider_client_timeout_s: float = 60.0

    # K11.2 — Neo4j connection (Track 2 extraction graph). Empty
    # `neo4j_uri` means "skip Neo4j init at startup" — Track 1 dev
    # keeps working without Neo4j running. Set to e.g.
    # bolt://neo4j:7687 to enable. When set, the lifespan hook
    # fail-fasts on unreachable Neo4j (per the K11.2 spec).
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = "loreweave_dev_neo4j"
    # Driver-level connection acquisition timeout. Short on
    # purpose so a misconfigured URI fails the startup check
    # within ~5s rather than hanging the container.
    neo4j_connection_timeout_s: float = 5.0


settings = Settings()
