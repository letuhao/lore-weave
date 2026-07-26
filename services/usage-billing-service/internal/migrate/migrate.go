package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS usage_logs (
  usage_log_id UUID PRIMARY KEY DEFAULT uuidv7(),
  request_id UUID NOT NULL UNIQUE,
  owner_user_id UUID NOT NULL,
  provider_kind TEXT NOT NULL CHECK (provider_kind IN ('openai','anthropic','ollama','lm_studio')),
  model_source TEXT NOT NULL CHECK (model_source IN ('user_model','platform_model')),
  model_ref UUID NOT NULL,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  total_tokens INT NOT NULL DEFAULT 0,
  total_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
  billing_decision TEXT NOT NULL CHECK (billing_decision IN ('quota','credits','rejected')),
  request_status TEXT NOT NULL CHECK (request_status IN ('success','provider_error','billing_rejected')),
  policy_version TEXT NOT NULL DEFAULT 'm03-v1',
  input_payload_ciphertext TEXT,
  output_payload_ciphertext TEXT,
  payload_encryption_key_ref TEXT,
  payload_encryption_algo TEXT,
  decrypt_access_audit_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_logs_owner_created ON usage_logs(owner_user_id, created_at DESC);

-- v2: purpose column for usage categorization (translation, chat, chunk_edit, image_gen, etc.)
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'unknown';
CREATE INDEX IF NOT EXISTS idx_usage_logs_purpose ON usage_logs(owner_user_id, purpose);

CREATE TABLE IF NOT EXISTS usage_log_details (
  usage_log_id UUID PRIMARY KEY REFERENCES usage_logs(usage_log_id) ON DELETE CASCADE,
  payload_encryption_key_ciphertext TEXT NOT NULL,
  input_payload_ciphertext TEXT NOT NULL,
  output_payload_ciphertext TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_log_decrypt_audits (
  usage_log_decrypt_audit_id UUID PRIMARY KEY DEFAULT uuidv7(),
  usage_log_id UUID NOT NULL REFERENCES usage_logs(usage_log_id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL,
  viewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reconciliation_reports (
  report_id UUID PRIMARY KEY DEFAULT uuidv7(),
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  dry_run BOOLEAN NOT NULL DEFAULT true,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','completed','failed')),
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phase 6a Subsystem A — USD spend guardrail. Protects the user's wallet via
-- a per-user USD budget (daily + monthly calendar windows) enforced
-- pre-flight on every LLM job. See LLM_PIPELINE_PHASE6A_DESIGN.md.
CREATE TABLE IF NOT EXISTS spend_guardrails (
  owner_user_id        UUID PRIMARY KEY,
  daily_limit_usd      NUMERIC(16,8) NOT NULL,
  monthly_limit_usd    NUMERIC(16,8) NOT NULL,
  daily_spent_usd      NUMERIC(16,8) NOT NULL DEFAULT 0,
  monthly_spent_usd    NUMERIC(16,8) NOT NULL DEFAULT 0,
  reserved_usd         NUMERIC(16,8) NOT NULL DEFAULT 0,
  daily_window_date    DATE NOT NULL DEFAULT (now() AT TIME ZONE 'utc')::date,
  monthly_window_month DATE NOT NULL DEFAULT date_trunc('month', now() AT TIME ZONE 'utc')::date,
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS token_reservations (
  reservation_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id    UUID NOT NULL,
  job_id           UUID,
  estimated_usd    NUMERIC(16,8) NOT NULL,
  status           TEXT NOT NULL DEFAULT 'held'
                     CHECK (status IN ('held','reconciled','released','swept')),
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Sweeper scan: held reservations past expiry.
CREATE INDEX IF NOT EXISTS idx_token_reservations_sweep
  ON token_reservations(expires_at) WHERE status = 'held';
-- Reserve idempotency: at most one held reservation per job.
CREATE UNIQUE INDEX IF NOT EXISTS idx_token_reservations_job
  ON token_reservations(job_id) WHERE status = 'held' AND job_id IS NOT NULL;

-- Phase 6a-β Subsystem B — platform resale ledger. Tracks what a user owes
-- LoreWeave for LoreWeave-funded platform_model calls: a config-seeded free
-- tier (USD, lazy calendar-month reset) plus prepaid credits. A platform_model
-- job reserves against this ledger AND spend_guardrails; a user_model job
-- never touches it. See LLM_PIPELINE_PHASE6A_BETA_DESIGN.md §3.
CREATE TABLE IF NOT EXISTS platform_balances (
  owner_user_id           UUID PRIMARY KEY,
  free_tier_allowance_usd NUMERIC(16,8) NOT NULL,            -- config-seeded, never a DDL default
  free_tier_used_usd      NUMERIC(16,8) NOT NULL DEFAULT 0,
  free_tier_window_month  DATE NOT NULL DEFAULT date_trunc('month', now() AT TIME ZONE 'utc')::date,
  credits_balance_usd     NUMERIC(16,8) NOT NULL DEFAULT 0,
  reserved_usd            NUMERIC(16,8) NOT NULL DEFAULT 0,  -- sum of held platform reservations
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- token_reservations gains model_source so reconcile/release/sweep know
-- whether a reservation also moves platform_balances. DEFAULT 'user_model'
-- covers any pre-Phase-6a-β rows (none in prod — test/UAT only).
ALTER TABLE token_reservations
  ADD COLUMN IF NOT EXISTS model_source TEXT NOT NULL DEFAULT 'user_model';
ALTER TABLE token_reservations DROP CONSTRAINT IF EXISTS token_reservations_model_source_check;
ALTER TABLE token_reservations ADD CONSTRAINT token_reservations_model_source_check
  CHECK (model_source IN ('user_model','platform_model'));

-- Phase 6a-β — drop the stale usage_logs.provider_kind CHECK. It hardcoded
-- four providers; provider-registry's migrate v3 already dropped the
-- equivalent CHECK on its own tables to allow custom providers (gemini, …).
-- The unupdated copy here makes /record 500 for any other provider_kind
-- (including the empty string book-service posts) — see PHASE6A_BETA_DESIGN.
ALTER TABLE usage_logs DROP CONSTRAINT IF EXISTS usage_logs_provider_kind_check;

-- S4c — the usage-audit stream consumer writes billing_decision='recorded' (the
-- token quota/credits/rejected decisions are retired; USD enforcement moved to the
-- Phase-6a pre-flight guardrail). The original CHECK predated 'recorded', so EVERY
-- audit insert violated it (SQLSTATE 23514) and the usage stream backed up with no
-- audit rows ever written (found by D-S4C-CONSUMER-LIVE-SMOKE, 2026-06-10). Widen
-- the constraint to allow 'recorded' while keeping the legacy values for old rows.
ALTER TABLE usage_logs DROP CONSTRAINT IF EXISTS usage_logs_billing_decision_check;
ALTER TABLE usage_logs ADD CONSTRAINT usage_logs_billing_decision_check
  CHECK (billing_decision IN ('quota','credits','rejected','recorded'));

-- D-S4C-ACCOUNTBALANCES-DROP (2026-06-17) — drop the inert token-quota wallet. The
-- token ledger was retired at S4c (USD spend_guardrails + platform_balances are the
-- live enforcement); nothing writes account_balances and its only reader (the
-- /v1/model-billing/account-balance endpoint) is removed in the same change. No FK
-- references it, so a plain idempotent drop is safe. ROLLBACK: re-add the CREATE TABLE
-- IF NOT EXISTS block above (it re-creates an EMPTY table — there is no data to restore;
-- the wallet was never populated post-retirement).
DROP TABLE IF EXISTS account_balances;

-- Public MCP P3 (H-C/PUB-11) — per-key spend attribution. The usage-stream consumer
-- writes mcp_key_id for jobs that originated at the public MCP edge (NULL for first-
-- party). The partial index backs the per-key monthly rollup (mcp-key-usage endpoint)
-- and the future per-key spend sub-cap (H-K). ROLLBACK: drop the column + index.
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS mcp_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_usage_logs_mcp_key
  ON usage_logs(owner_user_id, mcp_key_id, created_at DESC) WHERE mcp_key_id IS NOT NULL;

-- Public MCP P4/Wave-C (H-K) — per-key spend sub-cap. A reservation gets stamped
-- with the originating public key so the reserve handler can sum this key's HELD
-- holds (this table) + COMMITTED spend (usage_logs.mcp_key_id) against the key's
-- spend_cap_usd, inside the existing owner-row FOR UPDATE lock (race-safe). NULL
-- for first-party reservations (no per-key cap). The partial index backs the
-- held-sum scan. ROLLBACK: drop the column + index.
ALTER TABLE token_reservations ADD COLUMN IF NOT EXISTS mcp_key_id UUID;
CREATE INDEX IF NOT EXISTS idx_token_reservations_mcp_key
  ON token_reservations(mcp_key_id) WHERE status = 'held' AND mcp_key_id IS NOT NULL;

-- ── C6 / SD-C6 — the spend LANE ledger (3 tables) ────────────────────────────────────────────
-- A "lane" separates a user's spend by intent: ASSISTANT (the private work-assistant: distiller,
-- reflection, coaching scorer, voice STT/TTS) vs INTERACTIVE (novel chat, translation, extraction).
-- This lets a user cap assistant spend independently of their creative-writing spend, and lets the
-- product report the two separately. Every usage_logs row carries its lane (derived from purpose).

-- 1) spend_lanes — the SYSTEM-tier canonical lane set (admin-seeded; a regular user never writes it).
CREATE TABLE IF NOT EXISTS spend_lanes (
  lane_code   TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  sort_order  INT  NOT NULL DEFAULT 0
);
INSERT INTO spend_lanes (lane_code, label, description, sort_order) VALUES
  ('assistant',   'Work assistant', 'Private assistant: journaling, reflection, coaching, voice', 1),
  ('interactive', 'Interactive',    'Novel chat, translation, extraction, and other creative work', 2)
ON CONFLICT (lane_code) DO NOTHING;

-- 2) lane_purpose_map — purpose → lane. DATA, not a code CASE, so a new purpose is mapped by seeding a
-- row (not a redeploy). A purpose absent here defaults to 'interactive' at write time (the safe default:
-- an unclassified spend is not hidden inside the assistant lane).
CREATE TABLE IF NOT EXISTS lane_purpose_map (
  purpose   TEXT PRIMARY KEY,
  lane_code TEXT NOT NULL REFERENCES spend_lanes(lane_code)
);
INSERT INTO lane_purpose_map (purpose, lane_code) VALUES
  ('assistant',        'assistant'),
  ('voice_stt',        'assistant'),
  ('voice_tts',        'assistant'),
  ('reflection',       'assistant'),
  ('coaching',         'assistant'),
  ('distill',          'assistant'),
  ('chat',             'interactive'),
  ('translation',      'interactive'),
  ('image_gen',        'interactive'),
  ('entity_extraction','interactive')
ON CONFLICT (purpose) DO NOTHING;

-- usage_logs.lane — the resolved lane for each spend row (set at /record write from the map above).
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS lane TEXT NOT NULL DEFAULT 'interactive';
CREATE INDEX IF NOT EXISTS idx_usage_logs_owner_lane
  ON usage_logs(owner_user_id, lane, created_at DESC);

-- 3) user_lane_budgets — PER-USER per-lane monthly cap (User Boundaries: owner_user_id scope key).
-- A row = "this user wants at most $N/month on this lane". Absent ⇒ no lane-specific cap (the global
-- spend_guardrails still applies). NULL/0 monthly_limit_usd ⇒ unlimited for that lane.
CREATE TABLE IF NOT EXISTS user_lane_budgets (
  owner_user_id     UUID NOT NULL,
  lane_code         TEXT NOT NULL REFERENCES spend_lanes(lane_code),
  monthly_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, lane_code)
);
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
