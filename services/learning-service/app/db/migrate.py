"""learning-service schema — idempotent DDL string run at startup.

House style matches chat-service / knowledge-service: a single idempotent
`DDL` string of `CREATE TABLE IF NOT EXISTS` + guarded `ALTER`s, applied on
every boot via `run_migrations(pool)`. No Alembic.

Tables this cycle (Phase B — Axis-1 correction capture):
  - corrections          — the append-only correction log (redact-by-default)
  - dead_letter_events   — consumer DLQ (cloned from knowledge-service)

Reserved for Phase B2 (config telemetry — NOT created this cycle, documented
in docs/specs/2026-05-31-phase-b-correction-capture.md §3):
  - config_registry, config_adjustment_events, extraction_runs
`corrections.source_extraction_run_id` is the forward FK to `extraction_runs`.
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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
