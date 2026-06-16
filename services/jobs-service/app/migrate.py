"""Idempotent Postgres DDL for loreweave_jobs (Unified Job Control Plane P2).

House style mirrors campaign/knowledge-service: a single DDL string with CREATE
TABLE IF NOT EXISTS, applied on every startup via `run_migrations(pool)`. No
Alembic/goose — bare SQL via asyncpg. `run_down_migrations` drops in reverse for
a clean up→down→up round-trip.

`job_projection` is a MIRROR of every service's domain job rows (the SSOT lives
in each owning service). PK `(service, job_id)`. It is fed by the projection
consumer off `loreweave:events:jobs` (outbox-relayed, exactly-once) and, as the
H1 backstop, by the reconcile sweep. There are NO cross-DB FKs: `owner_user_id`
references loreweave_auth.users, `job_id`/`parent_job_id` live in the owning
service's DB — validated in application code, not by a constraint.

`dead_letter_events` is the consumer's retry→DLQ sink: an event that fails to
project `max_retries` times is parked here (and the reconcile sweep heals the
job) rather than poison-looping the PEL.
"""

import asyncpg

DDL = """
-- ═══════════════════════════════════════════════════════════════
-- job_projection — the unified cross-service job mirror (req 1 + 2).
-- One row per domain job. Fed by the projection consumer (primary) +
-- reconcile sweep (backstop). control_caps are NOT stored — they are
-- state-aware and derived at read time from (status, kind).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS job_projection (
  service        TEXT NOT NULL,                 -- owning service (control-routing target)
  job_id         UUID NOT NULL,                 -- domain job id (unique within service)
  owner_user_id  UUID NOT NULL,                 -- req 1 — whose GUI this appears in (not the BYOK biller)
  kind           TEXT NOT NULL,                 -- "extraction" | "translation" | "composition.generate" | …
  status         TEXT NOT NULL,                 -- canonical JobStatus value
  parent_job_id  UUID,                          -- H3 — children group under a parent (e.g. a campaign)
  detail_status  TEXT,                          -- M2 — service-native passthrough ("summarizing", stage labels)
  progress       JSONB,                         -- {"done":int,"total":int} or NULL (single-call/streaming)
  title          TEXT,                          -- human label
  error          JSONB,                         -- {"code","message"} or NULL
  job_created_at TIMESTAMPTZ,                   -- earliest event occurred_at seen for this job
  job_updated_at TIMESTAMPTZ NOT NULL,          -- latest applied event occurred_at (monotonic guard)
  projected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when the projection last wrote this row
  -- P4 usage/observability (all nullable; COALESCE-merged on each applied event so a
  -- later event without them never wipes the accumulated value). model = resolved NAME
  -- (not BYOK ref-UUID); cost_usd reliable; tokens best-effort; params = whitelisted
  -- dynamic key-value (model now, effort later — no schema change), never raw prompt.
  model          TEXT,
  cost_usd       NUMERIC,
  tokens_in      BIGINT,
  tokens_out     BIGINT,
  params         JSONB,
  PRIMARY KEY (service, job_id)
);

-- P4 additive columns for existing deployments (job_projection is a rebuildable MIRROR;
-- ADD COLUMN IF NOT EXISTS is idempotent + a no-op on a fresh CREATE above).
ALTER TABLE job_projection ADD COLUMN IF NOT EXISTS model     TEXT;
ALTER TABLE job_projection ADD COLUMN IF NOT EXISTS cost_usd  NUMERIC;
ALTER TABLE job_projection ADD COLUMN IF NOT EXISTS tokens_in  BIGINT;
ALTER TABLE job_projection ADD COLUMN IF NOT EXISTS tokens_out BIGINT;
ALTER TABLE job_projection ADD COLUMN IF NOT EXISTS params    JSONB;

-- List query: a user's jobs, most-recently-updated first.
CREATE INDEX IF NOT EXISTS idx_job_projection_owner_updated
  ON job_projection (owner_user_id, job_updated_at DESC);
-- History list (P4): offset-paginated, ORDER BY created_at DESC (stable; SSE doesn't
-- reorder it). Separate from the updated_at index the live Active list keysets on.
CREATE INDEX IF NOT EXISTS idx_job_projection_owner_created
  ON job_projection (owner_user_id, job_created_at DESC);
-- Filtered list (status facet).
CREATE INDEX IF NOT EXISTS idx_job_projection_owner_status
  ON job_projection (owner_user_id, status);
-- Children-under-parent grouping (H3).
CREATE INDEX IF NOT EXISTS idx_job_projection_parent
  ON job_projection (parent_job_id) WHERE parent_job_id IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- dead_letter_events — the consumer's retry→DLQ sink. An event that
-- fails to project max_retries times lands here; the reconcile sweep
-- is the durability backstop that heals the affected job.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dead_letter_events (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  stream      TEXT NOT NULL,
  msg_id      TEXT NOT NULL,
  payload     JSONB,
  error       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

DOWN_DDL = """
DROP TABLE IF EXISTS dead_letter_events;
DROP TABLE IF EXISTS job_projection;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)


async def run_down_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DOWN_DDL)
