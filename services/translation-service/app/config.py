from pydantic_settings import BaseSettings

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional literary translator. "
    "Preserve the style, tone, pacing, and voice of the original text. "
    "Do not add commentary, explanations, or translator notes. "
    "Translate faithfully and naturally."
)
DEFAULT_USER_PROMPT_TPL = (
    "Translate the following {source_language} text into {target_language}. "
    "Output only the translated text, nothing else.\n\n{chapter_text}"
)


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    book_service_internal_url: str = "http://book-service:8082"
    provider_registry_service_url: str = "http://provider-registry-service:8085"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    port: int = 8087

    class Config:
        env_file = ".env"


settings = Settings()
