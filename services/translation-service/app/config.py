from pydantic_settings import BaseSettings

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator. "
    "Your goal is to accurately convey the meaning and nuances of the original {source_lang} text "
    "while adhering to {target_lang} grammar, vocabulary, and cultural sensitivities. "
    "Produce only the {target_lang} translation, without any additional explanations or commentary."
)
DEFAULT_USER_PROMPT_TPL = (
    "Please translate the following {source_lang} ({source_code}) text "
    "into {target_lang} ({target_code}):\n\n{chapter_text}"
)

DEFAULT_COMPACT_SYSTEM_PROMPT = (
    "You are a translation assistant. Summarise the following translation session history "
    "into a concise Translation Memo (200 words max). Include: key character names and "
    "their translations, recurring terminology, tone/style notes. "
    "Output ONLY the memo, no other text."
)
DEFAULT_COMPACT_USER_PROMPT_TPL = "{history_text}"


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    book_service_internal_url: str = "http://book-service:8082"
    # Phase 4c-α: legacy URL used by remaining /v1/model-registry/invoke
    # + /internal/invoke callers (4c-β/γ migrate them out).
    provider_registry_service_url: str = "http://provider-registry-service:8085"
    # Phase 4c-α: SDK install. Same host as legacy URL — naming aligns
    # with knowledge-service + worker-ai for cross-service consistency.
    # When 4c-γ retires the last legacy caller, we'll drop the legacy
    # field and consolidate.
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    glossary_service_internal_url: str = "http://glossary-service:8088"
    # M4a: knowledge-service for the V3 knowledge layer (relations → pronoun/
    # honorific context). Empty by default = feature off (Null port): the client
    # degrades to an empty neighbourhood and makes no HTTP call. Set in the live
    # stack to enable. Internal-token auth (shared internal_service_token).
    knowledge_service_internal_url: str = ""
    rabbitmq_url: str
    # M5c: Redis Streams — consume glossary change events to flag stale translations.
    redis_url: str = "redis://redis:6379"
    notification_service_internal_url: str = "http://notification-service:8091"
    internal_service_token: str
    # MCP fan-out S-TRANSL (key-split, /review-impl): the confirm-token signing
    # secret is DEDICATED — distinct from `internal_service_token` (which gates the
    # X-Internal-Token route/envelope). Splitting the keys means a leak of one does
    # not forge the other: the envelope token proves "trusted caller", the confirm
    # secret proves "this exact priced action was proposed". Fail-closed: required,
    # no default — the service refuses to start unless CONFIRM_TOKEN_SIGNING_SECRET
    # is set (an unsigned/shared-secret confirm token is a money-path defect).
    confirm_token_signing_secret: str
    port: int = 8087
    # M7d-3: opt-in feed of source+translated text into the translation.quality
    # event so the M7d-2 online fidelity judge has inputs to score. OFF by default
    # — when off, the event payload is byte-identical to M7a (no extra cost, no
    # text shipped). INDEPENDENT of learning's online_translation_judge_enabled
    # (the consumer-side gate): both must be on for a judge to actually run, so
    # turning the feed on alone is harmless. Truncate each side to bound the
    # event-bus payload — a head-sample is enough for a fidelity judgment.
    translation_judge_feed_enabled: bool = False
    translation_judge_feed_max_chars: int = 2000
    # LLM re-arch Phase 2b-T2: opt-in event-driven decouple of the v2 TEXT path.
    # OFF ⇒ the synchronous session_translator path is unchanged. ON ⇒ the worker
    # submits the first chunk + releases; the llm_terminal_consumer resumes on each
    # `loreweave:events:llm_job_terminal` and finalizes (so a worker coroutine isn't
    # pinned for the whole chapter). Block + V3 decouple = 2b-T3 (still synchronous
    # under this flag for now).
    translation_decouple_enabled: bool = False

    # Wave 2a (D-2B-SUBMIT-PERSIST-GAP) — stuck-resume sweeper (parity with worker-ai
    # Wave 1b). A Redis stream gives no redelivery after ack, so a consumer crash/poison,
    # a lost terminal event, or a submit→persist gap can strand a chapter_translations
    # row with resume_state set. This periodic loop re-drives any such row idle past the
    # timeout by re-checking its provider_job_id's terminal status and replaying the
    # consumer's idempotent resume dispatch. Only runs when the decouple flag is on.
    translation_resume_sweep_interval_s: int = 60
    translation_resume_sweep_timeout_s: int = 900
    translation_resume_sweep_batch: int = 20

    # P5 — fair scheduling (per-tenant WFQ via loreweave_jobs.FairScheduler). OFF by
    # default: the coordinator publishes chapter messages directly (legacy path) and no
    # dispatcher runs. ON ⇒ the coordinator ENQUEUEs chapter units into the per-owner
    # WFQ; the dispatcher loop releases them round-robin (≤ p5_owner_cap in-flight per
    # owner, ≤ p5_global_budget total) → publishes translation.chapter; the chapter
    # worker releases the lease on terminal. Stops one owner's giant job from
    # monopolizing the fleet. Lane = "translation:chapter".
    p5_sched_enabled: bool = False
    p5_owner_cap: int = 5
    p5_global_budget: int = 0  # 0 ⇒ unlimited (per-owner cap is then the only limit)
    p5_lease_ttl_ms: int = 3_600_000  # crash-leak backstop; must exceed a chapter's runtime
    p5_dispatch_interval_s: float = 0.5  # dispatcher tick (latency to first dispatch)
    p5_reclaim_interval_s: int = 60  # periodic expired-lease self-heal

    # ── MCP fan-out S-TRANSL: cost-estimate (HIGH#1) + re-price-at-execution (H14) ──
    # Output:input token ratio for the translation cost projection. A translation's
    # output is roughly the same length as its source (sometimes a touch longer in
    # a target language). 1.0 is a faithful neutral projection; tune per deployment
    # without touching code. NOT a model/price literal (those resolve from
    # provider-registry) — only a workload shape heuristic, so it does NOT trip the
    # ai-provider-gate.
    transl_estimate_output_ratio: float = 1.0
    # H14 re-price-at-execution thresholds. Before a confirmed Tier-W job actually
    # runs, re-price the SAME scope; if the fresh estimate exceeds BOTH a relative
    # AND an absolute floor over the confirmed estimate, refuse and signal a
    # re-confirm rather than silently overspending. "exceeds est×1.25 OR est+$0.50"
    # (the design's H14) — i.e. trip when actual > est*mult OR actual > est+abs.
    transl_reprice_mult: float = 1.25
    transl_reprice_abs_usd: float = 0.50

    class Config:
        env_file = ".env"


settings = Settings()
