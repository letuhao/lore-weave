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
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
