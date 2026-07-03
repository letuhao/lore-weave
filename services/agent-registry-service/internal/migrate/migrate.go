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

-- P1: user-authored Skills (SKILL.md — prompt-only, no executable scripts).
CREATE TABLE IF NOT EXISTS skills (
  skill_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  slug TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  frontmatter JSONB NOT NULL DEFAULT '{}',
  body_md TEXT NOT NULL DEFAULT '',
  surfaces TEXT[] NOT NULL DEFAULT '{}',
  triggers JSONB NOT NULL DEFAULT '{}',
  book_scoped BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','archived')),
  source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','agent','system','import')),
  used_count BIGINT NOT NULL DEFAULT 0,
  last_triggered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT skills_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_skills_book ON skills(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_system ON skills(slug) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_user   ON skills(owner_user_id, slug) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_book   ON skills(book_id, slug) WHERE tier = 'book';

-- P1: agent skill proposals (propose→confirm HITL spine). The agent submits via
-- the registry_propose_skill MCP tool; a human approves via the confirm route.
CREATE TABLE IF NOT EXISTS skill_proposals (
  proposal_id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('create','update')),
  target_skill_id UUID REFERENCES skills(skill_id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  frontmatter JSONB NOT NULL DEFAULT '{}',
  body_md TEXT NOT NULL DEFAULT '',
  surfaces TEXT[] NOT NULL DEFAULT '{}',
  confirm_token TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
  reject_reason TEXT NOT NULL DEFAULT '',
  from_session_id TEXT NOT NULL DEFAULT '',
  from_session_label TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
);
CREATE INDEX IF NOT EXISTS idx_skill_proposals_owner ON skill_proposals(owner_user_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_proposals_token ON skill_proposals(confirm_token);

-- P1: skill revision history (append a snapshot on each publish; restore = new draft).
CREATE TABLE IF NOT EXISTS skill_revisions (
  revision_id UUID PRIMARY KEY DEFAULT uuidv7(),
  skill_id UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
  description TEXT NOT NULL DEFAULT '',
  frontmatter JSONB NOT NULL DEFAULT '{}',
  body_md TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_revisions_skill ON skill_revisions(skill_id, created_at DESC);

-- P1: per-user per-skill enablement toggle (GUI §4). System skills default-on;
-- a user disable stores an override here (never mutates the System row). For a
-- user's own skill this coexists with 'status' (draft = never injected).
CREATE TABLE IF NOT EXISTS skill_enablement (
  skill_id UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (skill_id, owner_user_id)
);

-- P2: user/book-registered MCP servers (the per-user federation overlay source).
-- P2 carries internal-only fields; P3 adds auth/secret/oauth/egress/scan columns
-- for arbitrary external servers. A registration is a pointer to an MCP endpoint
-- the user wants federated into THEIR catalog, namespaced by tool_name_prefix so
-- it can never shadow a System tool.
CREATE TABLE IF NOT EXISTS mcp_server_registrations (
  mcp_server_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  display_name TEXT NOT NULL DEFAULT '',
  endpoint_url TEXT NOT NULL,
  transport TEXT NOT NULL DEFAULT 'streamable_http' CHECK (transport IN ('streamable_http')),
  tool_name_prefix TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','pending','suspended','error')),
  last_health JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT mcp_reg_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_mcp_reg_owner ON mcp_server_registrations(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_mcp_reg_book ON mcp_server_registrations(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_reg_user ON mcp_server_registrations(owner_user_id, endpoint_url) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_reg_book ON mcp_server_registrations(book_id, endpoint_url) WHERE tier = 'book';

CREATE TABLE IF NOT EXISTS mcp_server_enablement (
  mcp_server_id UUID NOT NULL REFERENCES mcp_server_registrations(mcp_server_id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (mcp_server_id, owner_user_id)
);

-- P3: external-MCP + security columns (all additive; existing internal rows keep
-- auth_kind='none', empty egress/scan). auth_kind pins how the server authenticates;
-- the bearer/oauth secret ciphertext lives in agent-registry's own AES-GCM vault
-- (DECISION-1), NEVER echoed on the public API (has_secret only). oauth_meta holds
-- issuer/scopes/resource(RFC8707)/PKCE state; egress_allowlist is the per-server
-- outbound host allowlist the ai-gateway egress path enforces; scan_result is the
-- supply-chain scan verdict that gates status pending→active.
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS auth_kind TEXT NOT NULL DEFAULT 'none';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS is_external BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS secret_ciphertext TEXT NOT NULL DEFAULT '';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS secret_key_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS oauth_meta JSONB NOT NULL DEFAULT '{}';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS egress_allowlist JSONB NOT NULL DEFAULT '[]';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS scan_result JSONB NOT NULL DEFAULT '{}';
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS last_scanned_at TIMESTAMPTZ;
-- auth_kind domain guard (idempotent; ADD CONSTRAINT has no IF NOT EXISTS pre-PG16 so guard via catalog).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mcp_reg_auth_kind') THEN
    ALTER TABLE mcp_server_registrations ADD CONSTRAINT mcp_reg_auth_kind CHECK (auth_kind IN ('none','bearer','oauth2'));
  END IF;
END $$;
-- P3 OAuth: the refresh token is sealed separately from the access token (both vault).
ALTER TABLE mcp_server_registrations ADD COLUMN IF NOT EXISTS refresh_ciphertext TEXT NOT NULL DEFAULT '';

-- P3 REG-P3-03: in-flight OAuth 2.1 authorization-code + PKCE flows. A start mints a
-- state + code_verifier bound to (server, owner); the callback consumes it exactly
-- once to exchange the code. Short TTL; swept opportunistically.
CREATE TABLE IF NOT EXISTS oauth_flows (
  state TEXT PRIMARY KEY,
  mcp_server_id UUID NOT NULL REFERENCES mcp_server_registrations(mcp_server_id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL,
  code_verifier TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '10 minutes'
);
CREATE INDEX IF NOT EXISTS idx_oauth_flows_server ON oauth_flows(mcp_server_id);

-- P4: user-authored slash commands. A /name args in a chat message expands the
-- template_md (server-side by default) with the parsed args before the turn. Tenancy
-- as everywhere: scope key + per-tier partial UNIQUE(name).
CREATE TABLE IF NOT EXISTS slash_commands (
  command_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  name TEXT NOT NULL,                                   -- lowercase a-z0-9-, no leading slash
  description TEXT NOT NULL DEFAULT '',
  arg_schema JSONB NOT NULL DEFAULT '{}',
  template_md TEXT NOT NULL DEFAULT '',
  expand_side TEXT NOT NULL DEFAULT 'server' CHECK (expand_side IN ('server','client')),
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT commands_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_commands_owner ON slash_commands(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_commands_book ON slash_commands(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commands_system ON slash_commands(name) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_commands_user   ON slash_commands(owner_user_id, name) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_commands_book   ON slash_commands(book_id, name) WHERE tier = 'book';

-- P4: declarative hooks (no code execution). Fire at agent-loop seams; the action is
-- a fixed, enum-typed effect the chat-service hook engine interprets.
CREATE TABLE IF NOT EXISTS hooks (
  hook_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  name TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  on_event TEXT NOT NULL CHECK (on_event IN ('pre_tool_call','post_tool_call','pre_turn','post_turn')),
  match JSONB NOT NULL DEFAULT '{}',                    -- e.g. {"tool_pattern":"glossary_*"}
  action JSONB NOT NULL DEFAULT '{}',                   -- {"kind":"deny|require_approval|annotate|inject_text", ...}
  priority INTEGER NOT NULL DEFAULT 0,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT hooks_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_hooks_owner ON hooks(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_hooks_book ON hooks(book_id);
CREATE INDEX IF NOT EXISTS idx_hooks_event ON hooks(on_event);

-- P5: subagent definitions — a named persona (own system_prompt) with a tool_scope
-- (a subset filter over the user's catalog) + an optional model_ref. The CRUD +
-- resolver ship here; the scoped-execution RUNTIME (a registry_run_subagent server
-- tool that runs an isolated nested turn) is a larger structural piece tracked as
-- D-REG-P5-SUBAGENT-RUNTIME.
CREATE TABLE IF NOT EXISTS subagent_defs (
  subagent_id UUID PRIMARY KEY DEFAULT uuidv7(),
  plugin_id UUID REFERENCES plugins(plugin_id) ON DELETE CASCADE,
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  name TEXT NOT NULL,                                  -- lowercase a-z0-9-
  description TEXT NOT NULL DEFAULT '',
  system_prompt TEXT NOT NULL DEFAULT '',
  tool_scope JSONB NOT NULL DEFAULT '[]',              -- allowed tool-name globs, e.g. ["glossary_*","kg_*"]
  model_ref TEXT NOT NULL DEFAULT '',
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT subagents_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_subagents_owner ON subagent_defs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_subagents_book ON subagent_defs(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_subagents_system ON subagent_defs(name) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_subagents_user ON subagent_defs(owner_user_id, name) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_subagents_book ON subagent_defs(book_id, name) WHERE tier = 'book';

-- REG-P1-03: seed the 5 hardcoded chat-service skills as System-tier rows so the
-- FE can list + toggle them and enablement resolves. Their BODIES remain authored
-- in chat-service skill_registry (single source; DECISION_LOG DL-4) — these rows
-- carry only catalog metadata. Slugs are byte-identical to SYSTEM_SKILLS keys.
INSERT INTO skills (tier, slug, description, source, body_md) VALUES
  ('system','glossary','Glossary/lore entity workflows — search, propose, confirm entity edits.','system','(System skill — body served by chat-service skill_registry)'),
  ('system','universal','Cross-domain manuscript workflows — the default universal agent surface.','system','(System skill — body served by chat-service skill_registry)'),
  ('system','knowledge','Knowledge-graph + memory grounding and story search.','system','(System skill — body served by chat-service skill_registry)'),
  ('system','admin','Admin/CMS system-tier operations (admin surface only).','system','(System skill — body served by chat-service skill_registry)'),
  ('system','plan_forge','PlanForge novel-system planning workflows.','system','(System skill — body served by chat-service skill_registry)')
ON CONFLICT (slug) WHERE tier = 'system' DO NOTHING;
`

// Up applies the schema. Idempotent; safe to run on every boot.
func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	return err
}
