import asyncpg

DDL = """
CREATE TABLE IF NOT EXISTS chat_sessions (
  session_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id     UUID NOT NULL,
  title             VARCHAR(255) NOT NULL DEFAULT 'New Chat',
  model_source      VARCHAR(20) NOT NULL,
  model_ref         UUID NOT NULL,
  system_prompt     TEXT,
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
  parent_message_id UUID REFERENCES chat_messages(message_id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, sequence_num)
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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
