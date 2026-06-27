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
-- Unified Job Control Plane reconcile source: GET /internal/translation/jobs?since= filters
-- on the effective last-touch (no updated_at column). An EXPRESSION index over the EXACT
-- same GREATEST(...) the query uses lets the periodic sweep avoid a seq-scan + sort.
CREATE INDEX IF NOT EXISTS idx_tj_reconcile_ts ON translation_jobs (
  GREATEST(created_at, COALESCE(started_at, created_at), COALESCE(finished_at, created_at))
);

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

-- D-TRANSLATE-REASONING-TOGGLE — per-job "enable model reasoning (thinking)".
-- Default OFF (translation output is sensitive to hidden thinking burning the
-- budget). On the job ROW so it survives job-resume (the message is rebuilt from
-- the row in _job_message_from_row), not just the create-time message.
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS thinking_enabled BOOLEAN NOT NULL DEFAULT false;

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

-- Wave 2a (D-2B-SUBMIT-PERSIST-GAP) — a stale-resume sweeper (parity with worker-ai's
-- Wave 1b) needs a time-based idle signal; chapter_translations had no updated_at.
-- Additive, default now(); bumped on every resume_state write (the engines' _persist_inflight).
ALTER TABLE chapter_translations
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
-- Partial index for the sweep scan (only rows with a live resume_state matter).
CREATE INDEX IF NOT EXISTS idx_ct_resume_sweep
  ON chapter_translations(updated_at) WHERE resume_state IS NOT NULL;

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
-- D-RE-WORKER-GRADED-EFFORT: the clamped graded reasoning effort (none|low|medium|high) the
-- worker honors per call. Additive + idempotent; default 'none' ⇒ zero behavior change for
-- existing rows (the worker falls back to the thinking_enabled bool when absent).
ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS reasoning_effort TEXT NOT NULL DEFAULT 'none';
-- bug #3 / D-JOBS-P4: actual job cost for the unified Jobs GUI. The gateway `usage` carries
-- only tokens (no cost), so this is DERIVED from the summed per-chapter tokens × the model's
-- pricing (provider-registry estimate oracle) and rides the live + terminal job events.
-- Nullable: an older/unpriced job leaves it NULL (the GUI renders cost null-safe). Mirrors
-- translation_jobs.cost_usd.
ALTER TABLE extraction_jobs ADD COLUMN IF NOT EXISTS cost_usd NUMERIC;
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

-- OBS/M2: per-batch outcome SSOT (extraction-pipeline §2.3 / INV-F15, INV-O12/13).
-- The batch-outcome taxonomy that makes a silent all-rejected/truncated batch visible.
-- These rows are the OBSERVE source-of-truth; a reconciliation sweep re-derives job stats
-- from them. (A same-txn outbox PROJECTION of these rows is deferred until a consumer binds
-- — D-OBS-BATCH-OUTCOME-PROJECTION.) owner_user_id + book_id carry the tenant scope
-- (INV-T6); detail_redacted is bounded + carries NO raw_response/secrets.
CREATE TABLE IF NOT EXISTS extraction_batch_outcomes (
  id                        UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id                    UUID NOT NULL REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
  owner_user_id             UUID NOT NULL,
  book_id                   UUID NOT NULL,
  chapter_id                UUID NOT NULL,
  batch_idx                 INT  NOT NULL DEFAULT 0,
  chunk_idx                 INT  NOT NULL DEFAULT 0,
  status                    TEXT NOT NULL,   -- ok|empty_valid|truncated|validation_rejected|llm_error|writeback_failed|unplannable
  finish_reason             TEXT,
  kinds                     TEXT[] NOT NULL DEFAULT '{}',
  entities_found            INT NOT NULL DEFAULT 0,
  entities_written          INT NOT NULL DEFAULT 0,
  validation_rejected_count INT NOT NULL DEFAULT 0,
  input_tokens             INT NOT NULL DEFAULT 0,
  output_tokens            INT NOT NULL DEFAULT 0,
  error_code               TEXT,
  detail_redacted          TEXT,
  event_id                 TEXT NOT NULL,   -- stable: sha256(job_id, chapter_id, batch_idx, content_hash)
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (event_id)        -- redelivery-stable dedup for the projection (INV-O13)
);
CREATE INDEX IF NOT EXISTS idx_ebo_job     ON extraction_batch_outcomes(job_id);
CREATE INDEX IF NOT EXISTS idx_ebo_chapter ON extraction_batch_outcomes(job_id, chapter_id);

-- CACHE/M6: the EXECUTE ledger (extraction-pipeline §2.1 / §8.1 two-ledger model). "The LLM
-- produced this parse" — keyed by tenant + chapter content-hash + effort band + batch, so a
-- re-extraction of an UNCHANGED chapter skips the LLM (don't re-spend tokens). Distinct from
-- extraction_writeback_log ("landed in glossary"): LLM-skip keys here, writeback-skip there.
-- owner_user_id is IN the unique key + every lookup — cross-tenant cache reuse is forbidden
-- (INV-9; content_hash is a within-tenant idempotency key, never cross-tenant). raw_response
-- is the verbatim debugging/provenance artifact; parsed_entities is what a cache hit reuses.
CREATE TABLE IF NOT EXISTS extraction_raw_outputs (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id               UUID,
  owner_user_id        UUID NOT NULL,
  book_id              UUID NOT NULL,
  chapter_id           UUID NOT NULL,
  chapter_content_hash TEXT NOT NULL,
  chapter_chunk_idx    INT  NOT NULL DEFAULT 0,
  batch_idx            INT  NOT NULL DEFAULT 0,
  kinds_requested      TEXT[] NOT NULL DEFAULT '{}',
  profile_hash         TEXT NOT NULL DEFAULT '',
  model_source         TEXT NOT NULL DEFAULT '',
  model_ref            UUID,
  model_name           TEXT,
  reasoning_effort     TEXT NOT NULL DEFAULT 'none',
  effort_band          TEXT NOT NULL DEFAULT 'none',
  input_tokens         INT,
  output_tokens        INT,
  finish_reason        TEXT,
  raw_response         TEXT NOT NULL DEFAULT '',
  parsed_entities      JSONB NOT NULL DEFAULT '[]',
  parse_status         TEXT NOT NULL DEFAULT 'ok',
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- profile_hash IS in the key (§8.1): a changed extraction profile (different kinds/attrs)
  -- re-maps batch_idx to different work, so it must MISS the cache and re-extract — without
  -- it a re-extraction after an ontology edit would silently reuse the old profile's parse.
  UNIQUE (owner_user_id, book_id, chapter_id, chapter_chunk_idx, chapter_content_hash, effort_band, batch_idx, profile_hash)
);
CREATE INDEX IF NOT EXISTS idx_ero_cache
  ON extraction_raw_outputs(owner_user_id, book_id, chapter_id, chapter_content_hash, effort_band);
-- D-RAWCACHE-MINIO-OFFLOAD: cold-archive pointer for the bulky verbatim `raw_response`.
-- When an offload sweep moves a row's raw_response to object storage it NULLs raw_response
-- (sets it to '') and records the object key here; replay never needs raw_response (it uses
-- parsed_entities), so offload is transparent to the cache. A partial index makes the sweep's
-- "not-yet-offloaded, has a body" scan cheap without bloating the index with archived rows.
ALTER TABLE extraction_raw_outputs ADD COLUMN IF NOT EXISTS raw_response_uri TEXT;
CREATE INDEX IF NOT EXISTS idx_ero_offload_pending
  ON extraction_raw_outputs(created_at)
  WHERE raw_response_uri IS NULL AND raw_response <> '';

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

-- T2-M2 dirty-only re-translate: a job scoped to specific block positions of a
-- single chapter. block_index_filter = the dirty block positions; seed_version_id
-- = the prior llm version whose blocks are copied for every NON-filtered position.
-- NULL for ordinary whole-chapter jobs. Stored for queryability; the worker reads
-- them off the per-chapter message (rides through coordinator fan-out).
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS block_index_filter INT[],
  ADD COLUMN IF NOT EXISTS seed_version_id    UUID;

-- GT: Glossary batch translation jobs (enhancement track)
CREATE TABLE IF NOT EXISTS glossary_translation_jobs (
  job_id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id             UUID NOT NULL,
  owner_user_id       UUID NOT NULL,
  status              TEXT NOT NULL DEFAULT 'pending',
  source_language     TEXT NOT NULL DEFAULT 'zh',
  target_language     TEXT NOT NULL,
  model_source        TEXT NOT NULL DEFAULT 'platform_model',
  model_ref           UUID NOT NULL,
  overwrite_mode      TEXT NOT NULL DEFAULT 'missing_only',
  metadata            JSONB NOT NULL DEFAULT '{}',
  total_entities      INT NOT NULL DEFAULT 0,
  completed_entities  INT NOT NULL DEFAULT 0,
  failed_entities     INT NOT NULL DEFAULT 0,
  attrs_translated    INT NOT NULL DEFAULT 0,
  attrs_skipped       INT NOT NULL DEFAULT 0,
  total_input_tokens  BIGINT NOT NULL DEFAULT 0,
  total_output_tokens BIGINT NOT NULL DEFAULT 0,
  cost_estimate       JSONB,
  error_message       TEXT,
  started_at          TIMESTAMPTZ,
  finished_at         TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gtj_owner ON glossary_translation_jobs(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gtj_book  ON glossary_translation_jobs(book_id, created_at DESC);

-- T2-M1: source-side translation segments (block-range division of a chapter).
-- Language-independent ranges of chapter_blocks (~2000-token, heading-aware) — the
-- foundation for per-part translate/status (M2) + dirty-only re-translate. block_hashes
-- = the ordered chapter_blocks.content_hash of the range; source_content_hash = a
-- chapter-stable digest of the whole range for cheap idempotent re-segmentation.
CREATE TABLE IF NOT EXISTS chapter_segments (
  id                  UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id          UUID NOT NULL,
  segment_index       INT  NOT NULL,
  start_block_index   INT  NOT NULL,
  end_block_index     INT  NOT NULL,
  segment_text        TEXT NOT NULL,
  block_hashes        TEXT[] NOT NULL DEFAULT '{}',
  token_estimate      INT  NOT NULL DEFAULT 0,
  source_content_hash TEXT NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, segment_index)
);
CREATE INDEX IF NOT EXISTS idx_cseg_chapter ON chapter_segments(chapter_id);

-- T2-M2: per-(chapter, target_language, segment) translation status. Records the
-- segment's source_content_hash AT translate time, so a later source edit (the
-- segment's blocks changed → its chapter_segments.source_content_hash differs) reads
-- as DIRTY (recorded hash != current hash, or no row). A full-chapter translation
-- upserts every segment; dirty-only re-translate refreshes just the changed ones.
CREATE TABLE IF NOT EXISTS segment_translations (
  id                     UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id             UUID NOT NULL,
  target_language        TEXT NOT NULL,
  segment_index          INT  NOT NULL,
  source_content_hash    TEXT NOT NULL,
  chapter_translation_id UUID,
  translated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, target_language, segment_index)
);
CREATE INDEX IF NOT EXISTS idx_segtr_chapter_lang
  ON segment_translations(chapter_id, target_language);

-- T2-M3 (D) per-segment glossary staleness:
-- which glossary entities each SEGMENT's source text references (language-independent
-- — source terms in source text). Populated best-effort at translate finalize.
CREATE TABLE IF NOT EXISTS segment_glossary_usage (
  chapter_id     UUID NOT NULL,
  segment_index  INT  NOT NULL,
  entity_id      UUID NOT NULL,
  PRIMARY KEY (chapter_id, segment_index, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_sgu_entity ON segment_glossary_usage(entity_id);
-- Per-(chapter, language, segment) staleness flag: set true when a glossary entity the
-- segment uses changes after it was translated; reset false on (re)record. Distinct from
-- source-edit `dirty` (a segment can be glossary-stale with unchanged source).
ALTER TABLE segment_translations
  ADD COLUMN IF NOT EXISTS is_glossary_stale BOOLEAN NOT NULL DEFAULT false;

-- D-JOBS-P4-TRANSLATION-COST: job-level cost for the unified Jobs GUI. The gateway
-- `usage` carries only tokens (no cost), so this is DERIVED at finalize from the summed
-- per-chapter tokens × the model's pricing (provider-registry estimate oracle), out-of-tx,
-- and rides the terminal job event. Nullable: an older/unpriced job leaves it NULL (the
-- GUI renders cost null-safe).
ALTER TABLE translation_jobs
  ADD COLUMN IF NOT EXISTS cost_usd NUMERIC;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
