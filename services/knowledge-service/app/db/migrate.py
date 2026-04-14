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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
