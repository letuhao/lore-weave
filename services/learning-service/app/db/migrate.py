"""learning-service schema — idempotent DDL string run at startup.

House style matches chat-service / knowledge-service: a single idempotent
`DDL` string of `CREATE TABLE IF NOT EXISTS` + guarded `ALTER`s, applied on
every boot via `run_migrations(pool)`. No Alembic.

Tables this cycle (Phase B — Axis-1 correction capture):
  - corrections          — the append-only correction log (redact-by-default)
  - dead_letter_events   — consumer DLQ (cloned from knowledge-service)

Phase B2 (config telemetry — added this cycle, DESIGN §3 of
docs/specs/2026-05-31-phase-b2-config-telemetry-design.md):
  - config_registry          — content-addressed effective config (N runs -> 1 row)
  - extraction_runs          — per-chapter run record (transactional emit from worker-ai)
  - config_adjustment_events — append-only per-novel tuning log (best-effort)
`corrections.source_extraction_run_id` is a LOGICAL join to `extraction_runs`
(no enforced cross-table FK — preserves Phase-B's decoupled best-effort emit).
"""

from __future__ import annotations

import asyncpg

DDL = """
-- ── corrections ──────────────────────────────────────────────────────
-- One row per USER correction of an extraction output. Pipeline writes are
-- NOT persisted here (they are the original output, not a correction).
--
-- PRIVACY (R2, redact-by-default): we store STRUCTURAL fields raw + a
-- content HASH; raw novel text (`*_content`) is reserved/NULL until a tenant
-- opts into raw retention for Phase-E organic gold. Strict per-owner
-- isolation: every read filters on user_id (the corpus owner).
CREATE TABLE IF NOT EXISTS corrections (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- tenancy: user_id is the CORPUS OWNER (today owner == actor; see design §3)
  user_id                   UUID NOT NULL,
  project_id                UUID,
  book_id                   UUID,
  -- what was corrected
  target_type               TEXT NOT NULL,
  target_id                 TEXT NOT NULL,
  op                        TEXT NOT NULL,
  -- privacy split (no raw novel text persisted this cycle)
  before_structural         JSONB,
  after_structural          JSONB,
  before_content_hash       TEXT,
  after_content_hash        TEXT,
  before_content            JSONB,      -- RESERVED, NULL in Phase B (Phase-E opt-in)
  after_content             JSONB,      -- RESERVED, NULL in Phase B (Phase-E opt-in)
  diff_class                TEXT,
  -- provenance back to the run that produced the original output
  source_extraction_run_id  UUID,       -- nullable until B2 extraction_runs exists
  source_chapter            TEXT,
  source_span               JSONB,
  -- actor
  actor_type                TEXT NOT NULL,
  actor_id                  UUID,
  -- capture provenance / idempotency
  origin_service            TEXT NOT NULL,
  origin_event_id           TEXT NOT NULL,   -- = producer outbox row id (NOT aggregate_id / message_id)
  origin_event_type         TEXT NOT NULL,
  emitted_at                TIMESTAMPTZ,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT corrections_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_corrections_user_project
  ON corrections(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_corrections_target
  ON corrections(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_corrections_diff_class
  ON corrections(diff_class) WHERE diff_class IS NOT NULL;

-- ── dead_letter_events ───────────────────────────────────────────────
-- Consumer DLQ — a handler exception after MAX_RETRIES lands here.
CREATE TABLE IF NOT EXISTS dead_letter_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stream        TEXT NOT NULL,
  message_id    TEXT NOT NULL,
  event_type    TEXT,
  aggregate_id  TEXT,
  payload       JSONB,
  error         TEXT,
  retry_count   INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT dead_letter_uniq UNIQUE (stream, message_id)
);

-- ── config_registry (Phase B2) ───────────────────────────────────────
-- Content-addressed effective extraction config. N runs -> 1 row, deduped
-- by config_hash. Structural only — custom prompts enter as content-hash
-- (in resolved_config + prompt_versions), NEVER raw text (DESIGN Q5).
CREATE TABLE IF NOT EXISTS config_registry (
  config_hash           TEXT PRIMARY KEY,        -- sha256 of canonical resolved_config (embedding_model excluded)
  resolved_config       JSONB NOT NULL,
  base_default_version  TEXT NOT NULL,           -- content-hash of the global-default values
  prompt_versions       JSONB NOT NULL,          -- {op: "v1-op-8hex" | "custom-8hex"}
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── extraction_runs (Phase B2) ───────────────────────────────────────
-- One row per CHAPTER processed. Emitted from worker-ai at chapter
-- completion (transactional with cursor-advance on success/skip;
-- best-effort on the failure path). Strict per-owner isolation: reads
-- filter on user_id (the corpus owner).
CREATE TABLE IF NOT EXISTS extraction_runs (
  run_id            UUID PRIMARY KEY,            -- minted by worker-ai for dedup
  user_id           UUID NOT NULL,
  project_id        UUID,
  book_id           UUID,
  job_id            UUID,
  scope             TEXT,                          -- 'chapter' today; reserves 'chat'/'glossary_sync'
  chapter_ref       TEXT,
  config_hash       TEXT NOT NULL REFERENCES config_registry(config_hash),
  model_ref         TEXT,                          -- extractor model UUID (denorm for fast filter)
  metrics           JSONB NOT NULL DEFAULT '{}'::jsonb,
  outcome           TEXT,                          -- 'succeeded'|'skipped'|'failed' at emit; refined later (E2)
  outcome_source    TEXT,                          -- 'pipeline' at emit
  origin_service    TEXT NOT NULL,
  origin_event_id   TEXT NOT NULL,                 -- producer outbox row id (dedup key)
  emitted_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT extraction_runs_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_user_project
  ON extraction_runs(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_config
  ON extraction_runs(config_hash);
CREATE INDEX IF NOT EXISTS idx_runs_chapter
  ON extraction_runs(user_id, project_id, chapter_ref);

-- ── config_adjustment_events (Phase B2) ──────────────────────────────
-- Append-only per-novel tuning log. Async / lossy-OK (best-effort emit).
-- Structural diffs free; raw prompt text enters as content-hash only
-- (before/after_content reserved/NULL until tenant opt-in — mirrors
-- corrections' redact-by-default, DESIGN Q5).
CREATE TABLE IF NOT EXISTS config_adjustment_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL,
  project_id            UUID,
  actor_type            TEXT NOT NULL,
  actor_id              UUID,
  base_default_version  TEXT,
  target                TEXT NOT NULL,             -- e.g. 'precision_filter.categories' | 'prompts.entity.system'
  op                    TEXT NOT NULL,             -- 'set'
  before_structural     JSONB,
  after_structural      JSONB,
  before_content_hash   TEXT,                       -- raw-prompt targets: sha256 of prior text
  after_content_hash    TEXT,
  before_content        JSONB,                      -- RESERVED/NULL until tenant opts into raw retention
  after_content         JSONB,                      -- RESERVED/NULL
  reason                TEXT,
  origin_service        TEXT NOT NULL,
  origin_event_id       TEXT NOT NULL,
  emitted_at            TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT config_adj_origin_uniq UNIQUE (origin_service, origin_event_id)
);
CREATE INDEX IF NOT EXISTS idx_adj_user_project
  ON config_adjustment_events(user_id, project_id, created_at DESC);

-- ── Phase E2 — genre on extraction_runs (2026-06-01) ──────────────────
-- Copied from knowledge_projects.genre at run-emit time so genre-segment
-- mining queries operate within loreweave_learning (no cross-DB join).
ALTER TABLE extraction_runs
  ADD COLUMN IF NOT EXISTS genre TEXT;
CREATE INDEX IF NOT EXISTS idx_runs_genre
  ON extraction_runs(genre) WHERE genre IS NOT NULL;

-- ══════════════════════════════════════════════════════════════════════
-- Track "Production Eval + Feedback Flywheel" — Q1: the quality plane.
-- (docs/plans/2026-06-01-production-eval-feedback-flywheel-track.md §3)
--
-- The three-object eval model (OpenAI Eval/Run/Output-Item) + a universal
-- append-only Score entity (Langfuse). Item-level by design so paired/
-- clustered standard errors stay recomputable (Anthropic: never store only
-- the aggregate). Structural + content-hash only (redact-by-default). Metric
-- names mirror the OTel `gen_ai.evaluation.*` semantic conventions so the
-- telemetry stays portable.
-- ══════════════════════════════════════════════════════════════════════

-- ── score_config (Q1) ────────────────────────────────────────────────
-- Registered, versioned metric definitions (Langfuse ScoreConfig). Validates
-- quality_scores at WRITE time (datatype / range / categories) so a malformed
-- judge output is rejected, not silently stored.
CREATE TABLE IF NOT EXISTS score_config (
  score_config_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name             TEXT NOT NULL UNIQUE,         -- e.g. 'disjoint_median_f1', 'macro_f1'
  data_type        TEXT NOT NULL,                -- 'numeric' | 'categorical' | 'boolean'
  min_value        DOUBLE PRECISION,             -- numeric lower bound (inclusive)
  max_value        DOUBLE PRECISION,             -- numeric upper bound (inclusive)
  categories       JSONB,                        -- allowed labels for categorical
  description      TEXT,
  is_archived      BOOLEAN NOT NULL DEFAULT false,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── eval_runs (Q1) ───────────────────────────────────────────────────
-- One row per scored dump (OpenAI 'Run' / Vertex summary_metrics). Logical
-- links to config_registry(config_hash) + extraction_runs (no enforced FK —
-- baselines pre-date a registry row; preserves decoupled best-effort emit).
-- `disjoint_median_f1` is the metric-of-record; `judges` carries the panel
-- composition inline (the dedicated judge_panel table is deferred until a 2nd
-- panel exists — track critique). `idempotency_key` makes re-scoring / baseline
-- materialization safe to re-run.
CREATE TABLE IF NOT EXISTS eval_runs (
  eval_run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  UUID NOT NULL,
  project_id               UUID,
  book_id                  UUID,
  source_extraction_run_id UUID,                 -- logical link to extraction_runs (best-effort)
  config_hash              TEXT,                 -- logical link to config_registry (nullable)
  judge_panel_id           UUID,                 -- RESERVED (judge_panel table deferred)
  dataset_version          TEXT,                 -- golden-set fixture / dump label
  source                   TEXT NOT NULL DEFAULT 'offline',  -- offline|online|shadow|baseline
  judges                   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{label,uuid,role,macro_p,macro_r,macro_f1}]
  disjoint_median_f1       DOUBLE PRECISION,
  full_panel_median_f1     DOUBLE PRECISION,
  fleiss_kappa             DOUBLE PRECISION,
  bootstrap_ci             JSONB,                -- {low, high, n_common_chapters}
  bias_metrics             JSONB,
  n_chapters               INT,
  n_disjoint_judges        INT,
  idempotency_key          TEXT,                 -- caller-supplied dedup key (baseline / run+panel)
  origin_service           TEXT,
  origin_event_id          TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_runs_idempotency
  ON eval_runs(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_eval_runs_user
  ON eval_runs(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_runs_config
  ON eval_runs(config_hash) WHERE config_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_eval_runs_source_run
  ON eval_runs(source_extraction_run_id) WHERE source_extraction_run_id IS NOT NULL;

-- ── eval_results (Q1) ────────────────────────────────────────────────
-- Per-slice result (OpenAI 'Output Item' / Vertex metrics_table). Q1 writes
-- one row per (judge, category='all'); `chapter_ref` is reserved for the Q6b
-- per-chapter rows that make clustered SE recomputable. Cascades with the run.
CREATE TABLE IF NOT EXISTS eval_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id     UUID NOT NULL REFERENCES eval_runs(eval_run_id) ON DELETE CASCADE,
  category        TEXT NOT NULL,                 -- entity|relation|event|all
  chapter_ref     TEXT,                          -- cluster unit (reserved, Q6b)
  judge_label     TEXT,                          -- which judge produced this slice
  judge_uuid      TEXT,
  precision       DOUBLE PRECISION,
  recall          DOUBLE PRECISION,
  f1              DOUBLE PRECISION,
  input_hash      TEXT,
  gold_projection JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eval_results_run
  ON eval_results(eval_run_id, category);

-- ── quality_scores (Q1) ──────────────────────────────────────────────
-- Universal append-only Score/Feedback entity (Langfuse/LangSmith/Phoenix).
-- 3-judge ensemble + human corrections (Q2) + chat ratings (Q3) coexist
-- without mutating the scored output. DUAL dedup (track critique fix #5):
--   * consumed producer events (Q3 chat feedback): (origin_service, origin_event_id)
--   * self-produced judge verdicts (Q1/Q4, no outbox id):
--       (source_eval_run_id, target_kind, target_id, metric_name, judge_model)
CREATE TABLE IF NOT EXISTS quality_scores (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  target_kind        TEXT NOT NULL,             -- entity|relation|event|extraction_run|eval_run|chat_message
  target_id          TEXT NOT NULL,
  book_id            UUID,
  user_id            UUID NOT NULL,
  metric_name        TEXT NOT NULL,             -- FK-by-name to score_config.name
  value_num          DOUBLE PRECISION,
  value_label        TEXT,
  data_type          TEXT NOT NULL,             -- numeric|categorical|boolean (validated vs score_config)
  source             TEXT NOT NULL,             -- human|llm_judge|heuristic
  judge_model        TEXT,                      -- the judge that produced it (self-produced rows)
  comment            TEXT,
  source_eval_run_id UUID,                      -- the eval_run this score belongs to (self-produced)
  origin_service     TEXT,                      -- consumed-event provenance (Q3)
  origin_event_id    TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quality_scores_origin
  ON quality_scores(origin_service, origin_event_id)
  WHERE origin_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_quality_scores_self
  ON quality_scores(source_eval_run_id, target_kind, target_id, metric_name, judge_model)
  WHERE source_eval_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quality_scores_target
  ON quality_scores(target_kind, target_id);
CREATE INDEX IF NOT EXISTS idx_quality_scores_user_metric
  ON quality_scores(user_id, metric_name, created_at DESC);

-- ── Q3.5/Q4 — panel safety on eval_runs (anti-self-reinforcement, visible) ──
-- Records whether a scored run's metric-of-record panel was trustworthy
-- (>= 2 disjoint judges, no generator self-grading). Structural-only online
-- runs (no judge) set panel_safe = TRUE with a 'structural-only' reason.
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS panel_safe BOOLEAN;
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS panel_safety_reason TEXT;

-- ── online_eval_rule (Q4) ─────────────────────────────────────────────
-- The (filter + sampling_rate) automation for the eval-runner consumer.
-- sampling_rate is the local-LLM cost governor (the future LLM-judge path,
-- Q4b); the structural-completeness default needs no LLM so it can sample
-- higher. A NULL user_id = a global default rule.
CREATE TABLE IF NOT EXISTS online_eval_rule (
  rule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID,                          -- NULL = global default
  name            TEXT NOT NULL,
  filter_jsonb    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- event predicate (genre, config_hash, ...)
  sampling_rate   DOUBLE PRECISION NOT NULL DEFAULT 0.1 CHECK (sampling_rate >= 0 AND sampling_rate <= 1),
  judge_panel_id  UUID,                          -- NULL = structural-only (no LLM judge)
  metric_set      JSONB NOT NULL DEFAULT '["online_structural_completeness"]'::jsonb,
  enabled         BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_online_eval_rule_name
  ON online_eval_rule(name);
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
