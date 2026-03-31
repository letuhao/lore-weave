package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS account_balances (
  owner_user_id UUID PRIMARY KEY,
  tier_name TEXT NOT NULL DEFAULT 'starter',
  month_quota_tokens INT NOT NULL DEFAULT 100000,
  month_quota_remaining_tokens INT NOT NULL DEFAULT 100000,
  credits_balance INT NOT NULL DEFAULT 1000,
  billing_policy_version TEXT NOT NULL DEFAULT 'm03-v1',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
