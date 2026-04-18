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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
