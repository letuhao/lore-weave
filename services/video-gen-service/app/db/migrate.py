"""video-gen-service schema migration (idempotent, single-DDL house style).

LLM re-arch Phase 3 M5: one table — ``video_gen_jobs`` — backing the decoupled
job-row + terminal-event path (mirrors learning-service's ``llm_judges`` and
composition's ``generation_job``). Applied on every worker/API startup when the
decouple flag is on; no migration tool, like knowledge-/composition-service.
``uuidv7()`` is a PG18 built-in.

The gateway job id (``provider_job_id``) is the consumer match key: the M5
terminal-event consumer reads the shared ``loreweave:events:llm_job_terminal``
stream and looks up OUR row by it (a miss → some other service's job → skip).
It is UNIQUE so a redelivered terminal can't match two rows. No DB FKs —
user_id (auth) and provider_job_id (gateway) are cross-DB ids, validated in app
code per the platform convention.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger("video-gen.migrate")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS video_gen_jobs (
  id               UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,
  -- the gateway's job id (operation=video_gen). NULL only in the brief
  -- submit→persist window if a row were ever inserted before submit; M5
  -- submits first, so it is set at INSERT. UNIQUE = the consumer match key.
  provider_job_id  UUID UNIQUE,
  status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','running','completed','failed','cancelled')),
  -- the original request (prompt, model_source, model_ref, size, duration,
  -- style, init_image?) — kept for replay/debug + billing prompt_len.
  request_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- the local MinIO URL, null until the consumer downloads + stores.
  video_url        TEXT,
  size_bytes       BIGINT,
  content_type     TEXT,
  -- {code, message} on failure (mirrors the gateway JobError shape).
  error_json       JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- the user's job list (poll/history), newest first.
CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_user ON video_gen_jobs(user_id, created_at DESC);
-- the sweeper scans only non-terminal rows by updated_at.
CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_active
  ON video_gen_jobs(updated_at) WHERE status IN ('pending','running');
-- Unified Job Control Plane reconcile source: GET /internal/video_gen/jobs?since= filters
-- by updated_at over ALL statuses (the partial idx above only covers active) — full index.
CREATE INDEX IF NOT EXISTS idx_video_gen_jobs_updated_at ON video_gen_jobs(updated_at);

-- ── outbox_events: standard (matches knowledge/composition); relayed by worker-infra
-- to loreweave:events:<aggregate_type>. Unified Job Control Plane P1 — job-lifecycle
-- JobEvents are written here with aggregate_type='jobs' (→ loreweave:events:jobs) in
-- the SAME tx as the video_gen_jobs status change (emit_job_event). uuidv7() = PG18.
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'video_gen',
  aggregate_id   UUID NOT NULL,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(created_at) WHERE published_at IS NULL;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the idempotent schema. Safe on every start."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
    logger.info("video-gen migrate: schema applied (video_gen_jobs)")
