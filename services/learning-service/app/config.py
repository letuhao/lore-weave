from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """learning-service settings. Required fields with no default fail
    startup (no-hardcoded-secrets rule) — `learning_db_url`, `jwt_secret`,
    `internal_service_token`."""

    learning_db_url: str
    jwt_secret: str
    internal_service_token: str
    redis_url: str = "redis://redis:6379"
    port: int = 8094

    class Config:
        env_file = ".env"


settings = Settings()
