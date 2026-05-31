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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
