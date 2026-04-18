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

    # K5 — knowledge-service integration. Optional/tunable via env so we can
    # raise the timeout if knowledge-service ever becomes a real bottleneck.
    knowledge_service_url: str = "http://knowledge-service:8092"
    knowledge_client_timeout_s: float = 0.5      # 500ms total per Track1 doc
    knowledge_client_retries: int = 1            # one retry on 5xx/transport

    # D-T2-03 — degraded-mode fallback when knowledge-service is unreachable
    # or returns an error. Must agree with knowledge-service's Mode 1 + Mode 2
    # `recent_message_count` (which also defaults to 50). Both services read
    # env var RECENT_MESSAGE_COUNT so a tune stays in sync.
    recent_message_count: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
