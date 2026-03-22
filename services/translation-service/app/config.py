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
