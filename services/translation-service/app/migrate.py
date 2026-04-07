import asyncpg

DDL = """
CREATE TABLE IF NOT EXISTS user_translation_preferences (
  user_id         UUID PRIMARY KEY,
  target_language TEXT NOT NULL DEFAULT 'en',
  model_source    TEXT NOT NULL DEFAULT 'platform_model',
  model_ref       UUID,
  system_prompt   TEXT NOT NULL DEFAULT '',
  user_prompt_tpl TEXT NOT NULL DEFAULT '',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS book_translation_settings (
  book_id         UUID PRIMARY KEY,
  owner_user_id   UUID NOT NULL,
  target_language TEXT NOT NULL DEFAULT 'en',
  model_source    TEXT NOT NULL DEFAULT 'platform_model',
  model_ref       UUID,
  system_prompt   TEXT NOT NULL DEFAULT '',
  user_prompt_tpl TEXT NOT NULL DEFAULT '',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bts_owner ON book_translation_settings(owner_user_id);

CREATE TABLE IF NOT EXISTS translation_jobs (
  job_id             UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id            UUID NOT NULL,
  owner_user_id      UUID NOT NULL,
  status             TEXT NOT NULL DEFAULT 'pending',
  target_language    TEXT NOT NULL,
  model_source       TEXT NOT NULL,
  model_ref          UUID NOT NULL,
  system_prompt      TEXT NOT NULL,
  user_prompt_tpl    TEXT NOT NULL,
  chapter_ids        UUID[] NOT NULL,
  total_chapters     INT NOT NULL DEFAULT 0,
  completed_chapters INT NOT NULL DEFAULT 0,
  failed_chapters    INT NOT NULL DEFAULT 0,
  error_message      TEXT,
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tj_owner ON translation_jobs(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tj_book  ON translation_jobs(book_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chapter_translations (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id          UUID NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
  chapter_id      UUID NOT NULL,
  book_id         UUID NOT NULL,
  owner_user_id   UUID NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',
  translated_body TEXT,
  source_language TEXT,
  target_language TEXT NOT NULL,
  input_tokens    INT,
  output_tokens   INT,
  usage_log_id    UUID,
  error_message   TEXT,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ct_job     ON chapter_translations(job_id, chapter_id);
CREATE INDEX IF NOT EXISTS idx_ct_chapter ON chapter_translations(chapter_id, created_at DESC);

-- V2: chunk + session config columns
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

ALTER TABLE book_translation_settings
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS compact_model_source TEXT,
  ADD COLUMN IF NOT EXISTS compact_model_ref     UUID,
  ADD COLUMN IF NOT EXISTS chunk_size_tokens     INT  NOT NULL DEFAULT 2000,
  ADD COLUMN IF NOT EXISTS invoke_timeout_secs   INT  NOT NULL DEFAULT 300;

-- Per-chapter chunk rows (observability; recovery restarts chapter from scratch)
CREATE TABLE IF NOT EXISTS chapter_translation_chunks (
  id                      UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_translation_id  UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  chunk_index             INT  NOT NULL,
  chunk_text              TEXT NOT NULL,
  translated_text         TEXT,
  compact_memo_applied    TEXT,
  status                  TEXT NOT NULL DEFAULT 'pending',
  input_tokens            INT,
  output_tokens           INT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_translation_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_ctc_ct ON chapter_translation_chunks(chapter_translation_id);

-- UX Wave (LW-72): version tracking
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS version_num INT NOT NULL DEFAULT 1;

-- Backfill: assign sequential version_num per (chapter_id, target_language)
-- ordered by created_at so existing rows don't violate the unique index.
-- Safe to re-run (idempotent — ROW_NUMBER is deterministic by created_at).
UPDATE chapter_translations ct
SET version_num = sub.rn
FROM (
  SELECT id,
         ROW_NUMBER() OVER (
           PARTITION BY chapter_id, target_language
           ORDER BY created_at
         ) AS rn
  FROM chapter_translations
) sub
WHERE ct.id = sub.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ct_version
  ON chapter_translations(chapter_id, target_language, version_num);

CREATE TABLE IF NOT EXISTS active_chapter_translation_versions (
  chapter_id              UUID NOT NULL,
  target_language         TEXT NOT NULL,
  chapter_translation_id  UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  set_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  set_by_user_id          UUID NOT NULL,
  PRIMARY KEY (chapter_id, target_language)
);

-- V3: compact model prompt customisation (LW-73)
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';

ALTER TABLE book_translation_settings
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';

ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS compact_system_prompt   TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS compact_user_prompt_tpl TEXT NOT NULL DEFAULT '';

-- V4: Phase 8F — block-level translation (TF-01)
-- New column for Tiptap JSONB translations (keeps TEXT column for backward compat)
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS translated_body_json JSONB,
  ADD COLUMN IF NOT EXISTS translated_body_format TEXT NOT NULL DEFAULT 'text';
-- format = 'text' (legacy flat text in translated_body) | 'json' (Tiptap blocks in translated_body_json)
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
