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
    # Q4 — online-eval sampler (eval-runner consumer group). Master switch;
    # the sampling rate itself lives in the online_eval_rule table.
    online_eval_enabled: bool = True

    # Q4b — online LLM-as-judge. When a sampled run carries items + source text
    # (opted-in projects) AND a rule has a judge panel, the eval-runner judges
    # the extraction via provider-registry. Off by default (needs a judge model).
    provider_registry_internal_url: str = "http://provider-registry:8208"
    online_judge_enabled: bool = False
    online_judge_model_ref: str = ""          # judge model UUID (BYOK user_model)
    online_judge_model_source: str = "user_model"
    online_judge_user_id: str = ""            # BYOK owner of the judge model

    class Config:
        env_file = ".env"


settings = Settings()
