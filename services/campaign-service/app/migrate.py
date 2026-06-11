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

-- G1 (wake-up report): launch-time estimate band (from the wizard /estimate),
-- persisted so the completion report can show spent-vs-estimate. NULL = launched
-- without estimating.
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS est_usd_low  NUMERIC(16,8);
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS est_usd_high NUMERIC(16,8);

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

-- S5b-eval — per-campaign translation EVAL-JUDGE model. NULL = use the
-- service-wide default (or no judge). Rides the translation.quality event to
-- learning-service's M7d-2 fidelity judge. eval_fidelity_score on the projection
-- stores the judge's [0,1] verdict per chapter (additive telemetry — best-effort,
-- does NOT gate the eval stage, which still rides translation.quality).
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS eval_judge_model_source TEXT;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS eval_judge_model_ref    UUID;
ALTER TABLE campaign_chapters ADD COLUMN IF NOT EXISTS eval_fidelity_score NUMERIC(4,3);

-- D-FACTORY-INFLIGHT-LOG — append-only per-chapter activity log (the monitor's
-- timestamped recent-activity feed). Sourced ENTIRELY by a trigger on
-- campaign_chapters (below): every stage-status transition the driver/consumer/
-- reconcile/cancel write as an UPDATE becomes one row here — no app instrumentation.
CREATE TABLE IF NOT EXISTS campaign_activity (
  id           BIGSERIAL PRIMARY KEY,
  campaign_id  UUID NOT NULL,
  chapter_id   UUID NOT NULL,
  chapter_sort INT  NOT NULL DEFAULT 0,
  stage        TEXT NOT NULL,   -- knowledge | translation | eval
  status       TEXT NOT NULL,   -- dispatched | done | skipped | failed
  detail       TEXT,            -- last_error, only when status='failed'
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- recent-first keyset pagination per campaign (WHERE campaign_id ORDER BY id DESC).
CREATE INDEX IF NOT EXISTS idx_campactivity_campaign
  ON campaign_activity(campaign_id, id DESC);

-- The trigger: one activity row per changed stage-status. Fires on UPDATE only, so
-- the initial seed INSERT (all stages 'pending') logs nothing — only transitions.
-- IS DISTINCT FROM is NULL-safe; an attempts-only / job_id-only UPDATE writes nothing.
CREATE OR REPLACE FUNCTION campaign_activity_log() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.knowledge_status IS DISTINCT FROM OLD.knowledge_status THEN
    INSERT INTO campaign_activity (campaign_id, chapter_id, chapter_sort, stage, status, detail)
    VALUES (NEW.campaign_id, NEW.chapter_id, NEW.chapter_sort, 'knowledge', NEW.knowledge_status,
            CASE WHEN NEW.knowledge_status = 'failed' THEN NEW.last_error END);
  END IF;
  IF NEW.translation_status IS DISTINCT FROM OLD.translation_status THEN
    INSERT INTO campaign_activity (campaign_id, chapter_id, chapter_sort, stage, status, detail)
    VALUES (NEW.campaign_id, NEW.chapter_id, NEW.chapter_sort, 'translation', NEW.translation_status,
            CASE WHEN NEW.translation_status = 'failed' THEN NEW.last_error END);
  END IF;
  IF NEW.eval_status IS DISTINCT FROM OLD.eval_status THEN
    INSERT INTO campaign_activity (campaign_id, chapter_id, chapter_sort, stage, status, detail)
    VALUES (NEW.campaign_id, NEW.chapter_id, NEW.chapter_sort, 'eval', NEW.eval_status,
            CASE WHEN NEW.eval_status = 'failed' THEN NEW.last_error END);
  END IF;
  RETURN NULL;  -- AFTER trigger: return value ignored.
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_campaign_activity ON campaign_chapters;
CREATE TRIGGER trg_campaign_activity
  AFTER UPDATE ON campaign_chapters
  FOR EACH ROW EXECUTE FUNCTION campaign_activity_log();
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
