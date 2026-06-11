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
  -- D-EMB-MODEL-REF-01: holds the provider-registry user_model UUID of
  -- the embedding model (the /internal/embed model_ref). TEXT-typed for
  -- back-compat; the value is a UUID string. Pair with embedding_dimension.
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

-- K16.12: covering index for user-wide aggregate queries that INCLUDE
-- archived projects (e.g. `check_user_monthly_budget`, GET /costs).
-- An archived project's current-month spend still counts toward the
-- user's aggregate cap, so we can't use the partial index above.
CREATE INDEX IF NOT EXISTS idx_knowledge_projects_user_all
  ON knowledge_projects(user_id);

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
    CHECK (edit_source IN ('manual','rollback','regen'))
    -- K20α extended the allow list with 'regen' so the summary
    -- regenerator can distinguish its writes from user manual edits
    -- — without this, every regen would silently trigger the 30-day
    -- user_edit_lock on the next attempt.
);

-- K20α (review-impl H1): expand the edit_source CHECK to include
-- 'regen' on existing installs. New installs get the value from the
-- table definition; this block only fires once, when a pre-K20α
-- deployment upgrades.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'knowledge_summary_versions'
      AND c.conname = 'knowledge_summary_versions_edit_source_check'
      AND pg_get_constraintdef(c.oid) ILIKE '%regen%'
  ) THEN
    ALTER TABLE knowledge_summary_versions
      DROP CONSTRAINT IF EXISTS knowledge_summary_versions_edit_source_check;
    ALTER TABLE knowledge_summary_versions
      ADD CONSTRAINT knowledge_summary_versions_edit_source_check
      CHECK (edit_source IN ('manual','rollback','regen'));
  END IF;
END$$;

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
  ADD COLUMN IF NOT EXISTS embedding_dimension    INT;

-- D-EMB-CLEANUP-01 (session 58 cycle 2 ADR §7.2): the K12.3
-- embedding_provider_id column on knowledge_projects was created but
-- never populated/read/plumbed (not in _SELECT_COLS, every writer
-- passed None). The cycle-3 fix kept embedding_model + added a separate
-- embedding_dimension column; provider_id was vestigial. Drop it.
-- The same-named column on project_embedding_benchmark_runs is a
-- DIFFERENT, ACTIVELY-USED column and is intentionally untouched.
ALTER TABLE knowledge_projects
  DROP COLUMN IF EXISTS embedding_provider_id;

-- D-RERANK-NOT-BYOK — per-project BYOK rerank model (mirrors embedding_model):
-- the user's provider-registry user_model UUID + source. NULL rerank_model ⇒
-- raw-search SKIPS the rerank step (rerank is optional, never platform-fixed).
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS rerank_model        TEXT,
  ADD COLUMN IF NOT EXISTS rerank_model_source TEXT NOT NULL DEFAULT 'user_model';

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

-- Canon Model CM3b: pin the PUBLISHED revision the worker must extract (vs the
-- live draft). Set when a chapter.published row is queued; the worker-ai
-- coalescing drainer fetches that revision's text via book-service (CM3a).
-- NULL for legacy/chat rows. Additive + idempotent.
ALTER TABLE extraction_pending ADD COLUMN IF NOT EXISTS revision_id UUID;

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
    CHECK (scope IN ('chapters','chat','glossary_sync','all','chapters_pending')),
  scope_range       JSONB,
  status            TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','paused','summarizing','complete','failed','cancelled')),

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

-- S4a (Auto-Draft Factory cost attribution): the owning campaign for a
-- campaign-dispatched extraction job. NULL for ordinary user-initiated jobs.
-- worker-ai reads this from the job row and stamps it onto every provider
-- job_meta so the campaign's extraction spend is summable (decision C).
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS campaign_id UUID;

-- E0-3 Phase 2a (D-E0-3-CALLER-PAYS-EXTRACTION): BYOK dual-identity billing.
-- A collaborator's extraction must charge the COLLABORATOR's key, never the
-- owner's (only a key's owner may cause it to be charged). These three columns
-- carry the CALLER's billing identity; everything else on the row (graph
-- partition user_id, the canonical embedding_model search tag) stays the
-- project owner's. NULL ⇒ owner-triggered (or legacy) ⇒ single-identity path,
-- resolves exactly as before. Fail-safe: worker DENIES if billing_user_id is
-- set but a billing ref is NULL (never falls back to the owner's key).
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS billing_user_id         UUID,
  ADD COLUMN IF NOT EXISTS billing_embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS billing_llm_model       TEXT;

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

-- Canon Model CM3b: add 'chapters_pending' (the worker-ai coalescing drainer
-- scope) to the scope CHECK for ALREADY-DEPLOYED tables — the inline CHECK in
-- the table definition only applies to a fresh table. Idempotent: drop-if-exists
-- then re-add (Postgres names the inline column CHECK 'extraction_jobs_scope_check').
DO $cm3b_scope$ BEGIN
  ALTER TABLE extraction_jobs DROP CONSTRAINT IF EXISTS extraction_jobs_scope_check;
  ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_scope_check
    CHECK (scope IN ('chapters','chat','glossary_sync','all','chapters_pending'));
END $cm3b_scope$;

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

-- ═══════════════════════════════════════════════════════════════
-- K14.8 — dead letter events for the event consumer
-- Events that exhausted retry attempts go here for manual inspection.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dead_letter_events (
  dlq_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  stream          TEXT NOT NULL,
  message_id      TEXT NOT NULL,
  event_type      TEXT NOT NULL,
  aggregate_id    TEXT,
  payload         JSONB,
  error           TEXT,
  retry_count     INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dlq_created
  ON dead_letter_events (created_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- K17.9.1 — project_embedding_benchmark_runs
-- Output of the K17.9 golden-set harness. One row per harness run
-- per (project, embedding_model, run_id) tuple — so re-running the
-- same fixture on the same model under the same run_id fails
-- cleanly on the UNIQUE rather than silently duplicating.
-- FE surfaces the last run's score + pass/fail gate; the harness
-- runs automatically when a user first enables extraction on a
-- project (K12.4 picker → K17.9 runner). `passed` is the decision
-- bit that actually blocks extraction if false.
-- embedding_provider_id has no FK (lives in provider-registry DB).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS project_embedding_benchmark_runs (
  benchmark_run_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id             UUID NOT NULL
    REFERENCES knowledge_projects(project_id) ON DELETE CASCADE,
  embedding_provider_id  UUID,                              -- no FK (cross-DB)
  embedding_model        TEXT NOT NULL,
  run_id                 TEXT NOT NULL,                     -- harness-emitted id
  recall_at_3            DOUBLE PRECISION,
  mrr                    DOUBLE PRECISION,
  avg_score_positive     DOUBLE PRECISION,
  stddev                 DOUBLE PRECISION,
  negative_control_pass  BOOLEAN,
  passed                 BOOLEAN NOT NULL,                  -- gate bit
  raw_report             JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, embedding_model, run_id)
);

-- Covering index for the "latest run for project" FE query and
-- for the "latest run per (project, embedding_model)" variant the
-- K12.4 picker uses when a user switches models. `created_at DESC`
-- lets the planner serve both via a single index scan.
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_project_latest
  ON project_embedding_benchmark_runs
    (project_id, embedding_model, created_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- K19b.8 — Extraction job logs.
-- User-surfaced job lifecycle events (chapter processed, skipped,
-- retry exhausted, auto-pause, fail). Worker writes via an inline
-- _append_log helper; public GET /v1/knowledge/extraction/jobs/{id}/logs
-- reads with cursor pagination on log_id. ON DELETE CASCADE so
-- removing a job cleans its logs transactionally.
-- Level vocabulary is deliberately narrow (info/warning/error) —
-- prevents stringly-typed drift.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS job_logs (
  log_id      BIGSERIAL PRIMARY KEY,
  job_id      UUID NOT NULL
    REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
  user_id     UUID NOT NULL,                   -- no FK (cross-DB)
  level       TEXT NOT NULL
    CHECK (level IN ('info','warning','error')),
  message     TEXT NOT NULL,
  context     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cursor-paginated list: WHERE user_id=$1 AND job_id=$2 AND log_id>$3
-- ORDER BY log_id ASC LIMIT N.
CREATE INDEX IF NOT EXISTS idx_job_logs_user_job_log
  ON job_logs(user_id, job_id, log_id);

-- C3 (D-K19b.8-01) — retention sweep uses
--   DELETE ... WHERE created_at < now() - make_interval(days => $1)
-- Without this index the DELETE degenerates to a seq scan once logs
-- grow past a few thousand rows. Range predicate benefits from a
-- straight BTREE on created_at; no need to widen with (user_id, ...)
-- because the retention cron is cross-tenant and never filters by
-- user_id.
CREATE INDEX IF NOT EXISTS idx_job_logs_created_at
  ON job_logs(created_at);

-- ═══════════════════════════════════════════════════════════════
-- K16.12 — User-wide monthly AI budget cap.
-- Per-project budgets live on knowledge_projects (see above). This
-- table tracks the aggregate cross-project cap; at most one row per
-- user (PK on user_id). ai_monthly_budget_usd NULL = unlimited.
-- No FK on user_id — users table lives in auth-service (cross-DB).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_knowledge_budgets (
  user_id                UUID PRIMARY KEY,
  ai_monthly_budget_usd  NUMERIC(10,4),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- C14b — sweeper_state: per-sweeper resumable cursor.
-- Wraps any tenant-wide offline sweeper that iterates users so a
-- mid-sweep crash resumes from the last-processed user on restart.
-- One row per sweeper (sweeper_name PK). Row absent = sweep runs
-- from scratch (fresh start or post-completion clear).
--
-- Currently used by:
--   - reconcile_evidence_count_scheduler (C14a) — sweeper_name =
--     'reconcile_evidence_count'. last_user_id advances per-user;
--     natural-completion path deletes the row.
--
-- Not used by the C14a quarantine-cleanup sweeper: its Cypher filter
-- (pending_validation=true) is self-advancing — invalidated facts drop
-- out on the next call, so cursor state would be redundant.
--
-- `last_scope JSONB` is the escape hatch for future sweepers that
-- need cursor state beyond user_id (e.g. per-user-per-project
-- pagination). Default empty {} keeps existing callers simple.
-- No FK on user_id — users table lives in auth-service (cross-DB).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sweeper_state (
  sweeper_name  TEXT PRIMARY KEY,
  last_user_id  UUID,
  last_scope    JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- C16 — knowledge_summary_spending: per-user-per-scope monthly spend.
-- Closes D-K20α-01: global L0 regen has no project_id and so can't
-- be recorded against knowledge_projects.current_month_spent_usd.
-- This table is the authoritative ledger for non-project-attributable
-- AI spend.
--
-- scope_type CHECK is currently restricted to 'global' only — project-
-- scope regen records via the existing K16.11 record_spending path
-- (uses project_id we already have). When a future cycle introduces
-- another non-project-attributable scope, expand the CHECK enum + the
-- Pydantic Literal in summary_spending.py in one coordinated PR.
--
-- Each (user_id, scope_type, month_key) is a single row. Inserted on
-- first spend of the month; updated atomically on subsequent. Month
-- rollover is in-place via PK shape (a new month creates a new row,
-- no manual reset) — same pattern as sweeper_state.
--
-- check_user_monthly_budget aggregates this table's matching-month
-- rows alongside knowledge_projects.current_month_spent_usd to
-- enforce the user-wide cap.
--
-- No FK on user_id (cross-DB convention).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_summary_spending (
  user_id      UUID NOT NULL,
  scope_type   TEXT NOT NULL CHECK (scope_type IN ('global')),
  month_key    TEXT NOT NULL,
  spent_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, scope_type, month_key)
);

CREATE INDEX IF NOT EXISTS idx_summary_spending_user_month
  ON knowledge_summary_spending(user_id, month_key);

-- ═══════════════════════════════════════════════════════════════
-- C17 — entity_alias_map: post-merge alias→target redirect lookup.
-- Closes D-K19d-γb-03: extraction's canonical_id is a SHA hash of the
-- name, so a re-extracted source alias post-merge resurrects the
-- merged-away entity. This table is the redirect index the resolver
-- consults BEFORE the SHA hash so future mentions of "Alice" land on
-- the merge target rather than re-creating Alice.
--
-- Key shape mirrors entity_canonical_id: (user_id, project_scope, kind,
-- canonical_alias). project_scope is TEXT carrying either project_id::text
-- or the literal string 'global' so the table doesn't need a sentinel
-- UUID for global-scope entries.
--
-- reason discriminates merge-driven rows (authoritative, written at
-- merge_entities surgery time) from backfill rows (best-effort post-deploy
-- reconstruction from existing :Entity.aliases arrays). FE/audit can show
-- different UI for each.
--
-- source_entity_id nullable because backfill cannot reconstruct the
-- pre-merge source's id; merge writes the source.id for forensics.
--
-- No FK to :Entity.id (cross-DB convention — entity lives in Neo4j).
--
-- See ADR docs/03_planning/KNOWLEDGE_SERVICE_ENTITY_ALIAS_MAP_ADR.md
-- and KSA §5.0 "Alias-redirect on merge" for full design rationale.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS entity_alias_map (
  user_id           UUID NOT NULL,
  project_scope     TEXT NOT NULL,
  kind              TEXT NOT NULL,
  canonical_alias   TEXT NOT NULL,
  target_entity_id  TEXT NOT NULL,
  source_entity_id  TEXT,
  reason            TEXT NOT NULL CHECK (reason IN ('merge', 'backfill')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_scope, kind, canonical_alias)
);

CREATE INDEX IF NOT EXISTS idx_entity_alias_map_target
  ON entity_alias_map(target_entity_id);

-- ═══════════════════════════════════════════════════════════════
-- K21.12-BE (design D9) — per-project tool-calling toggle.
-- chat-service's tool-calling loop (K21 Cycle B) gates `_stream_with_tools`
-- on this flag, surfaced through `build_context`. DEFAULT true so a
-- project row that predates the column reads back enabled — combined
-- with the Pydantic model default this means tool calling stays on for
-- every existing project until the user explicitly turns it off (the
-- toggle UI is Cycle C). ADD COLUMN IF NOT EXISTS keeps the DDL
-- idempotent; wrapped in a DO block to match the house style for the
-- post-K1 column adds above.
-- ═══════════════════════════════════════════════════════════════
DO $$
BEGIN
  ALTER TABLE knowledge_projects
    ADD COLUMN IF NOT EXISTS tool_calling_enabled BOOLEAN NOT NULL DEFAULT true;
END$$;

-- ═══════════════════════════════════════════════════════════════
-- K21-C (design D4) — per-project memory_remember confirmation gate.
-- When true, the chat-service tool-calling loop's `memory_remember`
-- writes are queued into knowledge_pending_facts (below) for explicit
-- user confirmation instead of landing directly in the graph.
-- DEFAULT false — opt-in: today's behaviour (write directly) is the
-- default so a project row that predates the column keeps writing
-- straight through. The Pydantic model default in models.py is the
-- other half of that contract. ADD COLUMN IF NOT EXISTS keeps the DDL
-- idempotent; wrapped in a DO block to match the house style for the
-- post-K1 column adds above.
-- ═══════════════════════════════════════════════════════════════
DO $$
BEGIN
  ALTER TABLE knowledge_projects
    ADD COLUMN IF NOT EXISTS memory_remember_confirm BOOLEAN NOT NULL DEFAULT false;
END$$;

-- ═══════════════════════════════════════════════════════════════
-- K21-C (design D5) — knowledge_pending_facts.
-- A pending fact is a transient queue item awaiting user confirmation,
-- not a graph node, so it lives in Postgres not Neo4j. The executor
-- INSERTs a row here (carrying the already-injection-neutralized
-- fact_text — design D6) when a project has memory_remember_confirm
-- on; the public confirm/reject endpoints (design D7) drain it.
-- `fact_text` is already neutralized at queue time, so confirm writes
-- it through to merge_fact as-is.
--
-- No FK on user_id (cross-DB convention). No FK on project_id either:
-- project_id is nullable here (a no-project chat can still queue) and
-- the executor only ever inserts a project_id it just loaded; the
-- public endpoints filter on user_id for authority.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS knowledge_pending_facts (
  pending_fact_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,                    -- no FK (cross-DB)
  project_id       UUID,                             -- nullable: no-project chats
  session_id       TEXT NOT NULL,
  fact_type        TEXT NOT NULL
    CHECK (fact_type IN ('decision','preference','milestone','negation')),
  fact_text        TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- List path: WHERE user_id=$1 [AND session_id=$2] ORDER BY created_at.
-- The optional session filter is a column equality, so a composite
-- (user_id, created_at) index serves both the all-sessions list and
-- the per-session variant (the planner filters session_id after the
-- index scan — fine at any realistic per-user pending-fact volume).
CREATE INDEX IF NOT EXISTS idx_knowledge_pending_facts_user
  ON knowledge_pending_facts(user_id, created_at);


-- ═══════════════════════════════════════════════════════════════
-- P2 (hierarchical extraction T3) — 2026-05-23
-- Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D1
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS extraction_leaves (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id              UUID NOT NULL,
  scene_id             UUID NOT NULL,
  leaf_path            TEXT NOT NULL,
  op                   TEXT NOT NULL
    CHECK (op IN ('entity','relation','event','fact')),
  task_id              TEXT NOT NULL,
  status               TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed')),
  candidates_jsonb     JSONB,
  retried_n            INT  NOT NULL DEFAULT 0,
  error_message        TEXT,
  parse_version        INT  NOT NULL DEFAULT 1,
  extractor_version    TEXT NOT NULL,
  model_ref            TEXT NOT NULL,
  glossary_anchor_size INT,
  started_at           TIMESTAMPTZ,
  completed_at         TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, leaf_path, op)
);

CREATE INDEX IF NOT EXISTS idx_extraction_leaves_task_id ON extraction_leaves(task_id);
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_pending
  ON extraction_leaves(book_id, status) WHERE status IN ('pending','running');
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_book ON extraction_leaves(book_id);

CREATE TABLE IF NOT EXISTS extraction_leaves_raw (
  extraction_leaf_id UUID PRIMARY KEY REFERENCES extraction_leaves(id) ON DELETE CASCADE,
  raw_response_jsonb JSONB NOT NULL,
  raw_token_usage    JSONB NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- D6: opt-in raw retention; defaults OFF (D-P2-FE-SAVE-RAW for FE toggle).
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS save_raw_extraction BOOLEAN NOT NULL DEFAULT false;


-- ═══════════════════════════════════════════════════════════════
-- P3 (hierarchical extraction T4 + T7 stage 1) — 2026-05-23
-- Spec: docs/specs/2026-05-23-p3-hierarchical-reduce.md §D4
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS summary_chapters (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id           UUID NOT NULL,
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, embedding_model_uuid)
);
CREATE INDEX IF NOT EXISTS idx_summary_chapters_book ON summary_chapters(book_id);

CREATE TABLE IF NOT EXISTS summary_parts (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  part_id              UUID NOT NULL,
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (part_id, embedding_model_uuid)
);
CREATE INDEX IF NOT EXISTS idx_summary_parts_book ON summary_parts(book_id);

CREATE TABLE IF NOT EXISTS summary_books (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, embedding_model_uuid)
);

-- M1 (Cycle 10 reconcile): the AUTHORITATIVE extraction_jobs.status vocabulary.
-- The status values the code EMITS must stay in sync with
-- `app.jobs.state_machine.JobStatus` + the repo guards
-- (`app.db.repositories.extraction_jobs`) + worker-ai's `_complete_job`/`_fail_job`
-- + the FE (`ExtractionJobsTab`): pending/running/paused/complete/failed/cancelled.
-- 'summarizing' is a RESERVED transitional state introduced by the original M1 —
-- it has no writer yet and is intentionally NOT in JobStatus; kept here so a future
-- summary phase can use it without a constraint migration. The original M1 added
-- 'summarizing' but silently renamed 'complete'->'completed' and DROPPED
-- 'paused'/'cancelled' — which the whole codebase still emits, so every
-- finished/paused/cancelled extraction CheckViolated and was misreported
-- (DEFERRED 065). Reconciled to the full set the code uses (a widening — never
-- rejects an existing valid row). Idempotent via DROP IF EXISTS + re-add.
-- CAVEAT: the EXCEPTION-swallow below means a failed ADD (existing-row violation /
-- lock) leaves the OLD constraint in place SILENTLY — confirm the live swap took
-- via the cycle-11 extraction smoke (a real job reaching 'complete') or
-- pg_get_constraintdef, not by migrate exit code alone.
DO $$ BEGIN
  ALTER TABLE extraction_jobs
    DROP CONSTRAINT IF EXISTS extraction_jobs_status_check;
  ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_status_check
    CHECK (status IN ('pending','running','paused','summarizing','complete','failed','cancelled'));
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Phase B (correction capture) — knowledge-service's FIRST transactional
-- outbox. User edits to the graph (entity PATCH / archive; relations + events
-- in sub-session C) emit knowledge.*_corrected events here; worker-infra's
-- relay ships them to loreweave:events:knowledge (aggregate_type='knowledge')
-- for learning-service to persist as corrections. NOTE the cross-store caveat
-- (design §6.6): the graph write is in Neo4j, this outbox is in Postgres, so
-- emission is BEST-EFFORT post-Neo4j-success — never atomic. A dropped row
-- under-counts the correction log; the §10.1 replay tool is the backstop.
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'knowledge',
  aggregate_id   UUID NOT NULL,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox_events(created_at) WHERE published_at IS NULL;

-- ═══════════════════════════════════════════════════════════════
-- Phase E2 — genre tag on knowledge_projects (2026-06-01)
-- Free-text, user-settable (e.g. "Tiên hiệp", "trinh thám").
-- Copied to extraction_runs at run-emit time for genre-segment
-- mining queries without a cross-DB join at query time.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS genre TEXT;

-- ═══════════════════════════════════════════════════════════════
-- Q4b-feed — per-run items+source sample for the online LLM judge
-- (2026-06-01). docs/plans/2026-06-01-q4b-feed-extraction-run-samples.md
--
-- The ONLY run-attributable store of the extracted items + chapter
-- source: the live persist-pass2 path writes only post-merge Neo4j
-- (no run_id), and never extraction_leaves. worker-ai writes one row
-- here per SUCCEEDED chapter run, but ONLY for projects opted into
-- save_raw_extraction (the existing raw-retention consent — same gate
-- as extraction_leaves_raw). Non-opted runs write nothing
-- (redact-by-default). learning-service's eval-runner fetches by
-- run_id to feed run_online_judge.
--
-- TRANSIENT judging buffer, not history: pruned after 7 days on
-- knowledge-service startup. items_jsonb holds the minimal judge-shape
-- projection only ({entity:[{name,kind}], relation:[{subject,predicate,
-- object,polarity}], event:[{summary,participants}]}) — confidence,
-- canonical_ids, offsets dropped.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS extraction_run_samples (
  run_id       UUID PRIMARY KEY,
  user_id      UUID NOT NULL,
  project_id   UUID,
  book_id      UUID,
  config_hash  TEXT,
  items_jsonb  JSONB NOT NULL,
  source_text  TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extraction_run_samples_created
  ON extraction_run_samples(created_at);

-- ═══════════════════════════════════════════════════════════════
-- wiki-llm M6 — wiki_gen_jobs: a batch LLM wiki-generation run over a
-- book's entities. Mirrors extraction_jobs (state machine + cost-cap)
-- with wiki specifics: book_id, the entity_ids to generate (empty = all
-- AI-eligible), items_done for skip-on-resume, and the model the user
-- picked. The state CHECK matches state_machine.py exactly.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS wiki_gen_jobs (
  job_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,                    -- no FK (cross-DB)
  project_id      UUID NOT NULL
    REFERENCES knowledge_projects(project_id) ON DELETE CASCADE,
  book_id         UUID NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','paused','complete','failed','cancelled')),
  model_source    TEXT NOT NULL,
  model_ref       TEXT NOT NULL,
  entity_ids      JSONB NOT NULL DEFAULT '[]',       -- [] = all AI-eligible entities
  items_done      JSONB NOT NULL DEFAULT '[]',       -- entity_ids already generated (skip-on-resume)
  max_spend_usd   NUMERIC(10,4),
  items_total     INT,
  items_processed INT NOT NULL DEFAULT 0,
  cost_spent_usd  NUMERIC(10,4) NOT NULL DEFAULT 0,
  started_at      TIMESTAMPTZ,
  paused_at       TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  error_message   TEXT
);
CREATE INDEX IF NOT EXISTS idx_wiki_gen_jobs_project
  ON wiki_gen_jobs (project_id, created_at DESC);
-- Per-book lock (risk #13): only ONE active job per book. A 2nd request
-- conflicts on this partial unique index → the trigger returns 409 + the
-- existing job_id. Durable (survives restart), unlike a pg advisory lock.
CREATE UNIQUE INDEX IF NOT EXISTS idx_wiki_gen_jobs_one_active_per_book
  ON wiki_gen_jobs (book_id)
  WHERE status IN ('pending','running','paused');
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
