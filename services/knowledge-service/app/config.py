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


settings = Settings()
