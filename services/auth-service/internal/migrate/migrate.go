package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  locale TEXT,
  avatar_url TEXT,
  email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  account_status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash TEXT NOT NULL UNIQUE,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS verification_tickets (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_verification_user ON verification_tickets(user_id);

CREATE TABLE IF NOT EXISTS reset_tickets (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reset_user ON reset_tickets(user_id);

CREATE TABLE IF NOT EXISTS security_preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  email_verification_required BOOLEAN NOT NULL DEFAULT TRUE,
  password_reset_method TEXT NOT NULL DEFAULT 'email_link',
  session_alerts_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id    UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  prefs      JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- P9-02: Profile extensions
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS languages TEXT[] DEFAULT '{}';

-- P9-02: Follow system
CREATE TABLE IF NOT EXISTS user_follows (
  follower_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  following_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (follower_id, following_id),
  CHECK (follower_id != following_id)
);
CREATE INDEX IF NOT EXISTS idx_follows_following ON user_follows(following_id);
CREATE INDEX IF NOT EXISTS idx_follows_follower ON user_follows(follower_id);

-- 074 (D-ADMIN-CLI-JWT): admin principals — the RBAC source of truth for who
-- may be issued an admin JWT. ON DELETE RESTRICT (NOT CASCADE) so an admin grant
-- must be explicitly revoked before the user row can be removed; admin status
-- cannot be silently erased via the DELETE /account path.
CREATE TABLE IF NOT EXISTS admin_principals (
  user_id    UUID PRIMARY KEY REFERENCES users(id) ON DELETE RESTRICT,
  role       TEXT NOT NULL CHECK (role IN ('admin','sre','founder')),
  scopes     TEXT[] NOT NULL DEFAULT '{}',
  active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 074/075: append-only audit of every admin/break-glass token ISSUANCE attempt.
-- Lives in auth-service's own DB (NOT the meta-DB admin_action_audit, whose
-- MetaWrite path is deferred-073). Every attempt is logged via the outcome col,
-- denies/errors, so probing the mint endpoint leaves a trail. Free-text reason
-- is NEVER stored: only reason_len + a KEYED HMAC (not dictionary-reversible).
-- actor_handle is denormalized so the forensic trail survives user deletion.
CREATE TABLE IF NOT EXISTS admin_token_issuance_audit (
  audit_id            UUID PRIMARY KEY,
  actor_id            UUID NOT NULL,
  actor_handle        TEXT NOT NULL,
  second_actor_id     UUID NULL,
  second_actor_handle TEXT NULL,
  token_kind          TEXT NOT NULL CHECK (token_kind IN ('admin','break_glass')),
  outcome             TEXT NOT NULL CHECK (outcome IN ('success','deny','error')),
  deny_reason         TEXT NULL,
  role                TEXT NULL,
  scopes              TEXT[] NOT NULL DEFAULT '{}',
  break_glass         BOOLEAN NOT NULL DEFAULT FALSE,
  incident_ticket     TEXT NULL,
  reason_len          INT NULL CHECK (reason_len IS NULL OR reason_len >= 100),
  reason_hmac         BYTEA NULL,
  jti                 UUID NULL,
  issued_at_nanos     BIGINT NULL,
  expires_at_nanos    BIGINT NULL,
  created_at_nanos    BIGINT NOT NULL,
  created_at          TIMESTAMPTZ GENERATED ALWAYS AS
      (to_timestamp(created_at_nanos::double precision / 1e9)) STORED
);

-- jti is unique across SUCCESSFUL issuances (NULL on deny/error rows).
CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_issuance_jti
  ON admin_token_issuance_audit (jti) WHERE jti IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_admin_issuance_actor_created
  ON admin_token_issuance_audit (actor_id, created_at DESC);

-- Append-only: REVOKE UPDATE/DELETE so even a compromised app role cannot
-- rewrite history. NOTE: this only holds if auth-service connects as a
-- NON-OWNER role (owner/superuser bypasses REVOKE). The dev stack connects as
-- the DB owner, so the guard is a no-op there and the EXCEPTION below swallows
-- the missing-role case; production MUST run auth-service under app_service_role.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE admin_token_issuance_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

-- Public MCP credential store (P1, docs/specs/2026-06-26-public-mcp/03 §5). An
-- external agent presents an API key (lw_pk_<random>) in the Authorization header;
-- the mcp-public-gateway edge resolves it here. The raw secret is NEVER stored —
-- only an Argon2id hash (same primitive as password_hash). Lookup is by key_prefix
-- (the leading, non-secret slice) then a constant-time hash verify of the candidates.
-- ON DELETE CASCADE: deleting a user invalidates their keys (the resolve path also
-- re-checks users.account_status='active', H-L).
CREATE TABLE IF NOT EXISTS mcp_api_keys (
  key_id             UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  key_prefix         TEXT NOT NULL,                       -- e.g. 'lw_pk_AbC1' (shown in UI; O(1) lookup)
  key_hash           TEXT NOT NULL,                       -- argon2id$… of the full secret (never the raw key)
  scopes             TEXT[] NOT NULL DEFAULT '{}',        -- tier∩domain scopes (P2 fills; P0/P1 may be empty)
  spend_cap_usd      NUMERIC(16,8) NULL,                  -- per-key monthly USD sub-cap (NULL = inherit guardrail only, P3)
  rate_limit_rpm     INT NOT NULL DEFAULT 60,             -- edge per-key rate limit (P3)
  allow_self_confirm BOOLEAN NOT NULL DEFAULT FALSE,      -- OD-2: headless Tier-W self-confirm opt-in (default human-approve)
  status             TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
  last_used_at       TIMESTAMPTZ NULL,
  expires_at         TIMESTAMPTZ NULL,                    -- optional rotation/expiry
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resolve hot-path: prefix lookup scoped to live keys.
CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_prefix ON mcp_api_keys (key_prefix) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_owner ON mcp_api_keys (owner_user_id);

-- Public MCP per-key call audit (P3 / H-O, docs/specs/2026-06-26-public-mcp/03 §H-O). The
-- mcp-public-gateway edge sees EVERY external-agent call and fires a best-effort audit row here
-- (one per tools/call; non-call methods carry method only). Append-only: the owner reads their
-- own key's call history (GET /v1/account/mcp-keys/{id}/audit). key_id is NOT a FK — audit rows
-- OUTLIVE a revoked/deleted key (the history must survive key deletion); owner_user_id IS an FK
-- (CASCADE) so a deleted account's audit is purged with it.
CREATE TABLE IF NOT EXISTS mcp_call_audit (
  audit_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  key_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  method         TEXT NOT NULL,                       -- the JSON-RPC method (tools/call, tools/list, …)
  tool_name      TEXT NULL,                           -- the tools/call name; NULL for non-call methods
  outcome        TEXT NOT NULL CHECK (outcome IN ('relayed','denied_scope','rate_limited','unauthorized','upstream_error')),
  trace_id       TEXT NULL,                           -- the edge-minted x-trace-id (correlation)
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Owner read path: a key's recent calls, newest first.
CREATE INDEX IF NOT EXISTS idx_mcp_call_audit_owner_key_created
  ON mcp_call_audit (owner_user_id, key_id, created_at DESC);

-- Append-only: REVOKE UPDATE/DELETE so even a compromised app role cannot rewrite the call
-- history. Same dev-stack caveat as admin_token_issuance_audit (no-op when connected as the DB
-- owner; production MUST run auth-service under app_service_role).
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE mcp_call_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	if err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
