"""Idempotent Postgres DDL for loreweave_knowledge.

Follows chat-service's house style: a single DDL string with
CREATE TABLE IF NOT EXISTS + DO $$ blocks for ALTERs, applied on every
startup via run_migrations(pool). No migration tool, no files.

Cross-database FKs are intentionally absent: user_id references
loreweave_auth.users and book_id references loreweave_book.books, both
in different databases. Validation of those is done in application code
(or in Track 2 via cross-service HTTP calls).
"""

import asyncpg

DDL = """
-- ═══════════════════════════════════════════════════════════════
-- knowledge_projects
-- Explicit containers for scoping knowledge. Lives in Postgres (SSOT).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_projects (
  project_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id             UUID NOT NULL,                    -- no FK (cross-DB)
  name                TEXT NOT NULL,
  description         TEXT NOT NULL DEFAULT '',
  project_type        TEXT NOT NULL
    CHECK (project_type IN ('book','translation','code','general')),
  book_id             UUID,                             -- no FK (cross-DB)
  instructions        TEXT NOT NULL DEFAULT '',

  extraction_enabled  BOOLEAN NOT NULL DEFAULT false,
  extraction_status   TEXT NOT NULL DEFAULT 'disabled'
    CHECK (extraction_status IN ('disabled','building','paused','ready','failed')),
  embedding_model     TEXT,
  extraction_config   JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_extracted_at   TIMESTAMPTZ,
  estimated_cost_usd  NUMERIC(10,4) NOT NULL DEFAULT 0,
  actual_cost_usd     NUMERIC(10,4) NOT NULL DEFAULT 0,

  is_archived         BOOLEAN NOT NULL DEFAULT false,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_projects_user
  ON knowledge_projects(user_id) WHERE NOT is_archived;

CREATE INDEX IF NOT EXISTS idx_knowledge_projects_extraction_status
  ON knowledge_projects(extraction_status) WHERE extraction_status != 'disabled';

-- ═══════════════════════════════════════════════════════════════
-- knowledge_summaries
-- Plain-text L0 (global) and L1 (project) context. No embeddings.
-- UNIQUE (user_id, scope_type, scope_id) — NULLS NOT DISTINCT so that
-- a second (user, 'global', NULL) row conflicts instead of duplicating.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_summaries (
  summary_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id      UUID NOT NULL,
  scope_type   TEXT NOT NULL
    CHECK (scope_type IN ('global','project','session','entity')),
  scope_id     UUID,
  content      TEXT NOT NULL,
  token_count  INT,
  version      INT NOT NULL DEFAULT 1,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_summaries_unique
  ON knowledge_summaries(user_id, scope_type, scope_id) NULLS NOT DISTINCT;

-- ═══════════════════════════════════════════════════════════════
-- K7 (D-K1-01 / D-K1-02): defensive length caps.
-- Postgres has no IF NOT EXISTS for CHECK constraints, so we wrap
-- each ADD in a DO block keyed on pg_constraint lookup. Idempotent.
-- ═══════════════════════════════════════════════════════════════
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_projects_instructions_len'
  ) THEN
    ALTER TABLE knowledge_projects
      ADD CONSTRAINT knowledge_projects_instructions_len
      CHECK (length(instructions) <= 20000);
  END IF;
END$$;

-- K7-review-R4: name had Pydantic max=200 but no DB CHECK, asymmetric
-- with the other length-capped columns. Defense-in-depth: cap matches
-- ProjectName StringConstraints in app/db/models.py.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_projects_name_len'
  ) THEN
    ALTER TABLE knowledge_projects
      ADD CONSTRAINT knowledge_projects_name_len
      CHECK (length(name) BETWEEN 1 AND 200);
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_projects_description_len'
  ) THEN
    ALTER TABLE knowledge_projects
      ADD CONSTRAINT knowledge_projects_description_len
      CHECK (length(description) <= 2000);
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'knowledge_summaries_content_len'
  ) THEN
    ALTER TABLE knowledge_summaries
      ADD CONSTRAINT knowledge_summaries_content_len
      CHECK (length(content) <= 50000);
  END IF;
END$$;

-- ═══════════════════════════════════════════════════════════════
-- D-K8-01 — summary version history table
-- Append-only history: every successful summary update inserts a
-- row with the PRE-update state (content + version + token_count).
-- Rollback creates a NEW version whose content is a copy of the
-- target — monotonic, no counter rewinds, full audit trail.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_summary_versions (
  version_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  summary_id   UUID NOT NULL
    REFERENCES knowledge_summaries(summary_id) ON DELETE CASCADE,
  user_id      UUID NOT NULL,              -- denormalised for the row filter
  version      INT NOT NULL,               -- the version this row captures
  content      TEXT NOT NULL,
  token_count  INT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  edit_source  TEXT NOT NULL DEFAULT 'manual'
    CHECK (edit_source IN ('manual','rollback'))
    -- 'llm_regen' will be added when K20 (Track 2 summary regen) lands
);

-- Uniqueness: one row per (summary, version). Prevents accidental
-- duplicates if a repo bug retries a history insert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_versions_unique
  ON knowledge_summary_versions(summary_id, version);

-- List-by-user path: the history panel orders DESC by version.
-- Partial on user_id first so cross-user access is fast-fail.
CREATE INDEX IF NOT EXISTS idx_summary_versions_user_list
  ON knowledge_summary_versions(user_id, summary_id, version DESC);

-- ═══════════════════════════════════════════════════════════════
-- D-K8-03 — optimistic concurrency column on knowledge_projects
-- knowledge_summaries has had `version INT NOT NULL DEFAULT 1` since
-- the initial K1 DDL; knowledge_projects did not. D-K8-03 needs
-- version columns on both tables so PATCH endpoints can enforce
-- If-Match / 412. Existing rows default to version=1 on backfill.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

-- ═══════════════════════════════════════════════════════════════
-- K10.3 — extraction fields on knowledge_projects
-- K1.2 (Track 1) already created embedding_model / extraction_config
-- / last_extracted_at / estimated_cost_usd / actual_cost_usd, so K10.3
-- is a narrower ALTER that only adds the columns the extraction engine
-- and budget tracker need. ADD COLUMN IF NOT EXISTS keeps the DDL
-- idempotent without a DO-block wrapper.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS monthly_budget_usd     NUMERIC(10,4),
  ADD COLUMN IF NOT EXISTS current_month_spent_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS current_month_key      TEXT,
  ADD COLUMN IF NOT EXISTS stat_entity_count      INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stat_fact_count        INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stat_event_count       INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stat_glossary_count    INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stat_updated_at        TIMESTAMPTZ;

-- K12.3 — embedding config. These columns are accessed via direct SQL
-- (same pattern as budget columns), NOT through the Project Pydantic
-- model or _SELECT_COLS — kept separate to avoid bloating generic reads.
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS embedding_provider_id  UUID,
  ADD COLUMN IF NOT EXISTS embedding_dimension    INT;

-- ═══════════════════════════════════════════════════════════════
-- K10.1 — extraction_pending
-- Events that arrived while extraction was disabled for their project.
-- When the user enables extraction, the backfill job processes these
-- oldest-first. UNIQUE(project_id, event_id) makes queueing idempotent.
--
-- Cross-DB FKs on user_id are intentionally omitted (see module header).
-- The FK on project_id is in-DB and safe; ON DELETE CASCADE keeps the
-- queue in sync when a project is purged.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS extraction_pending (
  pending_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,                     -- no FK (cross-DB)
  project_id      UUID NOT NULL
    REFERENCES knowledge_projects(project_id) ON DELETE CASCADE,
  event_id        UUID NOT NULL,                     -- loreweave_events.event_log.id (cross-DB)
  event_type      TEXT NOT NULL,
  aggregate_type  TEXT NOT NULL,
  aggregate_id    UUID NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at    TIMESTAMPTZ,
  UNIQUE (project_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_extraction_pending_unprocessed
  ON extraction_pending (project_id, created_at)
  WHERE processed_at IS NULL;

-- ═══════════════════════════════════════════════════════════════
-- K10.2 — extraction_jobs
-- User-triggered extraction runs with atomic cost tracking. K10.4's
-- atomic_try_spend pattern relies on `cost_spent_usd` + `max_spend_usd`
-- being in a single row. CHECK constraints on status/scope give us a
-- cheap defense against stringly-typed bugs reaching the DB.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS extraction_jobs (
  job_id            UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id           UUID NOT NULL,                   -- no FK (cross-DB)
  project_id        UUID NOT NULL
    REFERENCES knowledge_projects(project_id) ON DELETE CASCADE,
  scope             TEXT NOT NULL
    CHECK (scope IN ('chapters','chat','glossary_sync','all')),
  scope_range       JSONB,
  status            TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','paused','complete','failed','cancelled')),

  llm_model         TEXT NOT NULL,
  embedding_model   TEXT NOT NULL,
  max_spend_usd     NUMERIC(10,4),

  items_total       INT,
  items_processed   INT NOT NULL DEFAULT 0,
  current_cursor    JSONB,
  cost_spent_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,

  started_at        TIMESTAMPTZ,
  paused_at         TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  error_message     TEXT
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_project
  ON extraction_jobs (project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_active
  ON extraction_jobs (status)
  WHERE status IN ('pending','running','paused');

-- K16.3 — at most one active job per project. Without this, two
-- concurrent POST /extraction/start requests can both INSERT under
-- READ COMMITTED isolation (neither sees the other's uncommitted row).
-- The unique partial index makes the second INSERT fail with a
-- UniqueViolationError that the endpoint maps to 409.
CREATE UNIQUE INDEX IF NOT EXISTS idx_extraction_jobs_one_active_per_project
  ON extraction_jobs (project_id)
  WHERE status IN ('pending','running','paused');

-- ═══════════════════════════════════════════════════════════════
-- K10.2b — extraction_errors
-- Not in the original K10 task list but K11.Z depends on it: when the
-- provenance validator rejects a write, the extraction job rolls back
-- the current event and logs a row here with enough context to debug
-- the offending extractor run without replaying the whole job.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS extraction_errors (
  error_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id          UUID
    REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
  project_id      UUID NOT NULL
    REFERENCES knowledge_projects(project_id) ON DELETE CASCADE,
  error_type      TEXT NOT NULL
    CHECK (error_type IN ('provenance_validation','extractor_crash','timeout','llm_refusal','unknown')),
  field           TEXT,
  value_preview   TEXT,                              -- truncated repr, never the full blob
  reason          TEXT NOT NULL,
  source_ref      TEXT,                              -- chunk_id / chapter_id for replay
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extraction_errors_job
  ON extraction_errors (job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_errors_project
  ON extraction_errors (project_id, created_at DESC);
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
