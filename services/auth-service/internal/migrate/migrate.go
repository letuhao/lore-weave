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

-- ── WS-1.0 · per-user data-encryption key (DECISIONS-SEALED PO-2) — 2026-07-12 ──
--
-- The envelope: a deployment KEK (env/KMS, NEVER in this database) wraps a per-USER DEK,
-- and the DEK encrypts that user's private content — diary bodies, assistant chat
-- messages, and their KG fact_text.
--
-- It lives in auth-service because a DEK is a platform-wide per-user fact, exactly like
-- user_preferences and the user's timezone (sealed decision T-1). It must be ONE key per
-- user: chat encrypts a message and knowledge later decrypts it to extract from, so a
-- per-service key would make cross-service reads impossible.
--
-- ⚠️ What is stored here is the WRAPPED dek. Consumers fetch this blob and unwrap it with
-- the KEK from their own environment, so the plaintext DEK never crosses the network. That
-- protects a stolen dump/backup and a curious DBA. It does NOT protect against an operator
-- who controls a running service — see the honest disclosure in loreweave_crypto. Do not
-- let that claim drift.
--
-- ON DELETE CASCADE is load-bearing for D18 erasure: dropping the user drops the DEK, and
-- without the DEK their ciphertext is unrecoverable — including in any backup taken before
-- the deletion. That is a genuine crypto-shred, and it is the only story that survives
-- backup resurrection (T23).
CREATE TABLE IF NOT EXISTS user_deks (
  user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  wrapped_dek TEXT NOT NULL,          -- base64(nonce || AES-GCM(kek, dek))
  key_ref     TEXT NOT NULL,          -- fingerprint of the KEK that wrapped it (rotation visibility)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Which users are still wrapped under a retired KEK? (an operator's rotation checklist)
CREATE INDEX IF NOT EXISTS idx_user_deks_key_ref ON user_deks(key_ref);

-- P3 (D-DEK-MULTICONSUMER-TRIPWIRE / DBT-9) — a DURABLE, attributed forensic trail for the crypto-shred,
-- the single most destructive irreversible op on the platform (previously the ONLY record was an
-- ephemeral slog line). Deliberately has NO FK to users(id): the audit must OUTLIVE the user's own
-- deletion (a shred is precisely part of erasing that user), so an ON DELETE CASCADE would erase the
-- evidence. rows_shredded=0 records a mis-targeted/no-op shred (visible, never hidden). Append-only.
CREATE TABLE IF NOT EXISTS dek_shred_audit (
  audit_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id       UUID NOT NULL,          -- NO FK: must survive the user's own deletion (forensic)
  rows_shredded INT  NOT NULL,          -- 0 = shred hit nothing (already-absent OR a wrong user_id)
  actor         TEXT NULL,              -- the caller service/actor, if identifiable (X-Actor header)
  trace_id      TEXT NULL,              -- the request's x-trace-id (correlation with the erasure)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dek_shred_audit_user_created ON dek_shred_audit (user_id, created_at DESC);

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
  outcome        TEXT NOT NULL CHECK (outcome IN ('relayed','denied_scope','rate_limited','unauthorized','upstream_error','tool_error')),
  trace_id       TEXT NULL,                           -- the edge-minted x-trace-id (correlation)
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- D-PMCP-AUDIT-DOWNSTREAM-OUTCOME: add 'tool_error' (a single tools/call the edge
-- relayed 2xx but whose JSON-RPC body carried an error member — the tool ran and
-- failed, distinct from a successful 'relayed' or a transport/non-2xx 'upstream_error'). The
-- inline CHECK above only applies to a FRESH table; this idempotent ALTER widens the
-- constraint on an already-created one (the auto-named constraint is *_outcome_check).
DO $$
BEGIN
    ALTER TABLE mcp_call_audit DROP CONSTRAINT IF EXISTS mcp_call_audit_outcome_check;
    ALTER TABLE mcp_call_audit ADD CONSTRAINT mcp_call_audit_outcome_check
        CHECK (outcome IN ('relayed','denied_scope','rate_limited','unauthorized','upstream_error','tool_error'));
END $$;

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

-- Public MCP human-approval queue (P4 / OD-2, docs/specs/2026-06-26-public-mcp/03 §6.3). A
-- default (allow_self_confirm=false) public key's Tier-W "propose" returns a confirm_token
-- WITHOUT spending; the mcp-public-gateway edge diverts it here (POST /internal/mcp-keys/approvals)
-- instead of handing the token to the agent. The owner sees the pending action, Approve replays
-- the token to the owning domain's /v1/<domain>/actions/confirm (the ONLY spend path) tagged with
-- X-Mcp-Key-Id so cost attributes to the AGENT's key, Deny drops it. Unlike mcp_call_audit this is
-- MUTABLE (status transitions) so it is NOT append-only. key_id is NOT a FK (the queue must outlive
-- a revoked key, same as audit); owner_user_id IS an FK (CASCADE) so a deleted account's queue is
-- purged with it. confirm_token is stored PLAINTEXT — it is already single-use (provider jti ledger)
-- + expiry-bound + user-bound, so at-rest exposure is bounded and avoids a re-mint round-trip.
CREATE TABLE IF NOT EXISTS mcp_pending_approvals (
  approval_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  key_id            UUID NOT NULL,                       -- the public key that proposed (NOT a FK)
  owner_user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tool_name         TEXT NOT NULL,                       -- the Tier-W tool the agent called
  domain            TEXT NOT NULL,                       -- the propose result's domain — routes the execute
  confirm_token     TEXT NOT NULL,                       -- the server-minted token replayed on approve
  preview           JSONB NOT NULL DEFAULT '{}',         -- the propose result shown to the human
  cost_estimate_usd NUMERIC NULL,                        -- the agent-visible estimate, if any
  status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','denied','expired','executed','failed')),
  expires_at        TIMESTAMPTZ NOT NULL,                -- mirrors the confirm token's own exp
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at        TIMESTAMPTZ NULL                      -- when the owner approved/denied (or it was executed)
);

-- Owner read path: the owner's pending (then recent) approvals, newest first.
CREATE INDEX IF NOT EXISTS idx_mcp_pending_approvals_owner
  ON mcp_pending_approvals (owner_user_id, status, created_at DESC);

-- P5 OAuth 2.1 (public-MCP on-behalf-of). Three tables:
--  - mcp_oauth_clients : registered clients (RFC 7591 DCR lands the open registration
--    in slice 3; slice 2 seeds clients via the internal register). Public PKCE clients
--    hold no secret (token_endpoint_auth_method='none').
--  - mcp_oauth_grants  : per (owner,client) consent — the GRANTED (downscoped) scopes +
--    the rotating refresh-token hash. id is the grant_id that rides x-mcp-key-id.
--  - mcp_oauth_codes   : short-lived single-use authorization codes (PKCE-bound). No
--    Redis in auth-service, so codes live here; the code itself is stored HASHED.
CREATE TABLE IF NOT EXISTS mcp_oauth_clients (
  client_id                  TEXT PRIMARY KEY,
  client_name                TEXT NOT NULL DEFAULT '',
  redirect_uris              TEXT[] NOT NULL DEFAULT '{}',
  grant_types                TEXT[] NOT NULL DEFAULT '{authorization_code,refresh_token}',
  token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
  scopes_requested           TEXT[] NOT NULL DEFAULT '{}',
  status                     TEXT NOT NULL DEFAULT 'active'
                               CHECK (status IN ('active','disabled')),
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_ip                 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mcp_oauth_grants (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id          TEXT NOT NULL,
  scopes             TEXT[] NOT NULL DEFAULT '{}',
  resource           TEXT NOT NULL DEFAULT '',
  refresh_token_hash TEXT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at       TIMESTAMPTZ NULL,
  expires_at         TIMESTAMPTZ NULL,
  revoked_at         TIMESTAMPTZ NULL,
  UNIQUE (owner_user_id, client_id)
);
CREATE INDEX IF NOT EXISTS idx_mcp_oauth_grants_owner ON mcp_oauth_grants (owner_user_id);
CREATE INDEX IF NOT EXISTS idx_mcp_oauth_grants_refresh
  ON mcp_oauth_grants (refresh_token_hash) WHERE refresh_token_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS mcp_oauth_codes (
  code_hash             TEXT PRIMARY KEY,                  -- sha256(code); the raw code is never stored
  owner_user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id             TEXT NOT NULL,
  scopes                TEXT[] NOT NULL DEFAULT '{}',
  redirect_uri          TEXT NOT NULL,
  resource              TEXT NOT NULL,
  code_challenge        TEXT NOT NULL,
  code_challenge_method TEXT NOT NULL DEFAULT 'S256',
  expires_at            TIMESTAMPTZ NOT NULL,
  consumed_at           TIMESTAMPTZ NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- P5 open DCR (RFC 7591, slice 3) audit. The /oauth/register endpoint is PUBLIC
-- (unauthenticated) — this append-only table records every registration ATTEMPT
-- (issued or rejected) for abuse detection. Writes are bounded by the per-IP rate
-- limit (a 429 sheds before any row is written, so the audit can't be flooded).
-- client_id is NULL on a rejected attempt (no client was issued).
CREATE TABLE IF NOT EXISTS mcp_oauth_client_registrations (
  registration_id UUID PRIMARY KEY DEFAULT uuidv7(),
  client_id       TEXT NULL,
  client_name     TEXT NOT NULL DEFAULT '',
  redirect_uris   TEXT[] NOT NULL DEFAULT '{}',
  outcome         TEXT NOT NULL CHECK (outcome IN ('registered','rejected')),
  reason          TEXT NULL,                           -- rejection reason code (NULL on success)
  created_ip      TEXT NOT NULL DEFAULT '',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mcp_oauth_client_registrations_ip
  ON mcp_oauth_client_registrations (created_ip, created_at DESC);

-- Append-only (mirrors mcp_call_audit) — REVOKE so even a compromised app role can't
-- rewrite the registration history. No-op when connected as the DB owner (dev stack).
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE mcp_oauth_client_registrations FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

-- D-C-PRODUCER-OUTBOX — transactional outbox (standard worker-infra shape: the shared
-- relay drains published_at IS NULL). auth had none; the mcp_approval owner notification
-- was a fire-and-forget POST lost if notification-service was down. Now it's written here
-- in the same tx as the approval INSERT and the relay delivers it (aggregate_type=
-- 'notification' ⇒ POST to notification-service, idempotent via the payload's dedup_key).
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  event_type     TEXT NOT NULL,
  aggregate_type TEXT NOT NULL DEFAULT 'notification',
  aggregate_id   UUID,
  payload        JSONB NOT NULL,
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_outbox_pending
  ON outbox_events (created_at) WHERE published_at IS NULL;
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	if err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}
