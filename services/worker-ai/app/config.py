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

    # Timeouts (seconds).
    extract_item_timeout_s: float = 120.0  # LLM calls are slow
    book_client_timeout_s: float = 10.0

    # Poll interval (seconds) — how often to check for running jobs.
    poll_interval_s: float = 5.0

    # Max items to process per poll cycle before re-checking job status.
    # Lower = more responsive to pause/cancel, higher = less DB overhead.
    items_per_status_check: int = 1

    log_level: str = "INFO"


settings = Settings()
