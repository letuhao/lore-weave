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
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
