"""campaign-service schema — Auto-Draft Factory S1.

Idempotent DDL (CREATE TABLE IF NOT EXISTS + additive ALTERs), mirroring the
translation-service/migrate.py pattern. `campaign_chapters` is the unified
per-chapter cross-pipeline projection (gap G7): the single source of truth for
"what stage is done for which chapter" (decision J).
"""

import asyncpg

DDL = """
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id      UUID NOT NULL,
  book_id            UUID NOT NULL,
  name               TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'created',
  gating_mode        TEXT NOT NULL DEFAULT 'phase_barrier',
  stages             TEXT[] NOT NULL DEFAULT '{knowledge,translation,eval}',
  target_language    TEXT,
  knowledge_model_source   TEXT,
  knowledge_model_ref      UUID,
  translation_model_source TEXT,
  translation_model_ref    UUID,
  knowledge_project_id     UUID,
  chapter_from       INT,
  chapter_to         INT,
  total_chapters     INT NOT NULL DEFAULT 0,
  error_message      TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_campaigns_owner
  ON campaigns(owner_user_id, created_at DESC);
-- Driver-claim index: the reconcile loop only scans non-terminal campaigns.
CREATE INDEX IF NOT EXISTS idx_campaigns_active
  ON campaigns(status) WHERE status IN ('running', 'cancelling');

-- S3c — HA claim-based dispatch (D-CAMPAIGN-DRIVER-SINGLETON). A driver leases
-- a campaign before processing; a lease in the future means another (live)
-- driver owns it. Expired/NULL → claimable (FOR UPDATE SKIP LOCKED). A crashed
-- driver's lease simply expires → another replica picks the campaign up.
-- `driver_leased_by` = the owning driver's instance id, so a driver RENEWS its
-- own leases each tick (re-claimable when leased_by = me) while peers skip a
-- live lease — without it a driver couldn't re-process a campaign it just leased
-- until the lease expired (dispatch cadence would collapse to the lease period).
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS driver_leased_until TIMESTAMPTZ;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS driver_leased_by TEXT;
-- Event→campaign correlation: the projection consumer maps an inbound event
-- (carrying book_id) to active campaigns on that book.
CREATE INDEX IF NOT EXISTS idx_campaigns_book_active
  ON campaigns(book_id, owner_user_id) WHERE status IN ('running', 'cancelling');

CREATE TABLE IF NOT EXISTS campaign_chapters (
  campaign_id        UUID NOT NULL,
  chapter_id         UUID NOT NULL,
  chapter_sort       INT  NOT NULL DEFAULT 0,
  ingest_status      TEXT NOT NULL DEFAULT 'done',
  knowledge_status   TEXT NOT NULL DEFAULT 'pending',
  translation_status TEXT NOT NULL DEFAULT 'pending',
  eval_status        TEXT NOT NULL DEFAULT 'pending',
  knowledge_attempts   INT NOT NULL DEFAULT 0,
  translation_attempts INT NOT NULL DEFAULT 0,
  -- S3c-2 cancel-propagation: the downstream job that owns this chapter's
  -- in-flight stage, so a campaign cancel can target it. Set when the stage is
  -- dispatched; NULL until then.
  knowledge_job_id     UUID,
  translation_job_id   UUID,
  last_error         TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (campaign_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_campchap_campaign
  ON campaign_chapters(campaign_id);
-- Projection lookup by chapter (the consumer joins inbound events here).
CREATE INDEX IF NOT EXISTS idx_campchap_chapter
  ON campaign_chapters(chapter_id);

-- S3c-2 cancel-propagation (additive; existing tables get these via ALTER).
ALTER TABLE campaign_chapters ADD COLUMN IF NOT EXISTS knowledge_job_id UUID;
ALTER TABLE campaign_chapters ADD COLUMN IF NOT EXISTS translation_job_id UUID;

-- S4d — per-campaign budget cap. budget_usd NULL = uncapped; spent_usd is summed
-- from the loreweave:events:campaign_usage stream by the SpendConsumer and the
-- campaign auto-pauses when spent_usd >= budget_usd (reactive; overshoot accepted).
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS budget_usd NUMERIC(16,8);
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS spent_usd  NUMERIC(16,8) NOT NULL DEFAULT 0;

-- S4d dedup ledger: usage delivery is at-least-once, so this PK makes spend
-- accumulation exactly-once (the sum-across-a-boundary bug class). request_id is
-- the provider-registry job_id carried on the usage event.
CREATE TABLE IF NOT EXISTS campaign_usage_seen (
  request_id  UUID PRIMARY KEY,
  campaign_id UUID NOT NULL,
  cost_usd    NUMERIC(16,8),
  seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- S5b — per-campaign VERIFIER model (V3 translation). NULL = fall back to the
-- translator model (matches v3/orchestrator.py _verifier_model). Threaded through
-- the translation dispatch onto the job. (Embedding/reranker are NOT stored here —
-- they are applied to the chosen knowledge project at create; the project is SSOT.)
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS verifier_model_source TEXT;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS verifier_model_ref    UUID;
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
