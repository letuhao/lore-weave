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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
