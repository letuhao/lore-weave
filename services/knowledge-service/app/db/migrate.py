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

-- Unified Job Control Plane reconcile source: GET /internal/knowledge/jobs?since=
-- filters extraction_jobs by updated_at — index it so the periodic sweep isn't a seq-scan.
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_updated_at ON extraction_jobs(updated_at);

-- D-WORKER-SKIP-FALSE-GREEN: items that advanced the cursor WITHOUT doing any
-- work (text unavailable, retry-exhausted). A drain that skipped every chapter
-- used to read "complete N/N" — an indistinguishable success that masked the
-- book-service `_text` extraction bug. worker-ai increments this alongside
-- items_processed, and _complete_job stamps error_message when skipped >= total.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS items_skipped INT NOT NULL DEFAULT 0;

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

-- Public-MCP spend attribution (P4 / D-PMCP-WORKER-CARRIER): when a priced
-- extraction is started by a PUBLIC MCP key, the key id + the key's spend cap ride
-- the job row so worker-ai (a separate process; knowledge extraction is poll-based,
-- no AMQP) can re-set loreweave_llm.set_public_key_attribution before each provider
-- call — mirroring billing_user_id. Both also ride resume_state for the decoupled
-- terminal-event resume. NULL ⇒ first-party (or legacy) ⇒ no per-key attribution.
-- spend_cap_usd is DOUBLE PRECISION (not NUMERIC): it originates as a Python float
-- and asyncpg's numeric codec requires a Decimal (binding a float raises DataError),
-- so float8 avoids a real-PG failure that mocked tests can't catch. Coarse spend
-- ceiling, not ledger money (authoritative per-key accounting is in usage-billing).
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS mcp_key_id    TEXT,
  ADD COLUMN IF NOT EXISTS spend_cap_usd DOUBLE PRECISION;

-- LLM re-arch Phase 2b WX-T1 (worker-ai extraction decouple): event-driven resume
-- state. extract_pass2 is a multi-stage DAG with a concurrent fan-in (entity →
-- gather(relation,event,fact) → recovery → filter, × chunks), so the decoupled
-- orchestrator must persist (a) the IN-FLIGHT job set — the trio puts ≥3 jobs in
-- flight at once → fan-in on all their terminal events — and (b) an explicit
-- partial-extraction blob (stage cursor + per-op accumulators) that can't be
-- reconstructed from anything else. All additive; NULL ⇒ legacy synchronous path
-- (zero behavior change until extraction_decouple_enabled flips on). See
-- docs/plans/2026-06-11-llm-rearch-phase2b-workerai-extraction-decouple-design.md.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS provider_job_ids JSONB,
  ADD COLUMN IF NOT EXISTS resume_state     JSONB,
  ADD COLUMN IF NOT EXISTS pipeline_stage   TEXT;

-- bug #37 — realized LLM-call counter for the Jobs GUI ("LLM calls: done / estimated").
-- Incremented at each provider-job submit (the decoupled consumer's _submit_map fan-out +
-- the inline entity submit); surfaced on the unified job's params.llm_calls_done. NOT NULL
-- DEFAULT 0 so every pre-existing + omitting job reads 0, never NULL.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS llm_calls_made INT NOT NULL DEFAULT 0;

-- C12 — target-typed extraction. `targets` selects which Pass-2 passes a
-- build runs (entities/relations/events/facts/summaries). NOT NULL with a
-- DEFAULT of ALL passes ⇒ every pre-C12 job + every caller that omits the
-- field gets the original behaviour unchanged (the SDK + orchestrator
-- treat the full set as "run all"). Requesting any of {relations,events,
-- facts} auto-includes `entities` (enforced in the request layer + SDK
-- guard, not the column). `concurrency_level` is a passthrough cap on
-- parallel LLM calls; NULL ⇒ current unbounded behaviour. Both additive.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS targets TEXT[] NOT NULL
    DEFAULT ARRAY['entities','relations','events','facts','summaries'],
  ADD COLUMN IF NOT EXISTS concurrency_level INT;

-- C13 — glossary pinning. `pinned_entity_ids` is the set of glossary entity
-- ids the user chose to force-inject into EVERY extraction window's
-- known_entities context (so sparse-but-critical entities stay anchored even
-- in chapters that never mention them). JSONB array of id strings; NULL ⇒ no
-- pins (back-compat — pre-C13 jobs + any caller that omits the field). The
-- worker reads it, batch-fetches the names from glossary-service, and prepends
-- them to known_entities. Additive.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS pinned_entity_ids JSONB;

-- D-RE-OTHER-AGENTIC-EFFORT: the clamped graded reasoning effort (none|low|medium|high) the
-- kg_build_graph cost-gate captured (clamped to the caller's grant at mint + confirm). worker-ai
-- honors it via D-KG-WORKER-GRADED-EFFORT. Additive + idempotent; default 'none' ⇒ no behavior
-- change for existing rows / callers that omit it.
ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS reasoning_effort TEXT NOT NULL DEFAULT 'none';

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
  session_id       TEXT,                             -- WS-2.1: nullable — a diary fact has no session
  fact_type        TEXT NOT NULL
    -- WS-2.1: 'statement' is the diary's fact kind (the distiller's coarse facts land here). The
    -- narrower chat-memory kinds stay for the memory_remember path.
    CHECK (fact_type IN ('decision','preference','milestone','negation','statement','commitment')),
  fact_text        TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- WS-2.1 — bring EXISTING knowledge_pending_facts rows up to the new shape (the CREATE TABLE above
-- only runs on a fresh DB). Idempotent: widen the fact_type CHECK to include 'statement' and drop the
-- session_id NOT NULL so a diary fact (no session) can queue. (Memory: a new enum value must widen
-- the CHECK via DROP-then-ADD, and NOT NULL must be dropped explicitly — the CREATE TABLE won't.)
DO $$
BEGIN
  -- Replace whatever fact_type CHECK exists with the widened one. WS-5.7 adds 'commitment':
  -- an ALREADY-migrated DB has the `_ck` constraint WITHOUT it, so we must DROP-then-re-ADD
  -- (a bare `IF NOT EXISTS ADD` would skip the re-widen — the recurring "migration must
  -- re-widen an existing CHECK, not just add-if-absent" trap).
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_pending_facts_fact_type_check') THEN
    ALTER TABLE knowledge_pending_facts DROP CONSTRAINT knowledge_pending_facts_fact_type_check;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_pending_facts_fact_type_ck') THEN
    ALTER TABLE knowledge_pending_facts DROP CONSTRAINT knowledge_pending_facts_fact_type_ck;
  END IF;
  ALTER TABLE knowledge_pending_facts
    ADD CONSTRAINT knowledge_pending_facts_fact_type_ck
    CHECK (fact_type IN ('decision','preference','milestone','negation','statement','commitment'));
  -- Drop the legacy session_id NOT NULL (diary facts have no session).
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'knowledge_pending_facts' AND column_name = 'session_id' AND is_nullable = 'NO'
  ) THEN
    ALTER TABLE knowledge_pending_facts ALTER COLUMN session_id DROP NOT NULL;
  END IF;
END$$;

-- WS-2.2 (dedup) — a stable dedup key so a re-distill of the same day does NOT duplicate its facts in
-- the inbox (the distiller re-queues on every "End my day"; without this the inbox grows unbounded on
-- re-runs). NULL for the legacy chat-memory queue path (no dedup there). The partial UNIQUE only
-- covers the diary path (dedup_key IS NOT NULL), so the ON CONFLICT DO NOTHING insert is idempotent.
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS dedup_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_pending_facts_dedup
  ON knowledge_pending_facts(user_id, project_id, dedup_key)
  WHERE dedup_key IS NOT NULL;

-- WS-2.2 (structured s/p/o) — recall must answer "what did <person> SAY about <topic>", which needs the
-- fact decomposed: subject (who/what it is about — the :ABOUT anchor at promote time), predicate, object,
-- and the event_date (the day it is true of, distinct from created_at). provenance separates what the USER
-- said from a QUOTED third party (a pasted email) so the review UI and recall never mis-attribute. All
-- nullable: a coarse legacy statement fact carries only fact_text; a structured one carries the trio too.
-- The dedup_key is derived from the trio when present (stable across LLM re-phrasings), else from fact_text.
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS subject     TEXT;
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS predicate   TEXT;
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS object      TEXT;
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS event_date  DATE;
ALTER TABLE knowledge_pending_facts ADD COLUMN IF NOT EXISTS provenance  TEXT;

-- WS-2.2 (rejection tombstone) — today reject is a hard DELETE, so the very next distill re-proposes the
-- exact fact the user just dismissed (a re-nagging loop). A tombstone remembers the dismissal by the SAME
-- dedup_key the queue uses, so the queue skips a tombstoned fact. Scoped per (user, project, dedup_key);
-- keyed identically to the pending dedup so a promote/queue and a reject can never disagree on identity.
CREATE TABLE IF NOT EXISTS knowledge_rejected_facts (
  user_id      UUID NOT NULL,
  project_id   UUID NOT NULL,   -- diary facts are always project-scoped; PK forbids NULL anyway
  dedup_key    TEXT NOT NULL,
  rejected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id, dedup_key)
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

-- ── WS-1.3 · the assistant project (spec 01 §4.1.1, decision D6) — 2026-07-12 ──
--
-- is_assistant marks the ONE project that backs a user's work-assistant / diary. Additive
-- marker column; project_type's CHECK is deliberately NOT widened (it stays
-- book|translation|code|general) — the assistant project IS a book project (its book is the
-- diary), and widening a CHECK that five services switch on would be a far larger blast
-- radius than a boolean.
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS is_assistant BOOLEAN NOT NULL DEFAULT false;

-- Exactly ONE assistant project per user. Provisioning is a multi-service fan-out that can
-- be retried, double-clicked, or raced across two devices; without this a user ends up with
-- two assistant projects and their memory silently splits in half.
-- (Partial index — it must exempt archived rows, or a user who archived an old assistant
-- project could never provision a new one: the partial-unique-must-exempt-tombstones lesson.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_projects_one_assistant_per_user
  ON knowledge_projects(user_id)
  WHERE is_assistant = true AND is_archived = false;

-- ⚠️ chat_turn_extraction_enabled DEFAULTS **FALSE** — fail CLOSED.
--
-- The v2 spec had this DEFAULT true. That is fail-OPEN on a privacy flag, on the exact
-- table that already shipped this bug once (canon_capture_enabled ships DEFAULT false and
-- carries a corrective self-disarm migration for precisely this mistake).
--
-- Why it matters: provisioning is a multi-service fan-out that CAN partially fail. With a
-- true default, a half-provisioned assistant would extract EVERY TURN of an all-day work
-- session as trusted canon — the exact outcome D6 exists to prevent. A privacy flag must
-- never arrive switched on by accident.
--
-- NOTE: the effective gate is DERIVED, never stored:
--     may_extract_chat_turn = (NOT is_assistant) AND chat_turn_extraction_enabled
-- Storing a copy of that answer is how the two consumers (handle_chat_turn and worker-ai's
-- drainer) drift apart, and a one-sided gate is a silent-success bug. See
-- app/events/gating.py.
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS chat_turn_extraction_enabled BOOLEAN NOT NULL DEFAULT false;

-- One-row-per-step marker so a DATA backfill runs EXACTLY ONCE, not on every startup.
-- (knowledge-service has no migration ledger; this mirrors book-service's
-- canon_model_migration table, which exists for precisely this reason.)
CREATE TABLE IF NOT EXISTS knowledge_data_migration (
  id         TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Explicit backfill: EXISTING projects were extracting chat turns unconditionally, so a
-- DEFAULT false would silently switch that off for every current user. A DEFAULT never
-- revisits existing rows, so this must be a real UPDATE. The assistant project is the ONE
-- kind that stays off (its facts come from the confirmed daily entry — D6).
--
-- ⚠️ MARKER-GATED, and that is the whole point — this is a USER SETTING, not a derived value.
-- migrate.py runs on EVERY service start. An ungated UPDATE would therefore re-run forever
-- and silently flip `chat_turn_extraction_enabled` back to TRUE for any user who had
-- deliberately turned it OFF for one of their projects — a privacy toggle undone by a
-- restart, with no event and nothing in any log.
--
-- This is the SAME bug the kg_indexed backfill was marker-gated to prevent (RUN-STATE D-R7),
-- one slice later, after I had written the lesson down. A backfill that touches a column a
-- HUMAN can change must run exactly once. See RUN-STATE DR-9.
DO $ctx1$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM knowledge_data_migration WHERE id = 'chat_turn_extraction_backfill_v1') THEN
    UPDATE knowledge_projects
       SET chat_turn_extraction_enabled = true
     WHERE is_assistant = false AND chat_turn_extraction_enabled = false;
    INSERT INTO knowledge_data_migration (id) VALUES ('chat_turn_extraction_backfill_v1');
  END IF;
END $ctx1$;

-- WS-0.1 (2026-07-11) — chapter-scoped cache invalidation.
-- Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.3 (P0-4).
--
-- `chapter.scenes_reparsed` used to invalidate BOOK-scoped (delete_by_book), which
-- was tolerable only while publish was rare and deliberate. Publish-independent
-- indexing makes "add to knowledge" a frequent per-chapter click, so a book-scoped
-- wipe would re-pay the LLM cost for all 200 chapters on every single click.
--
-- Why a NEW column rather than keying the delete on `scene_id`: `scene_id` currently
-- holds the chapter_id as an explicit PLACEHOLDER (pass2_orchestrator: "placeholder
-- until per-scene fanout", D-P2-PER-SCENE-FANOUT). A delete keyed on scene_id works
-- today and would silently match ZERO rows the day real per-scene fanout lands —
-- leaving a stale extraction cache (a correctness bug), not just a cost bug.
--
-- Backfill is correct by construction: every existing row was written with
-- scene_id := chapter_id. NOT NULL is then enforced so a future writer that forgets
-- to set chapter_id fails loudly instead of orphaning a leaf that no invalidation
-- can ever reach.
ALTER TABLE extraction_leaves
  ADD COLUMN IF NOT EXISTS chapter_id UUID;
UPDATE extraction_leaves SET chapter_id = scene_id WHERE chapter_id IS NULL;
ALTER TABLE extraction_leaves ALTER COLUMN chapter_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_chapter
  ON extraction_leaves(book_id, chapter_id);


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

-- ═══════════════════════════════════════════════════════════════
-- entity_canonical_snapshots  (F3 — Incremental Temporal Knowledge, §12.1)
-- A PER-ENTITY, ordinal-stamped canonical snapshot — the bounded "who is this
-- entity as of chapter N" prose. DISTINCT from the book-STRUCTURAL summary tree
-- above (summary_chapters/parts/books), which is chapter->part->book, not
-- per-entity. Aligned to the glossary `canonical_snapshot` versioned-cache model.
--
-- It is a LAZY, VERSIONED, REGENERABLE CACHE — NEVER truth (INV-FACTS: the facts
-- in Neo4j are the only source of truth; this is a rebuildable projection).
-- Keyed by (entity_id, attr_scope, as_of_ordinal, fold_algo_version):
--   * as_of_ordinal     — the chapter ordinal this snapshot projects (the head,
--                         or any explicitly-pinned N). A fresh re-ground at a new
--                         ordinal mints a NEW row (the row IS the version).
--   * fold_algo_version — bumped when the fold prompt/model/strategy changes; a
--                         stale-version row is invalid -> rebuild-on-read (B0/F6).
--   * fact_coverage_at  — the max fact `updated_at` (story-time) the snapshot
--                         folded in. A snapshot is VALID iff fold_algo_version ==
--                         current AND no fact with valid_from_ordinal <=
--                         as_of_ordinal has an updated_at newer than this. A late /
--                         back-filled fact bumps the entity's max updated_at ->
--                         every snapshot@>=that ordinal goes stale -> next read
--                         rebuilds (self-healing per B3). (Neo4j has no PG txid, so
--                         we use the fact updated_at timestamp as the coverage key.)
--   * content_hash      — sha256 of `content`; the translation cache + diff view
--                         key on THIS (re-ground that changes content => new hash
--                         => cache miss; identical content => hit) (D8).
-- B4 — fold failure has explicit state so a poison fact can't wedge an entity
-- forever: fold_attempts + fold_failed_at + canonical_status; after N fails the
-- item is 'unbuildable' (FE shows the structured facts instead of a broken card).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS entity_canonical_snapshots (
  id                  UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id             UUID NOT NULL,                  -- no FK (cross-DB) — tenant
  project_id          UUID,                           -- no FK (cross-DB)
  -- The Neo4j :Entity canonical id (TEXT, content-hashed). No FK (Neo4j-side).
  entity_id           TEXT NOT NULL,
  -- 'narrative' folded prose. Multi-valued attrs (aliases/tags) are NOT folded
  -- here — they are structured facts queried directly (§12.1 D9). attr_scope
  -- leaves room for a future per-attribute scope without a migration.
  attr_scope          TEXT NOT NULL DEFAULT 'narrative',
  as_of_ordinal       BIGINT NOT NULL,                -- the chapter ordinal projected
  content             TEXT NOT NULL DEFAULT '',       -- the bounded prose (<= canonicalMaxRunes)
  content_hash        TEXT NOT NULL,                  -- sha256(content) — translation/diff key
  fold_algo_version   INT  NOT NULL DEFAULT 1,        -- bumped on prompt/model/strategy change
  fact_coverage_at    TIMESTAMPTZ,                    -- max fact updated_at folded in (staleness key)
  -- B4 — fold failure state (mirrors the KG RETRY_BUDGET=3 + backoff).
  canonical_status    TEXT NOT NULL DEFAULT 'ready'
    CHECK (canonical_status IN ('ready','dirty','building','unbuildable')),
  fold_attempts       INT  NOT NULL DEFAULT 0,
  fold_failed_at      TIMESTAMPTZ,
  built_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- The cache identity: a (entity, scope, ordinal, algo_version) tuple is ONE
  -- regenerable row. A re-ground at a new algo_version or ordinal is a new row.
  UNIQUE (entity_id, attr_scope, as_of_ordinal, fold_algo_version)
);
-- The hot "current head" / pinned-ordinal lookup: newest snapshot per
-- (user, entity, scope) at or below a queried ordinal.
CREATE INDEX IF NOT EXISTS idx_entity_canon_snap_lookup
  ON entity_canonical_snapshots(user_id, entity_id, attr_scope, as_of_ordinal DESC);
-- Re-fold queue: find dirty / unbuildable snapshots to (re)build.
CREATE INDEX IF NOT EXISTS idx_entity_canon_snap_status
  ON entity_canonical_snapshots(user_id, canonical_status)
  WHERE canonical_status IN ('dirty','building');

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
-- C23-fix (dị bản G2) — derivative-project flag on knowledge_projects.
-- A DERIVATIVE work's knowledge project must get its OWN fresh partition
-- and must NEVER be returned by the SOURCE book's per-(user,book)
-- get-or-create dedup (create_or_get) or by get_by_book — otherwise the
-- derivative inherits the source's project_id and composition's
-- uq_composition_work_project (1 work : 1 project) is violated (the
-- UniqueViolationError that 500'd POST /works/{id}/derive). Additive +
-- backward-compatible: DEFAULT false ⇒ every existing row + every
-- non-derivative create path behaves exactly as before. The repo's
-- create_or_get/get_by_book SELECTs add `AND NOT is_derivative` so a
-- derivative is excluded from the source book's dedup; the derive path
-- sets force_new=true which both skips the dedup lock/select AND stamps
-- is_derivative=true. ADD COLUMN IF NOT EXISTS keeps the DDL idempotent.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS is_derivative BOOLEAN NOT NULL DEFAULT false;

-- ═══════════════════════════════════════════════════════════════
-- Phase E2 — genre tag on knowledge_projects (2026-06-01)
-- Free-text, user-settable (e.g. "Tiên hiệp", "trinh thám").
-- Copied to extraction_runs at run-emit time for genre-segment
-- mining queries without a cross-DB join at query time.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS genre TEXT;

-- ═══════════════════════════════════════════════════════════════
-- G4 (world-level knowledge project, 2026-06-15) — world_id binding.
-- A world's dedicated knowledge partition (bound to its hidden bible
-- book) carries world_id so it has first-class identity independent of
-- "the project whose book_id == the bible book". FK-by-convention to
-- book-service worlds.id (cross-DB, no SQL FK — same as user_id/book_id).
-- NULL for every normal per-book / general / derivative project, so the
-- column is additive + backward-compatible (existing rows read back NULL).
-- The partial index serves the world-rollup resolver (list WHERE world_id);
-- the HOME projects browser excludes world_id IS NOT NULL rows in the repo.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS world_id UUID;

CREATE INDEX IF NOT EXISTS idx_knowledge_projects_world
  ON knowledge_projects(world_id) WHERE world_id IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- D-JOURNEY-KG-BENCHMARK-UX (R1) — hidden per-(user, embedding_model)
-- benchmark SANDBOX projects. The K17.9 embedding benchmark runs on a
-- dedicated empty project (the runner refuses any project with real
-- passages), but the build gate is now MODEL-scoped, so a passing run on
-- this sandbox unlocks every real project using the same model — without
-- the run ever touching (or polluting) the content-bearing build project.
-- Sandboxes are owner-scoped, book_id IS NULL, and excluded from every
-- user-facing project listing.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE knowledge_projects
  ADD COLUMN IF NOT EXISTS is_benchmark_sandbox BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_knowledge_projects_benchmark_sandbox
  ON knowledge_projects(user_id, embedding_model) WHERE is_benchmark_sandbox;

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

-- wiki-llm W4a — per-entity result detail + live sub-step progress (the FE
-- screen-③ results table). `results` is an OBJECT keyed by entity_id →
-- {outcome, citations, flags, name}; it carries both the in-flight ('processing')
-- and finished rows (cheap idempotent upsert via `|| jsonb_build_object`, so a
-- resume/retry overwrites). `current_entity_id`/`current_pass` point at the one
-- in-flight entity + its pipeline pass (context|generate|verify|revise|writeback);
-- both are NULL when no entity is processing (cleared at complete/pause/fail).
ALTER TABLE wiki_gen_jobs
  ADD COLUMN IF NOT EXISTS results            JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS current_entity_id  TEXT,
  ADD COLUMN IF NOT EXISTS current_pass       TEXT;

-- wiki-llm W5 (D-WIKI-PER-STEP-MODEL) — an OPTIONAL second model for the
-- corrective revise re-gen ("write with A, fix canon-flagged articles with B").
-- NULL ⇒ the revise reuses the prose model_ref/model_source (unchanged behavior).
-- verify_article is rule-based (no LLM), so this only affects revise_article.
ALTER TABLE wiki_gen_jobs
  ADD COLUMN IF NOT EXISTS revise_model_ref    TEXT,
  ADD COLUMN IF NOT EXISTS revise_model_source TEXT;

-- D-RE-OTHER-AGENTIC-EFFORT: clamped reasoning effort for the wiki-gen LLM (kg_build_wiki
-- cost-gate, clamped to the caller's grant at mint). Additive; default 'none' (no thinking).
ALTER TABLE wiki_gen_jobs
  ADD COLUMN IF NOT EXISTS reasoning_effort TEXT NOT NULL DEFAULT 'none';

-- ═══════════════════════════════════════════════════════════════
-- KG CUSTOMIZABLE ONTOLOGY (epic 2026-06-20, lane L1) — additive.
-- Tiered graph schemas (system/user/project) describing GRAPH SHAPE
-- (edge types · fact/state types · controlled vocab · expected node
-- kinds). Postgres is SSOT; Neo4j stays derived. Scope-keyed UNIQUE
-- (NULLS NOT DISTINCT) — never UNIQUE(code) globally (the glossary
-- kinds-bug class). Nothing reads these until a project adopts, so old
-- projects are unaffected (additive-first).
-- Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS kg_graph_schemas (
  schema_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  scope            TEXT NOT NULL CHECK (scope IN ('system','user','project')),
  scope_id         TEXT,                       -- NULL=system; user_id; project_id
  code             TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  name             TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  description      TEXT NOT NULL DEFAULT '',
  schema_version   INT  NOT NULL DEFAULT 1,
  -- Q2 (LOCKED S0): true => off-vocab free-string predicates allowed
  -- (today's behavior); false => closed to kg_edge_types (off-vocab → triage).
  allow_free_edges BOOLEAN NOT NULL DEFAULT true,
  content_hash     TEXT,                        -- semantic surface hash, for Sync
  source_ref       TEXT,                        -- 'system:<id>' | 'user:<id>' | NULL native
  source_hash      TEXT,                        -- upstream content_hash frozen at adopt
  deprecated_at    TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- scope-keyed uniqueness; NULLS NOT DISTINCT so two system rows can't share a
-- code. PARTIAL (active rows only) — review-impl: replace-on-adopt deprecates
-- the prior project schema then inserts a fresh copy with the SAME code, so a
-- deprecated row must NOT occupy the (scope,scope_id,code) slot (else re-adopting
-- the same template — or the M1 fill-glossary-then-re-adopt flow — would hit a
-- unique violation). Uniqueness is enforced among NON-deprecated rows only.
DROP INDEX IF EXISTS idx_kg_graph_schemas_scope_code;
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_graph_schemas_active_scope_code
  ON kg_graph_schemas (scope, scope_id, code) NULLS NOT DISTINCT
  WHERE deprecated_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kg_graph_schemas_scope
  ON kg_graph_schemas (scope, scope_id);

CREATE TABLE IF NOT EXISTS kg_edge_types (
  edge_type_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  schema_id           UUID NOT NULL REFERENCES kg_graph_schemas(schema_id) ON DELETE CASCADE,
  code                TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  label               TEXT NOT NULL,
  directed            BOOLEAN NOT NULL DEFAULT true,
  source_node_kinds   TEXT[] NOT NULL DEFAULT '{}',   -- glossary kind codes (soft ref)
  target_node_kinds   TEXT[] NOT NULL DEFAULT '{}',
  temporal            BOOLEAN NOT NULL DEFAULT false,  -- true => valid_from + EVIDENCED_BY required (L7)
  provenance_required BOOLEAN NOT NULL DEFAULT false,
  cardinality         TEXT NOT NULL DEFAULT 'multi_active'
                        CHECK (cardinality IN ('single_active','multi_active')),
  description         TEXT NOT NULL DEFAULT '',
  deprecated_at       TIMESTAMPTZ,
  UNIQUE (schema_id, code)
);

CREATE TABLE IF NOT EXISTS kg_fact_types (
  fact_type_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  schema_id        UUID NOT NULL REFERENCES kg_graph_schemas(schema_id) ON DELETE CASCADE,
  code             TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  label            TEXT NOT NULL,
  description      TEXT NOT NULL DEFAULT '',
  deprecated_at    TIMESTAMPTZ,
  UNIQUE (schema_id, code)
);

-- M1 (LOCKED S0): expected node-kinds anchored to glossary, with adopt strength.
-- `required` gates adopt (block if glossary missing); `optional` warns + triages.
CREATE TABLE IF NOT EXISTS kg_schema_node_kinds (
  schema_node_kind_id UUID PRIMARY KEY DEFAULT uuidv7(),
  schema_id           UUID NOT NULL REFERENCES kg_graph_schemas(schema_id) ON DELETE CASCADE,
  kind_code           TEXT NOT NULL CHECK (length(kind_code) BETWEEN 1 AND 120),
  strength            TEXT NOT NULL CHECK (strength IN ('required','optional')),
  deprecated_at       TIMESTAMPTZ,
  UNIQUE (schema_id, kind_code)
);

CREATE TABLE IF NOT EXISTS kg_vocab_sets (
  vocab_set_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  schema_id        UUID NOT NULL REFERENCES kg_graph_schemas(schema_id) ON DELETE CASCADE,
  code             TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  label            TEXT NOT NULL,
  description      TEXT NOT NULL DEFAULT '',
  closed           BOOLEAN NOT NULL DEFAULT true,  -- true => assign-only, no coin
  deprecated_at    TIMESTAMPTZ,
  UNIQUE (schema_id, code)
);

CREATE TABLE IF NOT EXISTS kg_vocab_values (
  vocab_value_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  vocab_set_id     UUID NOT NULL REFERENCES kg_vocab_sets(vocab_set_id) ON DELETE CASCADE,
  code             TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  label            TEXT NOT NULL,
  metadata         JSONB NOT NULL DEFAULT '{}',    -- e.g. { axis, has_target, archetype } for drive
  deprecated_at    TIMESTAMPTZ,                    -- A4: soft-deprecate, never hard-drop (review-impl HIGH)
  UNIQUE (vocab_set_id, code)
);
-- review-impl HIGH: existing DBs created kg_vocab_values before deprecated_at —
-- A4 (never hard-drop a row that may have referencing graph data) requires the
-- column so sync removed_upstream can deprecate instead of DELETE.
ALTER TABLE kg_vocab_values ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;

-- NOTE (KG full-CRUD, spec-review EC-A1): the child tables keep their TOTAL
-- UNIQUE(schema_id, code) — deprecate-then-recreate is handled at the app layer by
-- REVIVE-on-recreate (add_* un-deprecates + overwrites a soft-deleted row of the
-- same code) rather than a partial-unique index that would let duplicate-code rows
-- accumulate. Total-unique keeps exactly one row per code, so (a) sync's unfiltered
-- `WHERE schema_id AND code` lookups stay single-row, and (b) graph data that
-- references a type by code has one unambiguous target. See ontology_mutations
-- `_revive_or_insert`.

-- Layer 3 views — per-user named lenses over a project graph (READ-only).
CREATE TABLE IF NOT EXISTS kg_views (
  view_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id       TEXT NOT NULL,
  user_id          UUID NOT NULL,                  -- owner (view per-user in shared project)
  code             TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 120),
  name             TEXT NOT NULL,
  description      TEXT NOT NULL DEFAULT '',
  edge_type_codes  TEXT[] NOT NULL DEFAULT '{}',
  node_kind_codes  TEXT[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, user_id, code)
);

-- Triage queue (spec §3.7) — extraction elements that don't match the resolved
-- schema park here (NOT written to Neo4j) and resolve human-gated by signature.
CREATE TABLE IF NOT EXISTS kg_triage_items (
  triage_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,
  project_id       TEXT NOT NULL,
  source           JSONB NOT NULL DEFAULT '{}',    -- {run_id, chapter_id, chapter_ord}
  item_type        TEXT NOT NULL CHECK (item_type IN
                     ('unknown_node_kind','unknown_edge_type','edge_kind_mismatch',
                      'unknown_vocab_value','edge_cardinality_conflict','proposed_edge')),
  payload          JSONB NOT NULL DEFAULT '{}',
  signature        TEXT NOT NULL,                  -- normalized group key, e.g. "drive:curiosity"
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                     ('pending','pending_glossary','resolved','dismissed')),
  resolution       JSONB,
  schema_version   INT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at      TIMESTAMPTZ,
  resolved_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_kg_triage_user_project_status
  ON kg_triage_items (user_id, project_id, status);
CREATE INDEX IF NOT EXISTS idx_kg_triage_project_signature
  ON kg_triage_items (project_id, signature);
-- D-KG-LF-PROPOSE-EDGE-INBOX: a well-formed on-schema edge PROPOSED by the agent
-- (kg_propose_edge) is a clean draft awaiting human placement — NOT a cardinality
-- conflict (a stateful condition the tool can't check per INV-K1). It gets its own
-- `proposed_edge` item_type. Existing DBs created the CHECK with the old 5-member
-- list; widen it idempotently (drop-then-add the auto-named column CHECK).
ALTER TABLE kg_triage_items DROP CONSTRAINT IF EXISTS kg_triage_items_item_type_check;
ALTER TABLE kg_triage_items ADD CONSTRAINT kg_triage_items_item_type_check
  CHECK (item_type IN ('unknown_node_kind','unknown_edge_type','edge_kind_mismatch',
                       'unknown_vocab_value','edge_cardinality_conflict','proposed_edge'));

-- ═══════════════════════════════════════════════════════════════
-- consumed_tokens (KM6 — class-C confirm-token single-use ledger, spec §13.4)
-- Backs the single-use guarantee of the generalized confirm machinery
-- (app/ontology/confirm.py + routers/public/kg_actions.py): a confirm-token's jti
-- is recorded here the FIRST time it is redeemed, so a replay of the SAME token
-- finds the row present and is rejected (the C2 guarantee). `exp` lets a future
-- janitor prune long-expired rows; correctness does not depend on pruning — the PK
-- dedup is what enforces single-use. Mirrors glossary's consumed_tokens.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS consumed_tokens (
  jti         TEXT PRIMARY KEY,
  descriptor  TEXT NOT NULL,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  exp         TIMESTAMPTZ NOT NULL
);

-- ═══════════════════════════════════════════════════════════════
-- session_working_memory — the pinned goal-state block (SSOT).
-- docs/specs/2026-06-23-interview-roleplay.md (M4).
--
-- `charter` and `state` are SEPARATE columns ON PURPOSE: the repo exposes
-- update_state() but NO update_charter(), so the summarizing executive (M5)
-- can structurally never write the goal — only the goal authority writes
-- `charter`, once, via init (ON CONFLICT DO NOTHING keeps it frozen and
-- preserves any state). For interview the authority is chat-service pushing
-- the template charter; for roleplay it is the world model (the POC seam).
-- Keyed by session_id (working memory is per-session, not per-project), with
-- user_id for tenant scoping. No cross-DB FK (session_id lives in loreweave_chat).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS session_working_memory (
  session_id  UUID PRIMARY KEY,                            -- no FK (cross-DB)
  user_id     UUID NOT NULL,
  charter     JSONB NOT NULL,
  state       JSONB NOT NULL DEFAULT '{"phase":"","covered":[]}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- event_text_translations — KG-TL M3 (docs/specs/2026-06-26-kg-timeline-
-- localization.md §5d). On-demand + CACHED Layer-2 translation of free-text
-- :Event fields (summary / time_cue / title) for the Timeline tab. Structurally
-- identical to glossary's `attribute_translations` cache: the read coalesces to
-- source with a `translated` flag, the lazy write upserts a MACHINE translation
-- and NEVER clobbers a `verified` one.
--
-- Layer-1 invariant (AC-T6): the :Event node fields stay source-language; this
-- table is the ONLY place a localized event-text value lives. The :Event node is
-- in Neo4j, so there's no cross-store FK — `event_id` is the Neo4j node id and
-- `user_id` + `project_id` carry the tenant/purge scope (AC-T7): deleting a
-- book/project's events deletes these rows via the same purge sweep that clears
-- the graph partition (a project purge filters by project_id; a book purge maps
-- book → project_id). `source_hash` invalidates a stale translation when the
-- source field is edited (re-translate on hash change — mirrors glossary's
-- confidence<>'verified' upsert guard, applied to the source text).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS event_text_translations (
  event_id       TEXT NOT NULL,                 -- Neo4j :Event node id (no cross-store FK)
  field          TEXT NOT NULL
    CHECK (field IN ('summary','time_cue','title')),
  language_code  TEXT NOT NULL,                 -- primary subtag (e.g. 'vi')
  value          TEXT NOT NULL,
  source_hash    TEXT NOT NULL,                 -- sha256 of the source text this row translates
  confidence     TEXT NOT NULL DEFAULT 'machine'
    CHECK (confidence IN ('machine','verified')),
  translator     TEXT NOT NULL DEFAULT 'knowledge-timeline',
  user_id        UUID NOT NULL,                 -- tenant scope (no cross-DB FK)
  project_id     UUID,                          -- purge scope; NULL = global-scope event
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, field, language_code)
);
-- Purge-cascade lookups: a project/book delete sweeps its cache rows by project.
CREATE INDEX IF NOT EXISTS idx_event_text_translations_project
  ON event_text_translations(project_id);
CREATE INDEX IF NOT EXISTS idx_event_text_translations_user
  ON event_text_translations(user_id);

-- ═══════════════════════════════════════════════════════════════
-- entity_access_log (Track 4 P0 — salience substrate)
-- Records how often / how recently each GLOSSARY entity is SURFACED into a
-- user's context block (L2-fact / L3-passage entities are not tracked here —
-- glossary entities are the unit of "importance"), so salience can be LEARNED (R-T4-01)
-- instead of guessed by static tier. Tenancy: scoped per (user, project) —
-- NEVER a shared/global signal (a UNIQUE(entity_id) without the scope key
-- would be the tenancy bug the project guards against). Purged with the
-- project (project_id scope). Written fire-and-forget AFTER the context
-- block renders (off the latency path); read by the P1 salience blend.
-- `decayed_score` is refreshed by the nightly Ebbinghaus decay job (P1);
-- `retrieval_count` is the raw lifetime counter.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS entity_access_log (
  user_id           UUID NOT NULL,                       -- tenant scope (no cross-DB FK)
  project_id        UUID NOT NULL,                       -- purge + tenant scope
  entity_id         TEXT NOT NULL,                       -- Neo4j :Entity id / glossary_entity_id
  retrieval_count   BIGINT NOT NULL DEFAULT 0,           -- raw lifetime surface count
  decayed_score     DOUBLE PRECISION NOT NULL DEFAULT 0, -- Ebbinghaus-decayed (nightly, P1)
  last_retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id, entity_id)
);
-- Read path: the salience blend loads a project's rows for the current user.
CREATE INDEX IF NOT EXISTS idx_entity_access_log_scope
  ON entity_access_log(user_id, project_id);
-- Decay job scans by recency.
CREATE INDEX IF NOT EXISTS idx_entity_access_log_last_retrieved
  ON entity_access_log(last_retrieved_at);

-- Track 4 P3b — feedback attribution. last_session_id = the chat session whose
-- context build most recently surfaced this entity (stamped by the router's P0
-- recording); feedback_score accumulates thumbs (±1) attributed to entities the
-- session surfaced within the turn's time window. Additive; both unused until
-- salience_feedback_weight > 0.
ALTER TABLE entity_access_log
  ADD COLUMN IF NOT EXISTS last_session_id UUID,
  ADD COLUMN IF NOT EXISTS feedback_score DOUBLE PRECISION NOT NULL DEFAULT 0;

-- ═══════════════════════════════════════════════════════════════
-- WS-4C Half A — per-project canon auto-capture toggle.
-- Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md
--
-- Whether chat-service, every Nth assistant turn, extracts the newly-named
-- entities the exchange established and lands them in this book's glossary
-- review inbox as `draft` + `ai-suggested` entities (never canon).
--
-- A USER setting, not an env flag (Settings & Config Boundary): capture spends
-- the user's own BYOK tokens, so two users genuinely want different values. The
-- deploy-time env ceiling lives in chat (`CHAT_CANON_CAPTURE_ENABLED`) and only
-- NARROWS this — effective = AND(deploy_allows, project_enables) — it is never
-- itself a per-user knob.
--
-- DEFAULT **false** — capture is OPT-IN, deliberately NOT mirroring
-- tool_calling_enabled's default-true. Capture is AMBIENT spend: it fires on
-- ordinary chatting, on the user's own paid model, for a turn they didn't ask it
-- for. Turning it on by default would charge every existing project for a feature
-- its owner never requested. That is the same consent boundary the Track-D spend
-- gate draws (spend is irreversible ⇒ fail closed); the toggle IS the consent, so
-- it must start un-granted. The FE toggle lives in the project settings modal
-- beside tool_calling_enabled / memory_remember_confirm.
--
-- ONE-TIME NORMALIZATION, self-disarming. An earlier revision of this same
-- (unreleased) branch shipped `ADD COLUMN ... DEFAULT true`, which back-fills every
-- existing row to true. `ADD COLUMN IF NOT EXISTS` never revisits a column, so
-- simply changing the literal above would leave those rows opted IN — silently
-- spending on every project in any database that ran the bad revision. Observed for
-- real on the dev DB (21/21 projects true).
--
-- The column's own `column_default` is the version marker: `true` ⇒ this database
-- ran the bad revision, so normalize the rows and fix the default. Fixing the
-- default disarms the block, so it can NEVER run again — a user who later opts IN
-- is not silently opted back out by a redeploy. Nobody could have legitimately
-- opted in while the marker is set: the toggle UI ships in the same change that
-- removes it.
-- ═══════════════════════════════════════════════════════════════
DO $$
DECLARE _bad_default boolean;
BEGIN
  ALTER TABLE knowledge_projects
    ADD COLUMN IF NOT EXISTS canon_capture_enabled BOOLEAN NOT NULL DEFAULT false;

  SELECT column_default = 'true' INTO _bad_default
    FROM information_schema.columns
   WHERE table_schema = current_schema()
     AND table_name   = 'knowledge_projects'
     AND column_name  = 'canon_capture_enabled';

  IF coalesce(_bad_default, false) THEN
    UPDATE knowledge_projects SET canon_capture_enabled = false
     WHERE canon_capture_enabled;
    ALTER TABLE knowledge_projects
      ALTER COLUMN canon_capture_enabled SET DEFAULT false;
  END IF;
END$$;

-- ═══════════════════════════════════════════════════════════════
-- book_id lookup index — the per-chat-turn KG-state probe.
--
-- GET /internal/books/{book_id}/kg-state (app/routers/internal_kg_state.py) is
-- called ONCE PER CHAT TURN by chat-service and resolves the newest live project
-- for a book. Until now NOTHING indexed knowledge_projects.book_id — the only
-- indexes are on user_id and extraction_status — so every book_id lookup was a
-- seq scan. Tolerable for the existing low-frequency callers (internal_timeline,
-- the extraction handlers); NOT tolerable on the chat hot path.
--
-- Partial + covering:
--   * `book_id IS NOT NULL` — 'code'/'general' projects carry a NULL book_id and
--     can never match this lookup; excluding them keeps the index small.
--   * `NOT is_archived` — mirrors idx_knowledge_projects_user; the probe only
--     ever wants live projects.
--   * `created_at DESC` as the second key serves the ORDER BY directly, so the
--     "newest project for this book" read is an index-only top-1, no sort.
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_knowledge_projects_book_active
  ON knowledge_projects(book_id, created_at DESC)
  WHERE book_id IS NOT NULL AND NOT is_archived;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
