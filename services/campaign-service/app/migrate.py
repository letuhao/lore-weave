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
  last_error         TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (campaign_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_campchap_campaign
  ON campaign_chapters(campaign_id);
-- Projection lookup by chapter (the consumer joins inbound events here).
CREATE INDEX IF NOT EXISTS idx_campchap_chapter
  ON campaign_chapters(chapter_id);
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
