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
    # C12c-a: glossary-service URL for the paginated entity list the
    # scope='glossary_sync' worker branch iterates.
    glossary_service_url: str = "http://glossary-service:8082"
    # Phase 4b-γ: provider-registry's internal LLM gateway. Worker-ai
    # calls submit_job through the loreweave_llm SDK; the SDK posts
    # to this base URL with the X-Internal-Token header.
    provider_registry_internal_url: str = "http://provider-registry-service:8085"

    # Timeouts (seconds).
    # Phase 4b-γ: extract_item_timeout_s is now used ONLY for the thin
    # persist-pass2 HTTP call (Neo4j write — fast, bounded). The LLM
    # wait happens inside the SDK's wait_terminal poll loop, which has
    # no overall timeout (gateway controls per-job lifetime).
    persist_pass2_timeout_s: float = 30.0  # Neo4j writes are seconds, not minutes
    extract_item_timeout_s: float = 120.0  # back-compat — to be removed in Phase 4d
    book_client_timeout_s: float = 10.0
    # C12c-a: glossary list is cheap pagination (no LLM) — shorter
    # timeout than the book client's chapter fetch.
    glossary_client_timeout_s: float = 10.0

    # Poll interval (seconds) — how often to check for running jobs.
    poll_interval_s: float = 5.0

    # Max items to process per poll cycle before re-checking job status.
    # Lower = more responsive to pause/cancel, higher = less DB overhead.
    items_per_status_check: int = 1

    log_level: str = "INFO"


settings = Settings()
