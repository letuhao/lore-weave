package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// schemaSQL is applied idempotently on startup (CREATE ... IF NOT EXISTS).
// Tenancy (CLAUDE.md LOCKED 3-tier): every user-facing row carries a scope key
// and a tier; a CHECK pins exactly one scope key per tier, and per-tier partial
// UNIQUE indexes replace the naive global UNIQUE(slug) that caused the
// entity-kinds bug. Additional tables are layered by later phases (mcp_server_
// registrations, skills, commands, hooks, subagent_defs, skill_proposals).
const schemaSQL = `
-- P0: the Plugin — the unit of install (a versioned bundle).
CREATE TABLE IF NOT EXISTS plugins (
  plugin_id UUID PRIMARY KEY DEFAULT uuidv7(),
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  name TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '0.0.0',
  description TEXT NOT NULL DEFAULT '',
  manifest JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','draft','suspended','archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- exactly one scope key per tier
  CONSTRAINT plugins_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_plugins_owner ON plugins(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_plugins_book ON plugins(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_plugins_system ON plugins(name, version) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_plugins_user   ON plugins(owner_user_id, name, version) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_plugins_book   ON plugins(book_id, name, version) WHERE tier = 'book';

-- P0: per-user / per-book enablement override (D1). Absence = tier default (on).
-- A System plugin is never mutated; disabling it stores an override row here.
CREATE TABLE IF NOT EXISTS plugin_enablement (
  enablement_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID NOT NULL REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  scope TEXT NOT NULL CHECK (scope IN ('user','book')),
  owner_user_id UUID,
  book_id UUID,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT enablement_scope_key CHECK (
    (scope = 'user' AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (scope = 'book' AND book_id IS NOT NULL)
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_enablement_user ON plugin_enablement(plugin_id, owner_user_id) WHERE scope = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_enablement_book ON plugin_enablement(plugin_id, book_id) WHERE scope = 'book';

-- REG-X-01: append-only activity log. P0 writes rows explicitly from mutation
-- handlers (simpler + directly testable than an AFTER-UPDATE trigger; see
-- DECISION_LOG DL-1). Read surface is the Activity-log screen (P1).
CREATE TABLE IF NOT EXISTS registry_audit (
  audit_id UUID PRIMARY KEY DEFAULT uuidv7(),
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_user_id UUID,
  actor_kind TEXT NOT NULL DEFAULT 'user' CHECK (actor_kind IN ('user','agent','admin','system')),
  kind TEXT NOT NULL,
  action TEXT NOT NULL,
  target_id UUID,
  target_name TEXT NOT NULL DEFAULT '',
  tier TEXT,
  detail JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_registry_audit_actor ON registry_audit(actor_user_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_registry_audit_kind ON registry_audit(kind, at DESC);

-- Q-CACHE substrate: a monotonic catalog version bumped on any mutation. The
-- effective-catalog etag derives from it so consumers (ai-gateway, P2) can
-- cheaply detect staleness. Single row (id = TRUE).
CREATE TABLE IF NOT EXISTS registry_meta (
  id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
  catalog_version BIGINT NOT NULL DEFAULT 1
);
INSERT INTO registry_meta (id) VALUES (TRUE) ON CONFLICT (id) DO NOTHING;
`

// Up applies the schema. Idempotent; safe to run on every boot.
func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	return err
}
