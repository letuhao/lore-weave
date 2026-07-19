import asyncpg

DDL = """
CREATE TABLE IF NOT EXISTS chat_sessions (
  session_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id     UUID NOT NULL,
  title             VARCHAR(255) NOT NULL DEFAULT 'New Chat',
  model_source      VARCHAR(20) NOT NULL,
  model_ref         UUID NOT NULL,
  system_prompt     TEXT,
  generation_params JSONB NOT NULL DEFAULT '{}',
  status            VARCHAR(20) NOT NULL DEFAULT 'active',
  message_count     INT NOT NULL DEFAULT 0,
  last_message_at   TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner
  ON chat_sessions (owner_user_id, status, last_message_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  message_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  session_id        UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
  owner_user_id     UUID NOT NULL,
  role              VARCHAR(20) NOT NULL,
  content           TEXT NOT NULL,
  content_parts     JSONB,
  sequence_num      INT NOT NULL,
  input_tokens      INT,
  output_tokens     INT,
  model_ref         UUID,
  usage_log_id      UUID,
  is_error          BOOLEAN NOT NULL DEFAULT false,
  error_detail      TEXT,
  branch_id         INT NOT NULL DEFAULT 0,
  parent_message_id UUID REFERENCES chat_messages(message_id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, sequence_num, branch_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
  ON chat_messages (session_id, sequence_num);

-- WS-3.5 / C7 (SD-C7) — who INITIATED a message. 'user' (the default, every existing + interactive
-- message) vs 'assistant_proactive' (a message the assistant started on its own — the weekly reflection
-- or a proactive nudge, never in reply to a user turn). Lets the FE badge a proactive turn and lets
-- analytics separate assistant-initiated from user-initiated spend/engagement. Additive, default 'user'.
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS initiated_by TEXT NOT NULL DEFAULT 'user'
  CHECK (initiated_by IN ('user', 'assistant_proactive'));

CREATE TABLE IF NOT EXISTS chat_outputs (
  output_id         UUID PRIMARY KEY DEFAULT uuidv7(),
  message_id        UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id        UUID NOT NULL,
  owner_user_id     UUID NOT NULL,
  output_type       VARCHAR(20) NOT NULL,
  title             VARCHAR(255),
  content_text      TEXT,
  language          VARCHAR(50),
  storage_key       VARCHAR(512),
  mime_type         VARCHAR(100),
  file_name         VARCHAR(255),
  file_size_bytes   BIGINT,
  metadata          JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_outputs_session
  ON chat_outputs (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_outputs_owner
  ON chat_outputs (owner_user_id, output_type, created_at DESC);

-- Phase 6: Message branching
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_messages' AND column_name='branch_id') THEN
    ALTER TABLE chat_messages ADD COLUMN branch_id INT NOT NULL DEFAULT 0;
    -- Replace old UNIQUE constraint (session_id, sequence_num) with branched version
    ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_session_id_sequence_num_key;
    ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_session_id_sequence_num_branch_id_key;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_branch_unique ON chat_messages(session_id, sequence_num, branch_id);
  END IF;
END $$;

-- Phase 6: Full-text search index for message search
CREATE INDEX IF NOT EXISTS idx_chat_messages_fts
  ON chat_messages USING gin(to_tsvector('english', content));

-- Phase 6: Chat Enhancement migrations (idempotent)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='generation_params') THEN
    ALTER TABLE chat_sessions ADD COLUMN generation_params JSONB NOT NULL DEFAULT '{}';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='is_pinned') THEN
    ALTER TABLE chat_sessions ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT false;
  END IF;
END $$;

-- Voice Pipeline V2: Audio segments for TTS replay
CREATE TABLE IF NOT EXISTS message_audio_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id UUID NOT NULL,
  user_id UUID NOT NULL,
  segment_index INT NOT NULL,
  object_key TEXT NOT NULL,
  sentence_text TEXT NOT NULL,
  duration_s REAL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (message_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_mas_message ON message_audio_segments(message_id);
CREATE INDEX IF NOT EXISTS idx_mas_user ON message_audio_segments(user_id);
CREATE INDEX IF NOT EXISTS idx_mas_cleanup ON message_audio_segments(created_at);

-- Knowledge Service K1: project link on chat_sessions
-- No FK (knowledge_projects lives in loreweave_knowledge, different DB).
-- Validated in application code when a session is assigned to a project.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='project_id') THEN
    ALTER TABLE chat_sessions ADD COLUMN project_id UUID;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_project
  ON chat_sessions(project_id) WHERE project_id IS NOT NULL;

-- Track B B1(2) — multi-KG: a session may ground on a SET of knowledge projects
-- (world + member books) unioned into one context block. `project_ids` is the
-- ordered set; the legacy single `project_id` stays for back-compat + tool scope.
-- No FK (knowledge_projects lives in loreweave_knowledge). Empty/NULL ⇒ the
-- legacy single-project (or no-project) path. Validated by knowledge-service on
-- context build (unknown ids are owner-scoped-filtered, not fatal).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='project_ids') THEN
    ALTER TABLE chat_sessions ADD COLUMN project_ids UUID[] NOT NULL DEFAULT '{}';
  END IF;
END $$;

-- A2A phase-2 — optional "composer" model for in-turn prose delegation. When
-- set, the orchestrator (session model) may call the server-side compose_prose
-- tool, which streams THIS model to generate prose and returns it as the tool
-- result. NULL → compose_prose is not advertised (single-model behaviour).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='composer_model_ref') THEN
    ALTER TABLE chat_sessions ADD COLUMN composer_model_source VARCHAR(20);
    ALTER TABLE chat_sessions ADD COLUMN composer_model_ref UUID;
  END IF;
END $$;

-- D-PLAN-PLANNER-DEFAULT-FE phase 2 — optional per-session PLANNER model. When set,
-- chat-service injects this model_ref into the agent's glossary_plan call so planning
-- uses a session-chosen model instead of the per-user provider-registry default. NULL →
-- the planner resolves its model the usual way (planner default → chat fallback).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='planner_model_ref') THEN
    ALTER TABLE chat_sessions ADD COLUMN planner_model_source VARCHAR(20);
    ALTER TABLE chat_sessions ADD COLUMN planner_model_ref UUID;
  END IF;
END $$;

-- K13.1 — outbox_events: transactional outbox for event-driven pipeline.
-- Matches book-service schema so worker-infra outbox-relay can pick up
-- events uniformly. Worker-infra publishes to Redis Stream
-- `loreweave:events:{aggregate_type}` and inserts into loreweave_events.event_log.
CREATE TABLE IF NOT EXISTS outbox_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'chat',
  aggregate_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox_events(created_at) WHERE published_at IS NULL;

-- K21-B — per-message tool-call history (JSONB) for UI replay. NULL when
-- the turn made no tool calls; otherwise an ordered list of
-- {iteration, tool, args, ok, result|error} entries.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_messages' AND column_name='tool_calls') THEN
    ALTER TABLE chat_messages ADD COLUMN tool_calls JSONB;
  END IF;
END $$;

-- Chat Quality Wave W1 — per-turn context-breakdown frame persisted on the
-- assistant message ({used_tokens, context_length, effective_limit, pct,
-- until_compact_pct, breakdown:{category: tokens}, baseline_tokens}) so the
-- per-category context history of a session is traceable after the fact.
-- NULL on rows written before W1 (and user rows).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_messages' AND column_name='context_breakdown') THEN
    ALTER TABLE chat_messages ADD COLUMN context_breakdown JSONB;
  END IF;
END $$;

-- Provider Context Strategy §5 (Phase 2) — the stateful /v1/responses CHAIN HEAD.
-- Set on an assistant row produced by a stateful turn; the "current head" for a
-- (session, branch) is simply the latest assistant message carrying a non-NULL
-- response_id, so branching (E7) and re-chain (E5) fall out for free — no separate
-- table. NULL on stateless turns and all pre-migration rows (⇒ start a fresh chain).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_messages' AND column_name='response_id') THEN
    ALTER TABLE chat_messages ADD COLUMN response_id TEXT;
  END IF;
END $$;

-- Chain-head lookup: newest non-NULL response_id per (session, branch). Partial index
-- keeps it tiny (only stateful rows) and the DESC matches the ORDER BY sequence_num DESC.
CREATE INDEX IF NOT EXISTS idx_chat_messages_chain_head
  ON chat_messages (session_id, branch_id, sequence_num DESC)
  WHERE response_id IS NOT NULL;

-- Chat Quality Wave W3 — manual steerable compact, PERSISTED on the session
-- (PO decision #2: multi-device consistent, unlike the per-turn ephemeral
-- auto-compaction). `compact_summary` is the LLM synopsis of every message
-- with sequence_num < `compacted_before_seq`; the history loader splices
-- summary + post-seq messages. NULL compacted_before_seq = never compacted.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='compact_summary') THEN
    ALTER TABLE chat_sessions ADD COLUMN compact_summary TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='compacted_before_seq') THEN
    ALTER TABLE chat_sessions ADD COLUMN compacted_before_seq INT;
  END IF;
END $$;

-- WS-1.6 (spec 05 §Q7) — the per-turn capture decision, PERSISTED so the assistant home
-- strip can show capture visibly ON or OFF *with a reason* ({"fire": bool, "reason": str}).
-- The decision was computed + logged every turn but discarded by the caller; a status that is
-- computed-but-not-surfaced is exactly the silent-no-op "collecting" chip this repo shipped
-- twice. NULL until the first post-turn write.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='capture_status') THEN
    ALTER TABLE chat_sessions ADD COLUMN capture_status JSONB;
  END IF;
END $$;

-- WS-1.8 / sealed decision T-4 (spec 02 §Q1) — the ASSISTANT-SESSION DISCRIMINATOR. An EXPLICIT
-- column, not a book_id=diary derivation: three consumers key off it (the day-window read, the
-- voice-disable gate, and chat_search scoping), and an explicit flag is self-describing where a
-- book_id overload is implicit (and would misfire for a future coach session that is assistant-
-- family but not diary-bound). 'chat' = a normal/roleplay/interview session (the default for every
-- existing row); 'assistant' = a Work Assistant session (stamped at create by WS-1.10). Closed set.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='session_kind') THEN
    ALTER TABLE chat_sessions ADD COLUMN session_kind TEXT NOT NULL DEFAULT 'chat'
      CHECK (session_kind IN ('chat','assistant'));
  END IF;
END $$;
-- The assistant-session lookups (day-window read · voice gate · search scoping) — a partial index
-- since 'assistant' rows are a small minority of all sessions.
CREATE INDEX IF NOT EXISTS idx_chat_sessions_assistant
  ON chat_sessions (owner_user_id) WHERE session_kind = 'assistant';

-- WS-1.8 / DBT-11 (spec 01) — chat_messages.local_date: the LOCAL calendar day a message
-- belongs to, stamped at write-time so the distiller can bucket "one day's" messages without
-- re-deriving the day later (which would let a timezone change silently re-bucket history).
-- D-R14: populated SERVER-side from the user's prefs.timezone with a UTC fallback. This
-- migration adds the column + the UTC-fallback DEFAULT for new rows; the timezone-aware
-- override (resolve prefs.timezone in the message-write path) is the follow-up. Existing rows
-- stay NULL (no wrong backfill to today's date). The only reader (the day-window query) filters
-- `local_date = $day` with STRICT equality, so a legacy NULL row is simply EXCLUDED — correct here:
-- those pre-column rows predate the assistant and are never diary-session messages (the reader also
-- scopes to s.book_id = the diary), and new diary messages always carry the default. (A future
-- reader that must include legacy rows would add COALESCE(local_date, created_at::date); the
-- day-window read deliberately does NOT — there is no missing diary data to fall back for.)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_messages' AND column_name='local_date') THEN
    ALTER TABLE chat_messages ADD COLUMN local_date DATE;
    ALTER TABLE chat_messages ALTER COLUMN local_date SET DEFAULT ((now() AT TIME ZONE 'UTC')::date);
  END IF;
END $$;

-- The distiller's per-day query: a user's messages for one local day, newest last.
CREATE INDEX IF NOT EXISTS idx_chat_messages_local_date
  ON chat_messages (owner_user_id, local_date, sequence_num) WHERE local_date IS NOT NULL;

-- WS-2.9 (spec 09 §Q6) — the per-turn "don't remember this" escape hatch. When a user turns grounding
-- OFF for a turn, that turn must not be captured in real time (already true) AND must not be distilled
-- into the diary (the leak this closes — the distiller read the whole day regardless). A message flagged
-- here is EXCLUDED from the day-window read. DEFAULT false keeps every existing message rememberable.
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS exclude_from_memory BOOLEAN NOT NULL DEFAULT false;

-- DBT-CHAT-PERSIST — how the assistant turn ENDED, so a turn that did not finish
-- cleanly is still shown (with a badge) instead of vanishing. Previously the
-- assistant row was written ONLY on a clean finish, so an error, a user
-- interrupt (client disconnect), or an abandoned/expired frontend-tool suspend
-- lost the whole streamed reply. NULL = legacy/complete rows; 'stop' = clean;
-- 'error' = threw mid-stream (pairs with is_error); 'interrupted' = user stopped
-- or the suspended run was abandoned/expired. `is_error`/`error_detail` already
-- exist for the error half.
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS finish_reason TEXT;

-- ARCH-1 C6 — suspended runs for AG-UI frontend-tool-calls. When the model
-- calls a frontend tool (e.g. propose_edit), the turn pauses: the in-flight
-- conversation `working` list + the dangling assistant tool-call cannot be
-- rebuilt from chat_messages (the assistant row isn't written until end-of-
-- turn), so the whole state is persisted here keyed by run_id. The resume
-- endpoint rehydrates it, appends the tool result, and runs a 2nd LLM pass.
-- Rows are deleted on resume; an `expires_at` sweep reclaims abandoned ones.
CREATE TABLE IF NOT EXISTS chat_suspended_runs (
  run_id            UUID PRIMARY KEY,
  session_id        UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
  owner_user_id     UUID NOT NULL,
  -- the assistant message id shared by both runs of the logical turn
  message_id        UUID NOT NULL,
  -- full conversation passed to the LLM at suspend time (incl. the dangling
  -- assistant tool-call message), as a JSON array of chat messages
  working           JSONB NOT NULL,
  -- the pending frontend tool call awaiting a client result
  pending_tool_call JSONB NOT NULL,  -- {id, name, args}
  -- usage accumulated in the first run, summed with the resume run at the end
  input_tokens      INT NOT NULL DEFAULT 0,
  output_tokens     INT NOT NULL DEFAULT 0,
  model_source      VARCHAR(20) NOT NULL,
  model_ref         UUID NOT NULL,
  parent_message_id UUID,
  user_message_content TEXT NOT NULL DEFAULT '',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at        TIMESTAMPTZ NOT NULL DEFAULT now() + interval '6 hours'
);

CREATE INDEX IF NOT EXISTS idx_chat_suspended_runs_session
  ON chat_suspended_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_suspended_runs_sweep
  ON chat_suspended_runs(expires_at);

-- RAID Wave C2 (DR-C2) — the permission mode the turn ran under, captured at
-- suspend time so a resumed run continues under the SAME mode (an Ask-mode
-- frontend-tool suspend must not resume into the full Write surface).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_suspended_runs' AND column_name='permission_mode') THEN
    ALTER TABLE chat_suspended_runs ADD COLUMN permission_mode VARCHAR(8) NOT NULL DEFAULT 'write';
  END IF;
END $$;

-- WS-3 — the PINNED rail's step tools, captured at suspend time.
-- The rail's TEXT rides the suspend for free (it is in the system message, which lives in
-- `working`), but its TOOLS did not: the resume pass re-derives the tool surface from
-- scratch and has no book_id to re-fetch the binding with, so the resumed turn read a
-- recipe naming tools it could not call. the flagship rail's first confirm gate is step 3 of 12, so the
-- flagship rail broke at its very first gate. NULL/absent ⇒ no pin (pre-WS-3 rows).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_suspended_runs' AND column_name='pinned_step_tools') THEN
    ALTER TABLE chat_suspended_runs ADD COLUMN pinned_step_tools JSONB;
  END IF;
END $$;

-- Track C P-1 (the step-runner) — carry the rail's book across the suspend so the RESUME
-- pass can re-fetch the pinned workflows + re-probe and KEEP DRIVING the rail past its
-- confirm gate. Without it the rail dead-ends at the confirm (assent turn drives to the
-- confirm → suspend → resume had no book_id → stall). NULL/absent ⇒ no rail (pre-P-1 rows).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_suspended_runs' AND column_name='book_id') THEN
    ALTER TABLE chat_suspended_runs ADD COLUMN book_id UUID;
  END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════
-- RAID Wave C2 (DR-C2) — per-tool approval allowlist ("Always allow").
-- In Write mode a Tier-A server tool NOT on the user's allowlist suspends
-- the run for a one-time approval card; "Always allow" inserts a row here
-- so that tool never prompts again for this user. Per-USER tier (CLAUDE.md
-- tenancy): a tool's trustworthiness is not book-specific, so no book
-- scope; no global rows. Reads fail-OPEN (a DB blip must not brick tool
-- calling — see DR-C2 reversibility).
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_tool_approvals (
  user_id    UUID NOT NULL,
  tool_name  TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, tool_name)
);

-- Track C WS-3 (D-C-ALLOWLIST-WRITE-ONLY) — the table was INSERT-ONLY: a user could
-- grant "Always allow" and never view, revoke, or refuse it. Consent without
-- withdrawal is broken by design, so the row now carries the DECISION rather than
-- meaning "granted" by its mere existence:
--   'allow' — the legacy "Always allow" (every pre-existing row IS a grant, so the
--             backfill default is exactly right and needs no data fix-up);
--   'deny'  — a persistent "Never allow" (the spec's deny-list). The gate must then
--             BLOCK the call outright instead of raising an approval card: re-asking
--             for something the user already refused forever is the same consent bug
--             wearing a different hat.
-- allow/deny are MUTUALLY EXCLUSIVE by construction — one row per (user, tool, kind)
-- on the existing PK, so a decision can only ever be flipped, never doubled.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_tool_approvals' AND column_name='decision') THEN
    ALTER TABLE user_tool_approvals ADD COLUMN decision TEXT NOT NULL DEFAULT 'allow';
    ALTER TABLE user_tool_approvals ADD CONSTRAINT user_tool_approvals_decision_chk
      CHECK (decision IN ('allow', 'deny'));
  END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════
-- Track "Production Eval + Feedback Flywheel" — Q3: chat-turn feedback.
-- The only absent feedback primitive (chat-service had none). Captures
-- explicit thumbs/rating + implicit regenerate-as-negative; emitted via the
-- existing outbox -> relay -> loreweave:events:chat -> learning-service, which
-- writes a quality_scores row (target_kind=chat_message, source=human).
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS message_feedback (
  id                         UUID PRIMARY KEY DEFAULT uuidv7(),
  message_id                 UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id                 UUID NOT NULL,
  user_id                    UUID NOT NULL,                  -- corpus owner (== message owner)
  rating                     SMALLINT NOT NULL,             -- +1 thumb up, -1 thumb down
  reason                     TEXT,                          -- optional free-text / 'regenerated'
  regenerated_from_message_id UUID,                         -- set when this is the implicit negative from a regenerate
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_message_feedback_message
  ON message_feedback(message_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_feedback_user
  ON message_feedback(user_id, created_at DESC);

-- ══════════════════════════════════════════════════════════════════════
-- T4 (Context Budget Law) — Core Memory Blocks. A per-session, owner-scoped
-- cache of the always-on context blocks (sealed #3: `story_state` only first)
-- so the Compiler can project the load-bearing lore gist as a SAFETY NET on a
-- turn whose expensive build_context grounding was gated (T5) — the follow-up
-- ("make it darker") never loses the lore the rewrite still needs (D4). Refreshed
-- on a cadence (sealed #5: lore-gate / scene change / every 5 turns), projected
-- from cache otherwise (D5 — no per-turn build_context round-trip).
--   TENANCY (CLAUDE.md, LOCKED): owns its own owner_user_id; every read/write
--   filters `session_id AND owner_user_id` (not join-only). UNIQUE per
--   (session, owner, label) → one row per block.
--   `version` is the OCC token (NET-NEW to chat-service — no prior PG OCC to
--   copy): a compare-and-set guards a future agent-writable block against a
--   multi-device stale clobber (D9); the auto-projected story_state cache uses
--   a plain upsert (derived data, last-refresh-wins is safe).
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS chat_session_blocks (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  session_id      UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
  owner_user_id   UUID NOT NULL,
  label           TEXT NOT NULL,              -- 'story_state' (the block key)
  value           TEXT NOT NULL DEFAULT '',   -- the rendered block body
  token_estimate  INT NOT NULL DEFAULT 0,     -- cached script-aware estimate of value
  refreshed_turn  INT NOT NULL DEFAULT 0,     -- session message_count at last refresh (cadence)
  source_hash     TEXT,                       -- hash of the grounding distilled from (skip no-op refresh)
  version         INT NOT NULL DEFAULT 1,     -- OCC token (compare-and-set; net-new)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, owner_user_id, label)
);

CREATE INDEX IF NOT EXISTS idx_chat_session_blocks_session
  ON chat_session_blocks (session_id, owner_user_id);

-- ══════════════════════════════════════════════════════════════════════
-- Interview-Practice Roleplay (POC for roleplay-service).
-- docs/specs/2026-06-23-interview-roleplay.md
--
-- session_templates — the "goal authority" for interview sessions. A
-- reusable interviewer persona + the scenario that seeds a session's frozen
-- `charter`. TENANCY (LOCKED rules): two tiers keyed by owner_user_id —
--   * System tier  : owner_user_id IS NULL → platform-owned, admin-write,
--                     read-only to users (seeded defaults).
--   * Per-user tier: owner_user_id = a user → that user writes their own.
-- Resolution merges System (defaults) → Per-user (overrides) by `code`.
-- NULL-distinct UNIQUE would let two System rows share a code, so the
-- uniqueness is split into two PARTIAL indexes (the correct fix for the
-- shared-row tenancy bug: never a bare UNIQUE(code) on a shared table).
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS session_templates (
  template_id    UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id  UUID,                                      -- NULL ⇒ System tier
  tier           VARCHAR(10) NOT NULL DEFAULT 'user',       -- 'system' | 'user'
  code           VARCHAR(100) NOT NULL,                     -- stable id for merge/resolution
  name           VARCHAR(255) NOT NULL,
  description    TEXT,
  system_prompt  TEXT NOT NULL,                             -- persona voice + rules
  model_source   VARCHAR(20),                               -- optional default model
  model_ref      UUID,
  scenario       JSONB NOT NULL DEFAULT '{}',               -- seeds working_memory.charter
  rubric         JSONB,                                     -- optional eval rubric (M6)
  is_active      BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT session_templates_tier_owner_chk CHECK (
    (tier = 'system' AND owner_user_id IS NULL) OR
    (tier = 'user'   AND owner_user_id IS NOT NULL)
  )
);
-- System-tier codes globally unique; per-user codes unique within the user.
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_templates_system_code
  ON session_templates (code) WHERE owner_user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_templates_user_code
  ON session_templates (owner_user_id, code) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_session_templates_owner
  ON session_templates (owner_user_id, is_active);

-- working_memory_seed — the frozen `charter` written ONCE at session create
-- from the chosen template's scenario (goal authority = template). Also the
-- degraded fallback (EC-4) when knowledge-service is unavailable. NULL for
-- non-interview sessions.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='working_memory_seed') THEN
    ALTER TABLE chat_sessions ADD COLUMN working_memory_seed JSONB;
  END IF;
END $$;

-- Story 04 / skills tool state machine — session-scoped tool/skill curation
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='enabled_tools') THEN
    ALTER TABLE chat_sessions ADD COLUMN enabled_tools TEXT[] NOT NULL DEFAULT '{}';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='enabled_skills') THEN
    ALTER TABLE chat_sessions ADD COLUMN enabled_skills TEXT[] NOT NULL DEFAULT '{}';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='activated_tools') THEN
    ALTER TABLE chat_sessions ADD COLUMN activated_tools TEXT[] NOT NULL DEFAULT '{}';
  END IF;
END $$;

-- D-COMPOSE-SESSION-RESTORE: a book-scoped chat (e.g. the Writing Studio
-- Compose panel) had no durable link to its book beyond the optional
-- knowledge-project id — for a book with no KG project yet, project_id stays
-- NULL forever, so the embedded binding logic could never find "the session
-- for this book" and always forced a fresh Start-New-Chat prompt (losing the
-- session AND its chosen model on every reopen). book_id is set at creation
-- time when the caller knows which book it's for; NULL for chat-page/roleplay
-- sessions that aren't book-scoped. No FK (books lives in loreweave_book, a
-- different DB) — an unknown/deleted book_id is harmless (just an inert tag).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='book_id') THEN
    ALTER TABLE chat_sessions ADD COLUMN book_id UUID;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_book
  ON chat_sessions(book_id) WHERE book_id IS NOT NULL;

-- ══════════════════════════════════════════════════════════════════════
-- Chat & AI settings unify (spec docs/specs/2026-07-05-chat-ai-settings.md).
-- The Account tier for behavior/grounding/voice/context settings. Model
-- account defaults deliberately stay in provider-registry `user_default_models`
-- (one SoT per fact — not duplicated here). Tenancy (LOCKED): PK = owner_user_id
-- (Per-user tier); one row per user; no shared/global user-writable row. The
-- System tier (env ceilings, client-seed presets) lives elsewhere, read-only.
-- `version` is the optimistic-concurrency guard for multi-device field-merge
-- (PATCH is a deep field-merge, not blob last-write-wins).
CREATE TABLE IF NOT EXISTS user_chat_ai_prefs (
  owner_user_id  UUID PRIMARY KEY,
  behavior       JSONB NOT NULL DEFAULT '{}'::jsonb,
  grounding      JSONB NOT NULL DEFAULT '{}'::jsonb,
  voice          JSONB NOT NULL DEFAULT '{}'::jsonb,
  context        JSONB NOT NULL DEFAULT '{"mode":"auto"}'::jsonb,
  version        BIGINT NOT NULL DEFAULT 0,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- WS-5.4 (spec 08, P5-D10) — `assistant` settings category. `coaching_enabled` is the
-- opt-out a user who wants the diary but NOT to be judged needs; DEFAULT OFF (opt-IN to
-- coaching, per P5-D10 — a spend/judgement-causing setting fails closed). A per-user
-- setting (not an env flag): two users legitimately differ.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_chat_ai_prefs' AND column_name='assistant') THEN
    ALTER TABLE user_chat_ai_prefs ADD COLUMN assistant JSONB NOT NULL DEFAULT '{}'::jsonb;
  END IF;
END $$;

-- Per-session overrides for the settings resolution cascade. NULL = inherit
-- from the next tier down (Book ▸ Account ▸ System) — never a hidden default at
-- this layer. Pre-migration rows are NULL ⇒ inherit, safe by design.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='grounding_enabled') THEN
    ALTER TABLE chat_sessions ADD COLUMN grounding_enabled BOOLEAN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='voice_overrides') THEN
    ALTER TABLE chat_sessions ADD COLUMN voice_overrides JSONB;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='context_overrides') THEN
    ALTER TABLE chat_sessions ADD COLUMN context_overrides JSONB;
  END IF;
END $$;

-- Tool-catalog-simplification Part D (CAT-4) — a per-SESSION manual escape
-- hatch back to a `_meta.visibility:"legacy"` tool that find_tools can no
-- longer discover. Session tier (SET-1): a user wants the old tool for THIS
-- conversation, not a standing account preference. Server-validated closed-set
-- (SET-6) against the live catalog at write time, not free text.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='chat_sessions' AND column_name='pinned_legacy_tools') THEN
    ALTER TABLE chat_sessions ADD COLUMN pinned_legacy_tools TEXT[] NOT NULL DEFAULT '{}';
  END IF;
END $$;

-- ══════════════════════════════════════════════════════════════════════
-- M7 — System-tier seed templates (the admin/platform path). These are the
-- shared defaults every tenant sees read-only; a user clones one (POST
-- /templates) to localize/customize. owner_user_id IS NULL ⇒ tier='system'.
-- ON CONFLICT DO NOTHING keys on the partial unique index
-- (uq_session_templates_system_code: code WHERE owner_user_id IS NULL) so a
-- re-run never duplicates and never clobbers an admin edit. Neutral 'en'
-- defaults — System tier is multi-tenant; localization is a per-user clone.
-- model_source/model_ref are NULL: the user supplies their own model at /start.
INSERT INTO session_templates (owner_user_id, tier, code, name, description, system_prompt, scenario, rubric)
VALUES
  (NULL, 'system', 'faang_swe',
   'FAANG SWE Interview',
   'A senior software-engineer loop: a brief warm-up, a coding/problem-solving round, then wrap-up.',
   'You are a senior engineer running a FAANG-style software interview. Be professional, concise, and probing. Ask ONE question at a time, let the candidate drive, and follow up on their reasoning (edge cases, complexity, trade-offs). Do not lecture or solve it for them. Keep the interview moving through the phases.',
   '{"goal":"Assess senior software-engineering skill through a coding/problem-solving interview","phases":["warmup","coding","followup","wrap"],"checklist":["clarifies the problem before coding","states an approach and its complexity","handles edge cases","writes correct working logic"],"time_budget_min":45,"language":"en"}'::jsonb,
   '{"dimensions":["problem clarification","algorithmic approach","code correctness","communication"]}'::jsonb),
  (NULL, 'system', 'behavioral_hr',
   'Behavioral (HR) Interview',
   'A behavioral interview focused on STAR stories: motivation, teamwork, conflict, and impact.',
   'You are a thoughtful HR / hiring-manager interviewer running a behavioral interview. Ask open-ended questions that invite STAR (Situation, Task, Action, Result) stories, one at a time. Gently probe for specifics — the candidate''s own actions and measurable results. Stay warm but keep them on track.',
   '{"goal":"Assess behavioral fit through STAR stories on teamwork, conflict, and impact","phases":["warmup","stories","followup","wrap"],"checklist":["gives a concrete Situation and Task","describes their own Actions specifically","states a measurable Result","tells a genuine conflict / failure story"],"time_budget_min":40,"language":"en"}'::jsonb,
   '{"dimensions":["STAR structure","specificity","ownership","reflection"]}'::jsonb),
  (NULL, 'system', 'system_design',
   'System Design Interview',
   'A senior system-design interview: requirements, high-level design, deep-dives, and trade-offs.',
   'You are a staff engineer running a system-design interview. Start from requirements and scale, then guide the candidate through a high-level design and one or two deep-dives. Push on trade-offs, bottlenecks, and failure modes. Ask one prompt at a time; let the candidate lead the design.',
   '{"goal":"Assess senior system-design skill: requirements, architecture, scaling, and trade-offs","phases":["requirements","high_level","deep_dive","wrap"],"checklist":["clarifies functional and scale requirements","proposes a clear high-level architecture","reasons about a data store and partitioning","discusses bottlenecks and failure modes"],"time_budget_min":50,"language":"en"}'::jsonb,
   '{"dimensions":["requirements","architecture","scalability","trade-off reasoning"]}'::jsonb)
ON CONFLICT (code) WHERE owner_user_id IS NULL DO NOTHING;

-- WS-5.1 (spec 08 §A1) — reflection_notes: the user's OWN end-of-day notes (what went well /
-- what to improve). This is the reflection substrate the recurring-theme + co-occurrence
-- detectors read (verified zero home repo-wide before this). PER-USER tier (User Boundaries):
-- owner_user_id scopes every row; UNIQUE(owner,entry_date) makes end-of-day capture an UPSERT
-- (one note per user per local day). Nothing here is canon — it is the user's private reflection.
CREATE TABLE IF NOT EXISTS reflection_notes (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  UUID NOT NULL,
  entry_date     DATE NOT NULL,
  went_well      TEXT,
  to_improve     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_reflection_notes_owner_date
  ON reflection_notes (owner_user_id, entry_date);

-- WS-5.6 / C2 (SD-C2) — reflection_dismissals: the user's tombstoned reflection patterns. A
-- dismissed pattern must never resurface as a "new" row next week, so worker-ai's reflection
-- detector drops any candidate whose PERIOD-INDEPENDENT pattern_key is here (dropped AT DETECTION,
-- before any phrasing). PER-USER tier (User Boundaries): owner_user_id scopes every row;
-- UNIQUE(owner,pattern_key) makes a dismiss idempotent (dismissing twice is a no-op, never a dup).
CREATE TABLE IF NOT EXISTS reflection_dismissals (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  UUID NOT NULL,
  pattern_key    TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, pattern_key)
);
CREATE INDEX IF NOT EXISTS idx_reflection_dismissals_owner
  ON reflection_dismissals (owner_user_id);

-- R1 (D-REFLECTION-PATTERNS-FEED) — reflection_patterns: the STRUCTURED patterns worker-ai's
-- deterministic detectors surfaced for a week (detector_code, summary, period-independent
-- pattern_key, evidence_refs), persisted alongside the prose reflection draft so the FE can render
-- DISMISSABLE chips (the dismiss chain FE→BFF→reflection_dismissals already exists; it just had
-- nothing to render against). worker-ai already tombstone-filters AT DETECTION; the READ additionally
-- filters against reflection_dismissals so a pattern dismissed AFTER generation vanishes on refresh
-- (server is SoT). PER-USER tier: owner_user_id scopes every row. Get-or-REPLACE per (owner, week_end)
-- — a re-run for the same week replaces its pattern set. UNIQUE(owner,week_end,pattern_key) dedups.
CREATE TABLE IF NOT EXISTS reflection_patterns (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  UUID NOT NULL,
  week_start     DATE NOT NULL,
  week_end       DATE NOT NULL,
  detector_code  TEXT NOT NULL,
  summary        TEXT NOT NULL,
  pattern_key    TEXT NOT NULL,
  evidence_refs  JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, week_end, pattern_key)
);
CREATE INDEX IF NOT EXISTS idx_reflection_patterns_owner_week
  ON reflection_patterns (owner_user_id, week_end DESC);

-- WS-5.20 (spec 08 §Scorer) — coaching_rubrics: the SCORING STANDARD, versioned + cited,
-- replacing the free-form SessionTemplate.rubric (dict[str,Any], no schema — "improvised
-- standards already ship"). SYSTEM tier: admin-seeded, everyone reads, a regular user never
-- writes (User Boundaries). `dimensions` = [{key,label,anchors:{1..5}}] — the server-
-- authoritative dimension set the Scorecard coerces against (coerce_scorecard's safe-when-wrong
-- guarantee is anchored to THIS, not the model's output). A coach session with NO resolvable
-- rubric REFUSES to score (P5-D5). `tier` carries the quarantine state until Gate 4 clears.
CREATE TABLE IF NOT EXISTS coaching_rubrics (
  rubric_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code            TEXT NOT NULL,
  version         INT  NOT NULL DEFAULT 1,
  label           TEXT NOT NULL,
  dimensions      JSONB NOT NULL,                 -- [{key,label,anchors:{"1":..,"5":..}}]
  source_citation TEXT NOT NULL DEFAULT '',
  license         TEXT NOT NULL DEFAULT '',
  tier            TEXT NOT NULL DEFAULT 'quarantine' CHECK (tier IN ('quarantine','validated')),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (code, version)
);
-- Seed ONE System-tier default rubric so a coach session can resolve a standard (a coaching
-- interview scores the user's STAR/clarity/structure). Idempotent; tier='quarantine' until
-- the Gate-4 human eval clears.
INSERT INTO coaching_rubrics (code, version, label, dimensions, source_citation, tier)
VALUES ('interview_v1', 1, 'Behavioral interview (STAR)',
  '[{"key":"star_structure","label":"STAR structure","anchors":{"1":"no discernible structure","3":"partial STAR (missing Result)","5":"complete Situation-Task-Action-Result"}},
    {"key":"clarity","label":"Clarity","anchors":{"1":"hard to follow","3":"mostly clear","5":"crisp and well-sequenced"}},
    {"key":"specificity","label":"Specificity","anchors":{"1":"vague generalities","3":"some concrete detail","5":"concrete, quantified examples"}}]'::jsonb,
  'STAR method (Situation-Task-Action-Result), widely-used behavioral-interview framework', 'quarantine')
ON CONFLICT (code, version) DO NOTHING;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
    # B1 / spec 07 §Q3 (T31) — a pg_trgm GIN index accelerates chat_search_sessions' ILIKE '%…%'
    # cross-session recall (the existing GIN is English tsvector, useless for VI/CJK names). CREATE
    # EXTENSION + the index run OUTSIDE the main DDL as BEST-EFFORT: a role lacking CREATE-EXTENSION
    # privilege must NOT abort the migration (chat-service would fail to start). Recall still works
    # without the index (a scan); this is purely a performance optimization. No CONCURRENTLY inside
    # the transactional migrator.
    import logging as _logging
    _log = _logging.getLogger(__name__)
    for stmt in (
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_content_trgm "
        "ON chat_messages USING gin (content gin_trgm_ops)",
    ):
        try:
            async with pool.acquire() as conn:
                await conn.execute(stmt)
        except Exception:  # noqa: BLE001 — best-effort; recall degrades to a scan, never a failed boot
            _log.warning("best-effort trigram index step skipped (recall falls back to a scan): %s", stmt)
