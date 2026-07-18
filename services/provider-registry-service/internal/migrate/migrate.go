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
-- Drop CHECK constraints to allow any provider_kind string. platform_models is
-- created further below in this same script (CREATE TABLE IF NOT EXISTS
-- platform_models) — its DROP CONSTRAINT is deferred to right after that
-- CREATE (not here) because this whole schemaSQL string replays in order on
-- every startup with no per-statement version tracking (see the 'vision'
-- CHECK note further down): on a genuinely fresh database this ALTER used to
-- run before platform_models existed, aborting the entire migration with
-- "relation platform_models does not exist" and leaving EVERY later
-- CREATE TABLE in this script un-applied (found 2026-07-08 bootstrapping a
-- throwaway test DB — every long-lived dev/prod DB masked this because
-- platform_models has existed in them since before this ALTER was added).
ALTER TABLE provider_credentials DROP CONSTRAINT IF EXISTS provider_credentials_provider_kind_check;
ALTER TABLE user_models DROP CONSTRAINT IF EXISTS user_models_provider_kind_check;
-- api_standard: which API protocol this provider speaks (openai_compatible, anthropic, ollama, lm_studio)
ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS api_standard TEXT NOT NULL DEFAULT 'openai_compatible';

-- D-PROVIDER-CONCURRENCY-CONFIG: per-credential concurrency cap. NULL = unlimited
-- (request-as-demand; the infra is the limiter). The user sets this ONLY when they
-- know their own backend's limit (e.g. a local GPU that can run N calls at once).
-- Replaces the old hardcoded per-kind cap (local→1, cloud→GOVERNOR_CLOUD_MAX): a
-- provider's capacity is a property of THAT credential's backend, not its kind.
ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS max_concurrency INT;

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
-- v3 (moved here, see the note above): now that platform_models exists, allow
-- any provider_kind string on it too, matching provider_credentials/user_models.
ALTER TABLE platform_models DROP CONSTRAINT IF EXISTS platform_models_provider_kind_check;

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
    'video_gen', -- Phase 5d
    'audio_gen', -- Phase 5e-β.2
    'entity_extraction','relation_extraction','event_extraction',
    'fact_extraction', -- Phase 4a-β
    'summarize_level', -- P3 hierarchical reduce
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
--
-- INVARIANT (session 67 cont.5 lesson): every ALTER block below MUST
-- list the FULL union of ops added by ALL later blocks too. Postgres
-- validates ADD CONSTRAINT against EXISTING rows — if a later cycle
-- added a row with an op not in this earlier block's list, this
-- ALTER fails and the whole migration aborts. The crash loop is
-- "migrate: ERROR: check constraint llm_jobs_operation_check ...
-- is violated by some row (SQLSTATE 23514)" + provider-registry
-- refuses to start. Memory anchor: cross-cutting enum sync.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen',
  'video_gen','audio_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','summarize_level','translation','vision'
));

-- Phase 5d: drop + recreate operation CHECK to add video_gen.
-- Same idempotent pattern as Phase 4a-β.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen','video_gen',
  'audio_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','summarize_level','translation','vision'
));

-- Phase 5e-β.2: drop + recreate operation CHECK to add audio_gen.
-- Same idempotent pattern.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen','video_gen','audio_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','summarize_level','translation','vision'
));

-- P3 (D-P3-EXTRACTION-CALLER-WIRE-UP): drop + recreate operation CHECK
-- to add summarize_level. Per the cross-cutting-enum lesson —
-- live-smoke caught this — production INSERT would fail with check
-- violation despite the validJobOperations map already accepting it.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen','video_gen','audio_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','summarize_level','translation','vision'
));

-- Phase 6a Subsystem A — USD spend guardrail. The estimator reads a per-model
-- pricing JSONB (dimensions: input_per_mtok, output_per_mtok, per_image,
-- per_second, per_kchar) to compute a worst-case cost upper bound pre-flight.
-- An empty '{}' is the fail-closed default: a model with no pricing is
-- unpriced and its jobs are rejected 402, never billed as free.
-- See docs/03_planning/LLM_PIPELINE_PHASE6A_DESIGN.md §3.2.
ALTER TABLE user_models     ADD COLUMN IF NOT EXISTS pricing JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE platform_models ADD COLUMN IF NOT EXISTS pricing JSONB NOT NULL DEFAULT '{}'::jsonb;
-- The spend reservation held in usage-billing for this job's pre-flight
-- estimate; the worker reconciles/releases it on terminal state. NULL for
-- jobs created before this migration.
ALTER TABLE llm_jobs ADD COLUMN IF NOT EXISTS reservation_id UUID;

-- S4b (Auto-Draft Factory, decision C) — transactional usage outbox. On a
-- COMPLETED job the worker writes one row HERE in the same tx as the llm_jobs
-- finalize, then a relay XADDs it to loreweave:events:usage (all) +
-- loreweave:events:campaign_usage (when campaign_id is set) and stamps
-- published_at. Replaces the fire-and-forget RecordUsage HTTP on the jobs path:
-- at-least-once delivery, consumers dedup on request_id (= job_id).
CREATE TABLE IF NOT EXISTS usage_outbox (
  id             BIGSERIAL PRIMARY KEY,
  request_id     UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  campaign_id    UUID,
  model_source   TEXT NOT NULL,
  model_ref      UUID NOT NULL,
  operation      TEXT NOT NULL,
  input_tokens   INT  NOT NULL,
  output_tokens  INT  NOT NULL,
  cost_usd       NUMERIC(16,8),
  published_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_outbox_unpublished
  ON usage_outbox(id) WHERE published_at IS NULL;

-- Public MCP P3 (H-C/PUB-11) — per-key spend attribution. A job that originated at
-- the public MCP edge carries job_meta.mcp_key_id; FinalizeWithUsageOutbox stamps it
-- here so it rides the usage stream → usage-billing usage_logs. NULL for first-party.
ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS mcp_key_id UUID;

-- LLM re-arch Phase 1 — transactional terminal-event outbox. On EVERY terminal
-- transition (completed|failed|cancelled) the worker (and the cancel handler)
-- writes one row HERE in the same tx as the llm_jobs finalize; a relay XADDs it
-- to loreweave:events:llm_job_terminal and stamps published_at. This is the
-- durable, per-job-correlated completion signal a caller resumes on (the SDK
-- event adapter + future service consumers). Mirrors usage_outbox: at-least-once
-- delivery, consumers dedup on job_id. result_ref = job_id (consumer fetches the
-- full result via GET /internal/llm/jobs/{id}); the event carries only the
-- correlation + summary so the stream stays light.
CREATE TABLE IF NOT EXISTS job_event_outbox (
  id             BIGSERIAL PRIMARY KEY,
  job_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  operation      TEXT NOT NULL,
  status         TEXT NOT NULL,
  kind           TEXT NOT NULL DEFAULT '',
  cost_usd       NUMERIC(16,8),
  error_code     TEXT,
  error_message  TEXT,
  campaign_id    UUID,
  correlation_id TEXT,
  published_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_job_event_outbox_unpublished
  ON job_event_outbox(id) WHERE published_at IS NULL;

-- Per-user DEFAULT model for a capability (rerank/embedding/...). Restores the
-- BYOK default-model UX that the removed RERANK_URL/_MODEL .env config provided
-- (D-RERANK-NOT-BYOK): the default is the user's own user_model, never platform
-- config. One row per (user, capability); the user_model FK cascades a clear when
-- the model is deleted. Consumers resolve via GET /internal/default-models/{cap}.
CREATE TABLE IF NOT EXISTS user_default_models (
  owner_user_id  UUID NOT NULL,
  capability     TEXT NOT NULL,
  user_model_id  UUID NOT NULL REFERENCES user_models(user_model_id) ON DELETE CASCADE,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, capability)
);

-- S-SETTINGS (MCP fan-out) — single-use ledger for the Tier-W settings.model_delete
-- confirm token. The confirm route records the token's hash here on first redeem;
-- a replay hits the PK (ON CONFLICT DO NOTHING → 0 rows) and is rejected. The
-- stateless kit confirm token has no jti, so we key on the token-hash. exp lets a
-- future sweeper prune expired rows.
CREATE TABLE IF NOT EXISTS settings_consumed_tokens (
  token_hash  TEXT PRIMARY KEY,
  descriptor  TEXT NOT NULL,
  exp         TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_settings_consumed_tokens_exp ON settings_consumed_tokens(exp);

-- #32 — full LLM-call logging. The usage_outbox now carries (1) request_status so the
-- billing audit records EVERY terminal status (not just completed — failed/cancelled get
-- a cost-0 audit row) and (2) the truncated request/response payloads so a call can be
-- traced/reproduced. usage-billing's writeUsageLog already encrypts + audited-decrypts
-- these (input_payload_ciphertext/output_payload_ciphertext); this carries them through
-- the worker→outbox→relay→consumer plumbing. Nullable: legacy/unpopulated rows stay valid.
ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS request_status   TEXT;
ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS request_payload  TEXT;
ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS response_payload TEXT;

-- (8)-residual — user-defined custom SORT ORDER for models, persisted so the
-- shared ModelPicker's drag-reorder survives across devices (server SSOT, not
-- localStorage). NULL = unordered: an explicit order wins, and un-ordered models
-- sort AFTER the ordered ones (NULLS LAST), falling back to favorites-first. The
-- PUT /user-models/reorder route assigns 0..N-1 to the provided ids and NULLs the
-- rest so a partial reorder is well-defined.
ALTER TABLE user_models ADD COLUMN IF NOT EXISTS sort_order INTEGER;

-- PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md L5): drop +
-- recreate operation CHECK to add 'vision'. Same idempotent pattern as the
-- prior additions — the cross-cutting-enum lesson (validJobOperations map +
-- this CHECK + openapi.yaml enum must all agree, or INSERT fails 23514
-- despite the handler already accepting the operation).
--
-- /review-impl 2026-07-06 (fixed a self-inflicted instance of the exact
-- crash-loop the invariant comment above (line 164) warns about): adding
-- 'vision' ONLY to this final block and not backfilling it into the 4
-- earlier blocks above crashed provider-registry on next restart the
-- moment a real 'vision' row existed — Postgres validates each ADD
-- CONSTRAINT against ALL EXISTING ROWS as the full schemaSQL string
-- replays in order on every startup (no per-statement version tracking),
-- so an earlier block whose list predates 'vision' fails outright once
-- such a row exists. Fixed by adding 'vision' to all 5 blocks. The NEXT
-- new operation added here MUST do the same to every block above it, not
-- just append a new one at the end.
ALTER TABLE llm_jobs DROP CONSTRAINT IF EXISTS llm_jobs_operation_check;
ALTER TABLE llm_jobs ADD CONSTRAINT llm_jobs_operation_check CHECK (operation IN (
  'chat','completion','embedding','stt','tts','image_gen','video_gen','audio_gen',
  'entity_extraction','relation_extraction','event_extraction',
  'fact_extraction','summarize_level','translation','vision'
));
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
