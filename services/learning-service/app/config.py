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
    # In-cluster S2S URL = container DNS name + container port (matches
    # knowledge-service). The prior default (`provider-registry:8208`) resolved
    # to nothing — every online LLM judge (translation-fidelity M7d-2 + extraction)
    # silently no-op'd (verdict None) because the call never reached the gateway.
    # Caught by D-S5BEVAL-LIVE-SMOKE (2026-06-10).
    provider_registry_internal_url: str = "http://provider-registry-service:8085"
    online_judge_enabled: bool = False
    online_judge_model_ref: str = ""          # judge model UUID (BYOK user_model)
    online_judge_model_source: str = "user_model"
    # D-EVAL-JUDGE-PER-USER: FALLBACK only. The judge now bills the CONTENT
    # OWNER (the event/run's user_id); this env id is used solely when an event
    # carries no owner. Leave empty in multi-tenant deployments.
    online_judge_user_id: str = ""
    # M7d — online translation-fidelity judge (reuses the judge model above).
    # Off by default; runs only when a translation.quality event carries the
    # source+translated text (the M7d-3 worker feed, itself off by default).
    online_translation_judge_enabled: bool = False
    # Q4b-feed — knowledge-service internal base URL. The eval-runner fetches
    # the run's items+source sample from here (GET /internal/extraction/runs/
    # {run_id}/sample) for opted-in runs, then feeds the online judge.
    knowledge_internal_url: str = "http://knowledge-service:8092"

    # D-WIKI-M8-LEARNING-CONSUMER — collect the wiki feedback flywheel signal
    # (wiki.corrected → corrections, wiki.suggestion_reviewed → quality_scores,
    # target='wiki_article'). ON by default: the collect is cheap (DB writes from
    # events already on the stream). The expensive LLM-judge scoring of wiki articles
    # is a separate, off-by-default follow-up (D-WIKI-M8-EVAL-PLUS). Flip this off to
    # stop recording the wiki signal entirely. NOTE: this is a collect on/off, not a
    # pause — events arriving while it is off are acked WITHOUT a row (not buffered or
    # replayable); flipping it back on resumes collection from new events only.
    wiki_learning_enabled: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
