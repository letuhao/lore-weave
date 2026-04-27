package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS provider_credentials (
  provider_credential_id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  provider_kind TEXT NOT NULL CHECK (provider_kind IN ('openai','anthropic','ollama','lm_studio')),
  display_name TEXT NOT NULL,
  endpoint_base_url TEXT,
  secret_ciphertext TEXT,
  secret_key_ref TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','invalid','disabled','archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_provider_credentials_owner ON provider_credentials(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_provider_credentials_owner_kind ON provider_credentials(owner_user_id, provider_kind);

CREATE TABLE IF NOT EXISTS provider_inventory_models (
  provider_inventory_model_id UUID PRIMARY KEY DEFAULT uuidv7(),
  provider_credential_id UUID NOT NULL REFERENCES provider_credentials(provider_credential_id) ON DELETE CASCADE,
  provider_model_name TEXT NOT NULL,
  context_length INT,
  capability_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(provider_credential_id, provider_model_name)
);

CREATE TABLE IF NOT EXISTS user_models (
  user_model_id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  provider_credential_id UUID NOT NULL REFERENCES provider_credentials(provider_credential_id) ON DELETE CASCADE,
  provider_kind TEXT NOT NULL CHECK (provider_kind IN ('openai','anthropic','ollama','lm_studio')),
  provider_model_name TEXT NOT NULL,
  context_length INT,
  alias TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  is_favorite BOOLEAN NOT NULL DEFAULT false,
  capability_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_models_owner ON user_models(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_user_models_owner_flags ON user_models(owner_user_id, is_active, is_favorite);

-- v2: notes field for user annotations on models
ALTER TABLE user_models ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

-- v3: support custom providers + api_standard
-- Drop CHECK constraints to allow any provider_kind string
ALTER TABLE provider_credentials DROP CONSTRAINT IF EXISTS provider_credentials_provider_kind_check;
ALTER TABLE user_models DROP CONSTRAINT IF EXISTS user_models_provider_kind_check;
ALTER TABLE platform_models DROP CONSTRAINT IF EXISTS platform_models_provider_kind_check;
-- api_standard: which API protocol this provider speaks (openai_compatible, anthropic, ollama, lm_studio)
ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS api_standard TEXT NOT NULL DEFAULT 'openai_compatible';

CREATE TABLE IF NOT EXISTS user_model_tags (
  user_model_tag_id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_model_id UUID NOT NULL REFERENCES user_models(user_model_id) ON DELETE CASCADE,
  tag_name TEXT NOT NULL,
  note TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_model_tags_unique ON user_model_tags(user_model_id, tag_name);

CREATE TABLE IF NOT EXISTS platform_models (
  platform_model_id UUID PRIMARY KEY DEFAULT uuidv7(),
  provider_kind TEXT NOT NULL CHECK (provider_kind IN ('openai','anthropic','ollama','lm_studio')),
  provider_model_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','retired')),
  pricing_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
  quota_policy_ref TEXT,
  capability_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(provider_kind, provider_model_name)
);

-- Phase 2a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN): async LLM job state.
-- Single source of truth for jobs submitted via POST /v1/llm/jobs;
-- per-service business-job tables (extraction_jobs, translation_jobs)
-- will reference this row's job_id once Phase 4 migrations land.
--
-- Schema mirrors the openapi Job + SubmitJobRequest schemas in
-- contracts/api/llm-gateway/v1/openapi.yaml. Result retention defaults
-- to 7 days post-submission per Q8 of the refactor plan.
CREATE TABLE IF NOT EXISTS llm_jobs (
  job_id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN (
    'chat','completion','embedding','stt','tts','image_gen',
    'entity_extraction','relation_extraction','event_extraction',
    'fact_extraction', -- Phase 4a-β
    'translation'
  )),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending','running','completed','failed','cancelled'
  )),

  -- Request inputs (audited; immutable after submit).
  model_source TEXT NOT NULL CHECK (model_source IN ('user_model','platform_model')),
  model_ref UUID NOT NULL,
  input JSONB NOT NULL,
  chunking JSONB,
  callback JSONB,
  job_meta JSONB,
  trace_id TEXT,

  -- Progress tracking (mutated as job runs through Phase 3 chunk pool).
  chunks_total INT,
  chunks_done INT NOT NULL DEFAULT 0,
  tokens_used INT NOT NULL DEFAULT 0,
  last_progress_at TIMESTAMPTZ,

  -- Terminal state (populated when status moves to completed/failed/cancelled).
  result JSONB,
  error_code TEXT,
  error_message TEXT,
  finish_reason TEXT,

  -- Timestamps.
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,

  -- 7-day default retention (Q8). Phase 6 hardening adds a sweeper that
  -- deletes terminal rows past expires_at via the partial index below.
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),

  -- Lock the terminal-status ↔ completed_at invariant. Catches a row
  -- being marked terminal without setting completed_at (or vice versa).
  CONSTRAINT llm_jobs_terminal_consistency CHECK (
    (status IN ('completed','failed','cancelled')) = (completed_at IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_llm_jobs_owner ON llm_jobs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_llm_jobs_owner_status ON llm_jobs(owner_user_id, status);
-- Partial index supports the future Phase 6 retention sweeper without
-- bloating the index over still-running jobs.
CREATE INDEX IF NOT EXISTS idx_llm_jobs_expires_at ON llm_jobs(expires_at)
  WHERE status IN ('completed','failed','cancelled');

-- Phase 4a-β: drop + recreate operation CHECK to add fact_extraction.
-- CREATE TABLE IF NOT EXISTS doesn't update an existing constraint;
-- this ALTER is idempotent across cold + warm schemas.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','translation'
));
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
