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

-- LLM re-arch Phase 2b — event-driven decouple of the chapter pipeline.
-- pipeline_stage tracks the V3 stage (translate | verify | correct | done) so a
-- llm_job_terminal consumer can resume the chapter at the right step.
-- provider_job_id is the chapter's CURRENT in-flight LLM job (the sequential
-- chunk-translate / verify / correct call) — a terminal event for it routes the
-- consumer back to this chapter. The per-chunk state already lives in
-- chapter_translation_chunks (translated_text + status + compact_memo_applied),
-- so the session history is RECONSTRUCTED from completed chunk rows rather than
-- serialized in-memory — that's what makes the decouple tractable.
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS pipeline_stage  TEXT,
  ADD COLUMN IF NOT EXISTS provider_job_id UUID,
  -- 2b-T2: the explicit resume blob for the decoupled translate loop
  -- {chunks, chunk_idx, session_history, compact_memo, translated_parts,
  --  total_input, total_output, awaiting}. Persisting the running state (vs
  --  replaying compaction, which is itself an LLM call whose memo output isn't
  --  recoverable from chunk rows) keeps the resume correct + simple.
  ADD COLUMN IF NOT EXISTS resume_state    JSONB;
-- Resume index: find the chapter awaiting a given in-flight LLM job in O(1).
CREATE INDEX IF NOT EXISTS idx_ct_provider_job
  ON chapter_translations(provider_job_id) WHERE provider_job_id IS NOT NULL;
-- Per-chunk in-flight job (the chunk currently being translated). The sequential
-- chunk loop has at most one in-flight chunk per chapter at a time.
ALTER TABLE chapter_translation_chunks
  ADD COLUMN IF NOT EXISTS provider_job_id UUID;

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

-- V5: Outbox events for statistics-service pipeline
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  event_type     TEXT NOT NULL,
  aggregate_type TEXT NOT NULL DEFAULT 'chapter',
  aggregate_id   UUID NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox_events(created_at) WHERE published_at IS NULL;

-- V6: Translation Pipeline V2 — cross-chapter memo
CREATE TABLE IF NOT EXISTS translation_chapter_memos (
  book_id          UUID NOT NULL,
  chapter_index    INT NOT NULL,
  target_language  TEXT NOT NULL,
  terms_used       JSONB NOT NULL DEFAULT '{}',
  story_summary    TEXT NOT NULL DEFAULT '',
  style_notes      TEXT NOT NULL DEFAULT '',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, chapter_index, target_language)
);

-- V6: Translation Pipeline V2 — quality metrics on chunk rows
ALTER TABLE chapter_translation_chunks
  ADD COLUMN IF NOT EXISTS validation_errors   TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS validation_warnings TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS glossary_corrections INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS retry_count         INT NOT NULL DEFAULT 0;

-- V7: Glossary Extraction Pipeline — extraction jobs
CREATE TABLE IF NOT EXISTS extraction_jobs (
  job_id             UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id            UUID NOT NULL,
  owner_user_id      UUID NOT NULL,
  status             TEXT NOT NULL DEFAULT 'pending',
  source_language    TEXT NOT NULL DEFAULT 'zh',
  model_source       TEXT NOT NULL DEFAULT 'platform_model',
  model_ref          UUID NOT NULL,
  extraction_profile JSONB NOT NULL DEFAULT '{}',
  context_filters    JSONB NOT NULL DEFAULT '{}',
  chapter_ids        UUID[] NOT NULL,
  total_chapters     INT NOT NULL DEFAULT 0,
  completed_chapters INT NOT NULL DEFAULT 0,
  failed_chapters    INT NOT NULL DEFAULT 0,
  entities_created   INT NOT NULL DEFAULT 0,
  entities_updated   INT NOT NULL DEFAULT 0,
  entities_skipped   INT NOT NULL DEFAULT 0,
  total_input_tokens BIGINT NOT NULL DEFAULT 0,
  total_output_tokens BIGINT NOT NULL DEFAULT 0,
  cost_estimate      JSONB,
  error_message      TEXT,
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ej_owner ON extraction_jobs(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ej_book  ON extraction_jobs(book_id, created_at DESC);

CREATE TABLE IF NOT EXISTS extraction_chapter_results (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id          UUID NOT NULL REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
  chapter_id      UUID NOT NULL,
  book_id         UUID NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',
  entities_found  INT NOT NULL DEFAULT 0,
  input_tokens    BIGINT NOT NULL DEFAULT 0,
  output_tokens   BIGINT NOT NULL DEFAULT 0,
  error_message   TEXT,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ecr_job ON extraction_chapter_results(job_id);

-- ── V8: Translation Pipeline V3 — selection flag, per-role models, QA config ──
-- Additive + idempotent. Default pipeline_version='v2' ⇒ zero behavior change
-- until a book/job opts into 'v3'. verifier_model_* nullable ⇒ falls back to the
-- translator model. qa_depth ∈ {rule_only, standard, thorough}.
ALTER TABLE user_translation_preferences
  ADD COLUMN IF NOT EXISTS pipeline_version      TEXT NOT NULL DEFAULT 'v2',
  ADD COLUMN IF NOT EXISTS verifier_model_source TEXT,
  ADD COLUMN IF NOT EXISTS verifier_model_ref    UUID,
  ADD COLUMN IF NOT EXISTS max_qa_rounds         INT  NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS qa_depth              TEXT NOT NULL DEFAULT 'standard',
  ADD COLUMN IF NOT EXISTS cold_start_mode       TEXT NOT NULL DEFAULT 'single_pass';

ALTER TABLE book_translation_settings
  ADD COLUMN IF NOT EXISTS pipeline_version      TEXT NOT NULL DEFAULT 'v2',
  ADD COLUMN IF NOT EXISTS verifier_model_source TEXT,
  ADD COLUMN IF NOT EXISTS verifier_model_ref    UUID,
  ADD COLUMN IF NOT EXISTS max_qa_rounds         INT  NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS qa_depth              TEXT NOT NULL DEFAULT 'standard',
  ADD COLUMN IF NOT EXISTS cold_start_mode       TEXT NOT NULL DEFAULT 'single_pass';

ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS pipeline_version      TEXT NOT NULL DEFAULT 'v2',
  ADD COLUMN IF NOT EXISTS verifier_model_source TEXT,
  ADD COLUMN IF NOT EXISTS verifier_model_ref    UUID,
  ADD COLUMN IF NOT EXISTS max_qa_rounds         INT  NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS qa_depth              TEXT NOT NULL DEFAULT 'standard',
  ADD COLUMN IF NOT EXISTS cold_start_mode       TEXT NOT NULL DEFAULT 'single_pass';

-- S5b-eval: per-campaign translation eval-judge model. Only on translation_jobs
-- (campaign-supplied via dispatch; NOT a user/book setting). Rides the
-- translation.quality event to learning-service's M7d-2 fidelity judge.
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS eval_judge_model_source TEXT,
  ADD COLUMN IF NOT EXISTS eval_judge_model_ref    UUID;

-- Per-block QA issues — drives targeted re-translate + the future "needs review" UI.
CREATE TABLE IF NOT EXISTS translation_quality_issues (
  id                     UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_translation_id UUID NOT NULL REFERENCES chapter_translations(id) ON DELETE CASCADE,
  block_index            INT  NOT NULL,
  round                  INT  NOT NULL DEFAULT 0,
  issue_type             TEXT NOT NULL,   -- omission|wrong_name|added|number_mismatch|format|untranslated
  severity               TEXT NOT NULL,   -- high|med|low
  detail                 TEXT,
  expected               TEXT,
  resolved               BOOLEAN NOT NULL DEFAULT false,
  detected_by            TEXT NOT NULL DEFAULT 'rule',  -- rule|llm
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tqi_ct ON translation_quality_issues(chapter_translation_id);

-- Per-chapter quality rollup (cheap badge source; no status-enum churn).
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS quality_score         INT,
  ADD COLUMN IF NOT EXISTS unresolved_high_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS qa_rounds_used        INT NOT NULL DEFAULT 0;

-- M5c living-book: glossary-staleness flag. Set true (coarse, book-level) when a
-- glossary entity for the book changes (consumed from loreweave:events:glossary);
-- a hint that the translation predates the glossary edit. Additive + idempotent.
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS is_glossary_stale BOOLEAN NOT NULL DEFAULT false;

-- M6b full-propagate: per-(chapter_translation, entity) glossary usage index.
-- The worker records which glossary entities a chapter's translation actually
-- drew on (entries that scored > 0 against the chapter text). On a later
-- glossary.entity_updated the staleness consumer flags ONLY the chapter
-- translations whose index contains the changed entity_id (and, when the event
-- carries target_language, only that language) instead of the whole book.
-- A translation with NO rows here (translated before this index existed) falls
-- back to the coarse flag — no false-negatives. ON DELETE CASCADE ties usage to
-- its translation version.
CREATE TABLE IF NOT EXISTS chapter_translation_glossary_usage (
  chapter_translation_id UUID NOT NULL
    REFERENCES chapter_translations(id) ON DELETE CASCADE,
  entity_id              UUID NOT NULL,
  PRIMARY KEY (chapter_translation_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_ctgu_entity
  ON chapter_translation_glossary_usage(entity_id);

-- M7c (human-fix gold): mark human-authored translation versions + link the LLM
-- version they were edited from, so the LLM→human diff can be captured as a
-- learning correction (before=LLM draft, after=human edit). Additive + idempotent.
-- 'llm' default keeps every existing/worker-produced version unchanged.
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS authored_by TEXT NOT NULL DEFAULT 'llm',
  ADD COLUMN IF NOT EXISTS edited_from_version_id UUID;

-- S4a (Auto-Draft Factory cost attribution): the owning campaign for a
-- campaign-dispatched job. NULL for ordinary user-initiated translations. Stored
-- for queryability; the runtime correlation rides through to each provider job's
-- job_meta via the per-chapter message + a worker-set contextvar (see llm_client).
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS campaign_id UUID;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
