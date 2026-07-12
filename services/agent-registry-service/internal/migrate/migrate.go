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

-- P5 REG-P5-03: official MCP Registry ingest → admin curation queue. An admin pulls
-- the public server list into this queue as 'pending'; nothing federates until an
-- explicit approve creates a System-tier mcp_server_registration that then passes the
-- SAME P3 supply-chain scan (verification ≠ safety — an official listing is untrusted
-- until scanned). No credentials are ever ingested.
CREATE TABLE IF NOT EXISTS registry_ingest_queue (
  ingest_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  source         TEXT NOT NULL DEFAULT 'official',      -- future: other catalogs
  registry_id    TEXT NOT NULL,                          -- the upstream registry's stable server id
  name           TEXT NOT NULL,                          -- reverse-DNS
  description    TEXT NOT NULL DEFAULT '',
  version        TEXT NOT NULL DEFAULT '',
  endpoint_url   TEXT NOT NULL,                          -- the chosen streamable-http remote
  raw            JSONB NOT NULL DEFAULT '{}',            -- the full upstream entry (audit)
  status         TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','approved','rejected')),
  reviewed_by    UUID,
  approved_server_id UUID REFERENCES mcp_server_registrations(mcp_server_id) ON DELETE SET NULL,
  reject_reason  TEXT NOT NULL DEFAULT '',
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ingest_source_regid ON registry_ingest_queue(source, registry_id);
CREATE INDEX IF NOT EXISTS idx_ingest_status ON registry_ingest_queue(status, first_seen_at DESC);
-- REG-P5 scheduled worker: a 4th status for a server the upstream registry has REMOVED
-- after we approved it (denylist / retroactive-removal §7b#1). Swap the inline CHECK for
-- a named one that admits it (idempotent — drops the auto-named inline check, adds ours).
DO $$ BEGIN
  ALTER TABLE registry_ingest_queue DROP CONSTRAINT IF EXISTS registry_ingest_queue_status_check;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ingest_status_check') THEN
    ALTER TABLE registry_ingest_queue ADD CONSTRAINT ingest_status_check
      CHECK (status IN ('pending','approved','rejected','revoked_upstream'));
  END IF;
END $$;

-- Endpoint dedup for System-tier servers (REG-P5-03 §7b#3): an ingest approve must
-- not create a second System row for an endpoint already federated. Partial UNIQUE so
-- user/book rows (which dedup per-owner via uq_mcp_reg_user/book) are unaffected.
-- Boot-safe: if a pre-existing environment already has duplicate System endpoints
-- (a data bug), creating the UNIQUE index would ERROR and brick startup — so we catch
-- unique_violation and skip with a NOTICE. Approve's check-before-insert still prevents
-- NEW duplicates; the hard index applies once the pre-existing dup is resolved.
DO $$ BEGIN
  CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_reg_system ON mcp_server_registrations(endpoint_url) WHERE tier = 'system';
EXCEPTION WHEN unique_violation THEN
  RAISE NOTICE 'uq_mcp_reg_system skipped: pre-existing duplicate System endpoints — resolve them, then restart to enforce the index';
END $$;

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

-- WS-2a (agent-discoverability spec): curated multi-step WORKFLOWS — an authored,
-- ordered list of tool steps a user/agent can run as one named capability (C3 steps
-- schema). Same 3-tier tenancy as skills: System (admin-seeded, read-only to users),
-- Per-user, Per-book. steps/inputs hold the C3 object; the chat-service step-runner
-- (WS-2b) executes them, honoring each step's gate (none/confirm/approval). Slug is
-- unique PER TIER (per-user / per-book scope keys — never a global UNIQUE(slug)).
CREATE TABLE IF NOT EXISTS workflows (
  workflow_id UUID PRIMARY KEY DEFAULT uuidv7(),
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  slug TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  surfaces TEXT[] NOT NULL DEFAULT '{}',
  inputs JSONB NOT NULL DEFAULT '{}',       -- C3 inputs: { <name>: "required"|"optional" }
  steps JSONB NOT NULL DEFAULT '[]',        -- C3 steps: [ { id, tool, gate, when?, repeat?, inputs_map? } ]
  notes_md TEXT NOT NULL DEFAULT '',        -- prose the agent reads; NOT executed
  status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','archived')),
  source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user','agent','system','import')),
  used_count BIGINT NOT NULL DEFAULT 0,
  last_run_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT workflows_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_workflows_owner ON workflows(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_workflows_book ON workflows(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_system ON workflows(slug) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_user   ON workflows(owner_user_id, slug) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_book   ON workflows(book_id, slug) WHERE tier = 'book';

-- WS-2a HITL spine: an agent proposes a workflow via registry_propose_workflow; a
-- human approves via the confirm route (mirrors skill_proposals exactly).
CREATE TABLE IF NOT EXISTS workflow_proposals (
  proposal_id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  book_id UUID,                              -- set ⇒ a book-tier proposal; NULL ⇒ user-tier
  action TEXT NOT NULL CHECK (action IN ('create','update')),
  target_workflow_id UUID REFERENCES workflows(workflow_id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  surfaces TEXT[] NOT NULL DEFAULT '{}',
  inputs JSONB NOT NULL DEFAULT '{}',
  steps JSONB NOT NULL DEFAULT '[]',
  notes_md TEXT NOT NULL DEFAULT '',
  confirm_token TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
  reject_reason TEXT NOT NULL DEFAULT '',
  from_session_id TEXT NOT NULL DEFAULT '',
  from_session_label TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
);
CREATE INDEX IF NOT EXISTS idx_workflow_proposals_owner ON workflow_proposals(owner_user_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_proposals_token ON workflow_proposals(confirm_token);

-- WS-2a: workflow revision history (snapshot on each publish; restore = new draft).
CREATE TABLE IF NOT EXISTS workflow_revisions (
  revision_id UUID PRIMARY KEY DEFAULT uuidv7(),
  workflow_id UUID NOT NULL REFERENCES workflows(workflow_id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  surfaces TEXT[] NOT NULL DEFAULT '{}',
  inputs JSONB NOT NULL DEFAULT '{}',
  steps JSONB NOT NULL DEFAULT '[]',
  notes_md TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_workflow_revisions_wf ON workflow_revisions(workflow_id, created_at DESC);

-- WS-5 (agent-discoverability spec §5 / Track C): seed the System-tier curated
-- WORKFLOW CATALOG. Each row is a C3 steps object the chat-service step-runner
-- (WS-2b) hands the agent as an explicit rail. The rail NAMES the tools in order so a
-- mid-tier model FOLLOWS the sequence instead of reconstructing it — the measured S01
-- failure was gemma proposing entities before any category existed ('unknown kind',
-- silent loop). notes_md owns the plain-language vocabulary (no jargon reaches the
-- user). System-tier: admin-seeded, read-only to users, world-visible. Idempotent.
--
-- Re-seeding semantics for System WORKFLOWS: DO UPDATE, not DO NOTHING. A System
-- workflow is CODE-OWNED (admin-seeded, read-only to users), so this file is its source
-- of truth and a deploy must be able to CORRECT it. DO NOTHING would mean an
-- already-seeded row never picks up a fixed rail or fixed wording — the "a migration
-- never revisits its default" trap, which already bit this effort once (a stale July-9
-- glossary-bootstrap row silently shadowed the rewritten one). User/book-tier rows are
-- untouched.
--
-- W1 glossary-bootstrap — "set up my world": create the CATEGORIES a book tracks
-- (kinds), in the correct order (adopt → confirm → read back), NEVER entities-first.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','glossary-bootstrap','Set up a book''s world categories',
   'Set up the kinds of things a book tracks (characters, places, systems, terms…) — the starting structure for its lore, reviewed once before it is applied.',
   -- surfaces EMPTY = visible on every surface. A book-scoped chat turn resolves the
   -- runtime surface key "book" (not "chat"), so a ['chat'] filter would hide this exact
   -- workflow on the turn that needs it. Empty means the registry surface filter is skipped.
   '{}'::text[], '{}'::jsonb,
   '[
     {"id":"see-standards","tool":"glossary_list_system_standards","gate":"none"},
     {"id":"adopt","tool":"glossary_adopt_standards","gate":"none"},
     {"id":"apply","tool":"glossary_confirm_action","gate":"confirm","inputs_map":{"confirm_token":"adopt.confirm_token"}},
     {"id":"read-back","tool":"glossary_book_ontology_read","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants to set up their book''s world/lore structure — "set up my world", "what should I track", "make me categories for my story". It creates the CATEGORIES a book tracks (internally: glossary kinds) — Characters, Locations, Cultivation/Power Systems, Organizations, Terms, and so on — NOT the individual people or terms (those come later, once the categories exist).\n\nCRITICAL ORDER — categories FIRST. Never try to add specific characters or terms before the categories exist: proposing an entity of a category that has not been created fails with "unknown kind" and you will loop. Follow the rail: (1) see the ready-made categories and genres, (2) adopt the ones that fit what the user described — this returns a confirmation to apply, it does not change anything yet, (3) the user confirms once and the categories are created, (4) read back and tell them, in plain words, what is now tracked.\n\nStep 2→3: glossary_adopt_standards returns a confirm_token; pass that exact token to glossary_confirm_action at step 3. Pick the genres that fit the story (e.g. a xianxia / cultivation / multi-world tale → the fantasy family plus the cultivation/power angle). If the user named a category the ready-made set lacks, you may add it with glossary_propose_kinds AFTER adopting — but adopt first.\n\nSPEAK PLAINLY the whole time. Say "categories", never "kinds"; "details to track", never "attributes". Never make the user type or understand a category code, a genre code, a token, or an id. At the confirm step, say in their words what you are about to set up — e.g. "I''ll set up Characters, Sects, Cultivation Systems, Techniques, Worlds, and Terms — apply this?" — and wait for their yes. If any step fails, stop and say plainly what did not work; never claim the world is set up when it is not.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W3 entity-triage — "clean up the suggestions": drain the review pile (keep the real
-- ones, throw out the junk, combine duplicates). The measured S03 failure was the agent
-- not triaging at all — it never listed the pile, or created new items during a cleanup.
-- The rail names list → keep/reject → merge → re-list so the pile visibly drains.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','entity-triage','Clean up a book''s suggested items',
   'Sort the AI-suggested items waiting for review — keep the real ones, throw out the junk, combine duplicates — until the pile is a clean, trustworthy list.',
   '{}'::text[], '{}'::jsonb,
   '[
     {"id":"see-pile","tool":"glossary_list_ai_suggestions","gate":"none"},
     {"id":"keep-and-reject","tool":"glossary_propose_status_change","gate":"confirm"},
     {"id":"merge-duplicates","tool":"glossary_propose_merge","gate":"confirm"},
     {"id":"recheck","tool":"glossary_list_ai_suggestions","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants to clean up / tidy / sort the suggested items in their book — "clean up the suggestions", "keep the good ones", "these are junk", "these two are the same person", "how many are left". The suggested items are the AI-proposed entries awaiting review (internally: draft entities tagged ai-suggested). The job: keep the real ones, throw out the junk, and combine duplicates, so the pile drains to a clean list the user trusts.\n\nEXACTLY WHICH TOOL DOES WHAT — use these, and ONLY these, for the cleanup:\n- glossary_list_ai_suggestions — show the pile. Each item comes back with its entity_id; you will pass those ids to the tools below. Never ask the user for an id.\n- glossary_propose_status_change — KEEP or THROW OUT items, in BATCHES. To keep: call it once with status="active" and entity_ids = all the real ones. To throw out: call it once with status="rejected" and entity_ids = all the junk ones. One confirmation covers the whole batch.\n- glossary_propose_merge — COMBINE duplicates. Call it with winner_id = the one entry to keep and loser_ids = the other entries that are the same thing (they must be the same category). The losers fold into the winner.\n- glossary_propose_reassign_kind — only if an item is filed under the wrong category (uncommon).\nDo NOT use glossary_propose_entity_edit or any rename/edit tool to keep, throw out, or combine — editing a name or a field is NOT triage and will not drain the pile. Renaming "Dracula" to "Count Dracula" does not merge them; use glossary_propose_merge. Do NOT create new items — this is a cleanup.\n\nRail: (1) list the pile and tell the user in plain terms what is there — how many, which look like real people/places, which look empty or junk, which look like the same thing twice; (2) keep the real ones (status_change → active) and throw out the junk (status_change → rejected); (3) combine duplicates (merge winner + losers); (4) list the pile again so the user SEES it shrank, and give an honest count.\n\nSPEAK PLAINLY to the user: say "suggestions" or "items", never "entities"/"drafts"; "keep"/"throw out"/"combine", never "status change"/"reject"/"merge candidate". Give honest counts (e.g. "kept 4, threw out 2, combined 2 into 1 — 5 left"), and never say the pile is clean while items still remain.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W2 (agent-discoverability WS-5) — populate-from-seed-doc. The user pastes freeform notes
-- (their cast, places, powers, terms) and wants them turned into real, reviewable glossary
-- entries. All backing tools verified present in the live catalog 2026-07-12 (grepped, not
-- trusted from the audit): glossary_extract_entities_from_doc (sync) + glossary_propose_
-- entities (sync, mints the review drafts). done_when "cast > 0" grounds save on the SSOT.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','populate-from-notes','Turn pasted notes into glossary entries',
   'Take a chunk of notes the user pastes — their characters, places, powers, terms — and turn it into real, reviewable entries in the book''s glossary.',
   '{book,editor}'::text[], '{}'::jsonb,
   '[
     {"id":"read-back","tool":"glossary_book_ontology_read","gate":"none"},
     {"id":"extract","tool":"glossary_extract_entities_from_doc","gate":"none","async_job":false},
     {"id":"save","tool":"glossary_propose_entities","gate":"none","done_when":"cast > 0"}
   ]'::jsonb,
   E'Use this when the user PASTES notes and wants them captured — "here are my characters", "add these to the glossary", "turn my notes into entries". The job: read their notes, pull out the people/places/powers/terms, and save them as review drafts the user can then approve.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- glossary_book_ontology_read — first, see which CATEGORIES the book already has, so each item you save is filed under a category that exists. If the book has no categories yet, set those up first (that is a different job — the world-setup recipe).\n- glossary_extract_entities_from_doc — feed it the user''s notes VERBATIM (paste exactly what they wrote). It returns candidate items with a suggested category + attributes. It writes nothing.\n- glossary_propose_entities — save the candidates. Each item''s category MUST be one the book already has (from the ontology read). They are saved as review drafts, not canon — there is no separate confirm step.\n\nORDER MATTERS: read the categories BEFORE saving, or a save under a category that does not exist fails with "unknown kind" and you will loop.\n\nSPEAK PLAINLY: say "entries" or "items", never "entities"; "categories", never "kinds"/"ontology". After saving, tell the user in plain words what landed ("saved 6 characters and 2 places as drafts for you to review") — and never claim something saved that did not.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W4 (agent-discoverability WS-5) — build the knowledge graph from a populated glossary.
-- Backing tools verified present 2026-07-12: kg_project_create (sync) + kg_project_entities_
-- to_nodes (sync) + kg_build_graph (ASYNC — starts an extraction job; the async_job flag
-- tells the agent to watch it, not treat it done on return). done_when "connections > 0"
-- grounds the projection on the SSOT.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','kg-build','Map how the cast connects',
   'Take a book that already has its cast in the glossary and build the connection map — who relates to whom, what belongs where — so relationships can be tracked and explored.',
   '{book,editor}'::text[], '{}'::jsonb,
   '[
     {"id":"read-back","tool":"glossary_book_ontology_read","gate":"none"},
     {"id":"make-space","tool":"kg_project_create","gate":"none"},
     {"id":"place-cast","tool":"kg_project_entities_to_nodes","gate":"none","done_when":"connections > 0"},
     {"id":"build","tool":"kg_build_graph","gate":"none","async_job":true}
   ]'::jsonb,
   E'Use this when the book already HAS its cast recorded and the user wants to see how it connects — "map the relationships", "build the knowledge graph", "how does everyone connect". The job: create the connection space, put the recorded cast into it as nodes, then build the graph over it.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- glossary_book_ontology_read — first, confirm the book actually has cast recorded. If the glossary is empty there is nothing to connect: say so and offer to capture the cast first (a different job). Never build a graph over an empty glossary.\n- kg_project_create — create (or get) the connection space that anchors this book''s graph. Idempotent — safe if it already exists.\n- kg_project_entities_to_nodes — place the book''s recorded glossary entries into the space as nodes. This is what makes "connections" exist.\n- kg_build_graph — start building the graph over those nodes. This is a BACKGROUND job: it is NOT done when the tool returns. Watch it, and never tell the user the map is ready before you have seen the job finish.\n\nORDER MATTERS: make the space, then place the cast, then build — building before the cast is placed produces an empty graph.\n\nSPEAK PLAINLY: say "connection map" or "how they connect", never "knowledge graph"/"nodes"/"projection". Tell the user what happened in their terms ("placed your 12 characters and started mapping how they connect — I will tell you when it finishes"), and never claim the map is built before the job actually completes.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- the flagship vision-to-book rail — THE FLAGSHIP SPINE (S06). "I have a story in my head, help me
-- write it": turn a told vision into a real foundation — world categories, the cast,
-- how they connect, and an arc plan. This is the rail the write-mode binding PINS, so
-- the steps sit in context from turn 1. The measured S06 failure was not a missing
-- tool: glossary-bootstrap was advertised and the steering directive injected, and the
-- agent STILL improvised (find_tools -> plan_propose_spec) because the user never ASKED
-- ("yeah do it" — an assent to the agent's OWN offer). A pinned rail removes the need
-- for the model to recognise a workflow at all. surfaces {book,editor}: a bookless chat
-- turn must never carry a book-building rail.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','vision-to-book','Turn a story idea into a real book foundation',
   'Take a story the user is describing and build its foundation — the world''s categories, the cast and key terms, how they connect, and a chapter-by-chapter plan — then draft the opening.',
   '{book,editor}'::text[], '{}'::jsonb,
   '[
     {"id":"see-standards","tool":"glossary_list_system_standards","gate":"none"},
     {"id":"adopt-categories","tool":"glossary_adopt_standards","gate":"none"},
     {"id":"apply-categories","tool":"glossary_confirm_action","gate":"confirm","inputs_map":{"confirm_token":"adopt-categories.confirm_token"},"done_when":"categories > 0"},
     {"id":"read-back","tool":"glossary_book_ontology_read","gate":"none"},
     {"id":"capture-cast","tool":"glossary_extract_entities_from_doc","gate":"none","async_job":false},
     {"id":"save-cast","tool":"glossary_propose_entities","gate":"none","done_when":"cast > 0"},
     {"id":"connect-project","tool":"kg_project_create","gate":"none"},
     {"id":"connect-people","tool":"kg_project_entities_to_nodes","gate":"none","done_when":"connections > 0"},
     {"id":"arc-plan","tool":"plan_propose_spec","gate":"none","async_job":true,"done_when":"plan > 0"},
     {"id":"draft-opening","tool":"book_chapter_create","gate":"none","done_when":"chapters > 0"},
     {"id":"write-opening","tool":"book_chapter_save_draft","gate":"none","done_when":"prose > 0"}
   ]'::jsonb,
   E'Use this whenever the user is BUILDING their book — telling you their story idea, their world, their characters — and wants it to become something real. It also covers the case where YOU offered to do this and they simply agreed ("yeah", "do it", "sure", "go ahead"): their yes refers to your offer, so run this rail rather than inventing your own sequence.\n\nWHAT IT DOES, in the user''s terms: (1) sets up the CATEGORIES their world tracks (characters, places, power systems, factions, terms), (2) captures the CAST and key terms they have told you about, (3) records HOW THEY CONNECT, (4) turns the story into a chapter-by-chapter PLAN, (5) drafts the opening.\n\nORDER IS LOAD-BEARING — categories BEFORE cast. Proposing a character before its category exists fails with "unknown kind" and you will loop. Never skip ahead to the plan just because it looks like the flashier tool: a plan with no world behind it leaves the user with nothing they can open and read.\n\nStep by step:\n- see-standards / adopt-categories / apply-categories: look at the ready-made categories, adopt the ones that fit what they described (a cultivation/xianxia tale wants Characters, Sects/Organizations, Cultivation Systems, Techniques, Worlds, Terms), then the user confirms ONCE and the categories are created. adopt returns a confirm_token — pass that exact token to glossary_confirm_action.\n- read-back: tell them, in plain words, what is now tracked.\n- capture-cast: feed glossary_extract_entities_from_doc the story AS THE USER TOLD IT (paste what they said — their own description of the people, places, and powers). It returns candidates.\n- save-cast: save the candidates with glossary_propose_entities (their category must be one you just created). They are saved as review drafts immediately — there is no separate confirm for the cast.\n- connect-project / connect-people: create the connections space and put the cast into it, so relationships can be tracked.\n- arc-plan: propose the story plan. This is a BACKGROUND job — it is NOT done when the tool returns. Watch it, and never tell the user the plan is ready before you have seen it finish.\n- draft-opening / write-opening: create the first chapter and save its draft prose. book_chapter_save_draft needs the version returned when the chapter was created.\n\nIf a step fails, STOP and say plainly what did not work. Never claim their world/plan/chapter exists when it does not.\n\nDO NOT NARRATE THE STEPS — RUN THEM. Saying "first I will look at the categories, then I will save them" is not doing it; it leaves the user with nothing. When a step is due, CALL its tool in the same turn, then tell them what CHANGED. Chain the steps you can rather than doing one and waiting to be asked again.

SPEAK PLAINLY — this is the whole point. The user is a novelist, not an engineer. NEVER say to them: workflow, vision-to-book, glossary, ontology, entity, kind, attribute, schema, spec, NovelSystemSpec, PlanForge, pipeline, engine, job, token, or any tool name. This recipe is PRIVATE — never tell them you are running it or name it. Say instead: "the things your world tracks", "your cast", "the categories", "your story plan", "your opening chapter". Narrate what is happening to THEIR STORY, never what is happening to the system.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W5 (agent-discoverability WS-5) — translation-pass. "Keep my translation current." The audit's
-- translation_run/canon_check names were WRONG (verified 2026-07-12: they do not exist); the
-- REAL tools are translation_coverage (sync, reports what is untranslated/stale) + translation_
-- retranslate_dirty (ASYNC — enqueues the re-translation of the stale/missing units). No probe
-- artifact tracks translation, so these steps are call-verified (no done_when), exactly like a read.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','translation-pass','Translate what is new or changed',
   'Look at what in the book is not yet translated (or has changed since it was), and bring the translation up to date.',
   '{book,editor}'::text[], '{}'::jsonb,
   '[
     {"id":"assess","tool":"translation_coverage","gate":"none"},
     {"id":"translate","tool":"translation_retranslate_dirty","gate":"none","async_job":true}
   ]'::jsonb,
   E'Use this when the user wants the translation brought up to date — "translate the new chapters", "update the translation", "what still needs translating". The job: see what is missing or out of date, then translate exactly those parts.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- translation_coverage — first, see what is untranslated or has drifted since it was last translated. This reads only; it changes nothing. Tell the user plainly what it found ("3 chapters have no translation yet, and 1 changed since it was translated").\n- translation_retranslate_dirty — translate exactly those out-of-date parts. This is a BACKGROUND job: it is NOT done when the tool returns. Watch it, and never tell the user the translation is finished before you have seen the job complete.\n\nORDER MATTERS: check coverage first, so you translate only what actually needs it instead of re-translating the whole book.\n\nSPEAK PLAINLY: say "translation" and "chapters", never "coverage"/"dirty units"/"retranslate job". Tell the user what changed in their terms ("started translating the 3 new chapters — I will tell you when it is done"), and never claim it finished before the job actually completes.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W9 (agent-discoverability WS-5) — canon-check. "Does my story stay consistent?" Real tools
-- (verified 2026-07-12): composition_list_canon_rules (sync) + composition_conformance_run (ASYNC —
-- a background check, poll with composition_get_mine_job) + composition_conformance_status (sync,
-- reads the result). No probe artifact for consistency, so the steps are call-verified.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','canon-check','Check the story for contradictions',
   'Check the book against the consistency rules it has recorded — names, timelines, established facts — and report what does not line up.',
   '{book,editor,studio}'::text[], '{}'::jsonb,
   '[
     {"id":"see-rules","tool":"composition_list_canon_rules","gate":"none"},
     {"id":"check","tool":"composition_conformance_run","gate":"none","async_job":true},
     {"id":"results","tool":"composition_conformance_status","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants to know whether the story holds together — "check for contradictions", "does this stay consistent", "did I break continuity". The job: run the book against its recorded consistency rules and tell the user, plainly, what conflicts.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- composition_list_canon_rules — first, see which consistency rules the book actually has. If there are none, say so and offer to set some up (a different job); never report "all consistent" when nothing was checked.\n- composition_conformance_run — run the check. This is a BACKGROUND job: it is NOT done when the tool returns. Watch it (poll composition_get_mine_job) and do not report results before it finishes.\n- composition_conformance_status — read the finished result and summarise the real conflicts.\n\nORDER MATTERS: confirm there are rules to check against BEFORE running, or a clean result is meaningless.\n\nSPEAK PLAINLY: say "consistency rules" and "contradictions", never "canon rules"/"conformance run"/"job". Tell the user what was found in their terms ("checked against your 8 rules — two things conflict: ...") and never claim it is consistent before the check has actually run.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W6 (agent-discoverability WS-5) — chapter-compose. "Write this chapter." Real tools (verified
-- 2026-07-12): composition_get_outline_node (sync, reads what the chapter is meant to cover) +
-- book_get_chapter (sync, reads the target chapter + its current draft_version) + book_chapter_
-- save_draft (sync, writes the chapter's draft text). The write step is book_chapter_save_draft ON
-- PURPOSE — composition_write_prose is a DEPRECATED, discovery-hidden thin proxy over it, so the
-- rail must name the ONE canonical chapter-write tool. NO done_when on the draft step: the probe's
-- "prose" is a BOOK-LEVEL absolute count, so on this rail's own use case (drafting a chapter of a
-- book that ALREADY has written chapters) prose>0 is already true and the rail would declare itself
-- done without drafting anything (the absolute-count-vs-per-item trap the /review-impl caught). The
-- grammar has no per-chapter prose predicate, so the step is call-verified — safe here because
-- book_chapter_save_draft is sync and returns new_draft_version on success (no silent-success).
-- book_get_chapter is REQUIRED before the write: save_draft hard-needs the chapter's own
-- draft_version as base_version, which the outline node (a DIFFERENT entity) does not carry.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','chapter-compose','Draft this chapter',
   'Take a chapter that has a place in the plan and write its opening draft, following what the plan says the chapter should cover.',
   '{book,editor,studio}'::text[], '{}'::jsonb,
   '[
     {"id":"outline","tool":"composition_get_outline_node","gate":"none"},
     {"id":"get-chapter","tool":"book_get_chapter","gate":"none"},
     {"id":"draft","tool":"book_chapter_save_draft","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants a specific chapter written — "draft chapter 3", "write this next part", "put down a first version of this scene". The job: read what the chapter is meant to cover, read the chapter itself, then write its draft.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- composition_get_outline_node — first, read what this chapter is meant to cover (its place in the plan). If the chapter has no place in the plan yet, say so and offer to plan it first; do not invent a chapter with no anchor.\n- book_get_chapter — read the target chapter to get its CURRENT draft version. You MUST pass that chapter''s own draft_version as base_version to the next step — NOT the outline''s version (they are different things); passing the wrong one fails with a version conflict.\n- book_chapter_save_draft — write the DRAFT text for the chapter, using the draft_version you just read. It saves a draft, not a published chapter, and returns the new version on success.\n\nORDER MATTERS: read the plan, then read the chapter for its version, THEN draft — skipping the chapter read leaves you guessing the version and the save fails.\n\nSPEAK PLAINLY: say "chapter" and "draft", never "outline node"/"draft version"/"compose". Tell the user what happened in their terms ("drafted the opening of chapter 3 — have a read and tell me what to change") and never claim a chapter is written before its text is saved.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W7 (agent-discoverability WS-5) — build-a-book. "Plan my whole book." Real tools (verified
-- 2026-07-12): plan_propose_spec (mode=llm ASYNC — proposes the arc plan) + composition_arc_suggest
-- (sync) + composition_outline_node_create (sync, builds the chapter outline). done_when "plan > 0"
-- grounds the plan step on the SSOT.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','build-a-book','Turn the idea into a book plan',
   'Take a book that has its world and cast and turn it into a real plan — the story arc and a chapter-by-chapter outline the user can build from.',
   '{book,editor,studio}'::text[], '{}'::jsonb,
   '[
     {"id":"plan","tool":"plan_propose_spec","gate":"none","async_job":true,"done_when":"plan > 0"},
     {"id":"arcs","tool":"composition_arc_suggest","gate":"none"},
     {"id":"outline","tool":"composition_outline_node_create","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants their book structured — "plan the whole book", "how should the story go", "give me a chapter outline". The job: propose the story plan, shape its arcs, and lay out the chapters.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- plan_propose_spec — propose the overall plan for the book. This is a BACKGROUND job when it runs the model: it is NOT done when the tool returns. Watch it, and do not present the plan before it has actually finished. done_when the plan exists.\n- composition_arc_suggest — suggest the story arcs the plan implies (the rise, the turn, the resolution).\n- composition_outline_node_create — lay out the chapters as an outline the user can open and build from.\n\nORDER MATTERS: propose the plan first, then its arcs, then the chapter outline — an outline with no plan behind it leaves the user with a list and no story.\n\nSPEAK PLAINLY: say "plan", "arcs", "chapters", never "spec"/"outline node"/"job". Tell the user what happened in their terms ("here is the shape of the book — three arcs across twelve chapters") and never claim the plan is ready before the job has actually completed.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- W12 (agent-discoverability WS-5) — autonomous-drafting. "Draft the next chapters for me." Real
-- tools (verified 2026-07-12): composition_authoring_run_create (sync, sets up the run OVER AN
-- APPROVED PLAN — needs a plan_run_id, so an approved plan must exist first) + composition_
-- authoring_run_start (COST-GATED — returns a confirm_token, SPENDS tokens; ASYNC server-side
-- driver that drafts chapters) + composition_authoring_run_get (sync, watch progress). gate stays
-- "none" — the cost-gate/confirm suspension is intrinsic to the start tool, exactly like the
-- flagship's paid steps. NO done_when: the drafted units land in the run and become book "prose"
-- only on acceptance, and prose is a book-level absolute count anyway (already >0 on a non-empty
-- book — same trap as W6), so every step is call-verified and the async watch step is the honest
-- completion signal, not a probe artifact.
INSERT INTO workflows (tier, slug, title, description, surfaces, inputs, steps, notes_md, status, source) VALUES
  ('system','autonomous-drafting','Draft the next chapters for me',
   'Set the book drafting itself chapter by chapter, on its own, pausing where the user wants to review — for a user who wants the draft to move forward without steering every line. Needs a story plan already in place.',
   '{book,editor,studio}'::text[], '{}'::jsonb,
   '[
     {"id":"set-up","tool":"composition_authoring_run_create","gate":"none"},
     {"id":"draft","tool":"composition_authoring_run_start","gate":"none","async_job":true},
     {"id":"watch","tool":"composition_authoring_run_get","gate":"none"}
   ]'::jsonb,
   E'Use this when the user wants the book to keep drafting on its own — "just write the next few chapters", "draft ahead", "keep going without me". The job: set up the run, start it (it SPENDS money, so the user must approve first), and watch it draft.\n\nPREREQUISITE: this drafts from an approved story plan. If the book has no plan yet, STOP and offer to plan it first (the plan rail) — do not start a drafting run with nothing to draft from.\n\nEXACTLY WHICH TOOL DOES WHAT:\n- composition_authoring_run_create — set up the run over the approved plan: which chapters, and whether to pause after each for review. Nothing drafts yet.\n- composition_authoring_run_start — start the drafting. This SPENDS money and asks the user to approve before anything runs — never claim it started before that approval lands. It is a BACKGROUND process that drafts chapter after chapter; it is NOT done when the tool returns.\n- composition_authoring_run_get — watch the progress and tell the user what has been drafted so far. A drafted part becomes part of the book only once it is accepted.\n\nORDER MATTERS: set up, then get approval to start, then watch — never start spending before the user has said yes.\n\nSPEAK PLAINLY: say "drafting", "chapters", "pause to review", never "authoring run"/"units"/"tokens"/"job". Tell the user what is happening in their terms ("drafting chapters 4 through 8 now, pausing after each so you can read them") and never claim chapters are written before their text is actually saved.',
   'published','system')
ON CONFLICT (slug) WHERE tier = 'system' DO UPDATE SET
  title = EXCLUDED.title, description = EXCLUDED.description, surfaces = EXCLUDED.surfaces,
  inputs = EXCLUDED.inputs, steps = EXCLUDED.steps, notes_md = EXCLUDED.notes_md,
  status = EXCLUDED.status, updated_at = now();

-- WS-3 (C6, agent-discoverability spec) — MODE -> CAPABILITY BINDING. A mode is not just
-- a nudge: it selects a capability PROFILE (which skills are injected, which workflows are
-- PINNED into context, which tool categories are hot-seeded). Same 3-tier tenancy as
-- workflows/skills: System (admin-seeded default), per-user, per-book. The effective
-- binding is the UNION of the three tiers, minus disable_workflows (the opt-out escape
-- hatch — a union alone would leave a user unable to turn OFF a System pin, which would
-- make this a global env-flag masquerading as a user setting).
CREATE TABLE IF NOT EXISTS mode_bindings (
  binding_id UUID PRIMARY KEY DEFAULT uuidv7(),
  tier TEXT NOT NULL CHECK (tier IN ('system','user','book')),
  owner_user_id UUID,
  book_id UUID,
  mode TEXT NOT NULL CHECK (mode IN ('ask','write','plan')),
  inject_skills TEXT[] NOT NULL DEFAULT '{}',
  inject_workflows TEXT[] NOT NULL DEFAULT '{}',      -- PINNED: rail rendered into context, step tools pre-activated
  seed_tool_categories TEXT[] NOT NULL DEFAULT '{}',
  disable_workflows TEXT[] NOT NULL DEFAULT '{}',     -- subtractive opt-out, applied LAST
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT mode_bindings_scope_key CHECK (
    (tier = 'system' AND owner_user_id IS NULL AND book_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL AND book_id IS NULL) OR
    (tier = 'book'   AND book_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_mode_bindings_owner ON mode_bindings(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_mode_bindings_book ON mode_bindings(book_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mode_bindings_system ON mode_bindings(mode) WHERE tier = 'system';
CREATE UNIQUE INDEX IF NOT EXISTS uq_mode_bindings_user   ON mode_bindings(owner_user_id, mode) WHERE tier = 'user';
CREATE UNIQUE INDEX IF NOT EXISTS uq_mode_bindings_book   ON mode_bindings(book_id, mode) WHERE tier = 'book';

-- System defaults. plan: generalizes the hardcoded plan->plan_forge (the hardcode STAYS in
-- chat-service as the degrade-safe fallback when the registry is unreachable). write: pins
-- the flagship rail, so a user who never names a workflow still runs on one.
INSERT INTO mode_bindings (tier, mode, inject_skills, inject_workflows) VALUES
  ('system','plan',  '{plan_forge}'::text[], '{}'::text[]),
  ('system','write', '{}'::text[],           '{vision-to-book}'::text[])
ON CONFLICT (mode) WHERE tier = 'system' DO UPDATE SET
  inject_skills = EXCLUDED.inject_skills,
  inject_workflows = EXCLUDED.inject_workflows,
  seed_tool_categories = EXCLUDED.seed_tool_categories,
  updated_at = now();
`

// Up applies the schema. Idempotent; safe to run on every boot.
func Up(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, schemaSQL)
	return err
}
