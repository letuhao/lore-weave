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

    class Config:
        env_file = ".env"


settings = Settings()
