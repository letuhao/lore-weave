package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityResearchJobsSQL — D-BATCH-RESEARCH-JOB M1: the async batch entity-research job.
//
// A job researches up to `max_entities` entities of one book kind on the web (one paid
// BYOK search per entity, reusing the deep-research primitives), attaching sourced
// `reference` evidence. The job lives in glossary-service (it owns the entities/evidence/
// the BYOK web-search) rather than proxying to knowledge like wiki does.
//
// Tenancy (CLAUDE.md › User Boundaries): per-book + owner; scope keys book_id +
// owner_user_id. kind_id is a book_kinds.book_kind_id (the post-G4 entity kind ref).
//
// Cost: provider-registry's web-search returns NO per-call cost (BYOK — the user's
// provider bills them), so the cap is by ENTITY COUNT (each entity = 1 search), and
// est_cost_usd is an INDICATIVE display estimate (items_total × a flat per-search const).
// No precise cost is metered because none is available — no silent seam pretending one is.
//
// One LIVE job per (book, kind) via a partial unique index so two runs can't double-bill
// the same entities; a finished/cancelled job releases the slot.
//
// Idempotent (CREATE … IF NOT EXISTS). Ledgered 0038.
const entityResearchJobsSQL = `
CREATE TABLE IF NOT EXISTS entity_research_jobs (
  job_id           UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id          UUID NOT NULL,
  owner_user_id    UUID NOT NULL,
  kind_id          UUID NOT NULL,               -- book_kinds.book_kind_id
  query_template   TEXT NOT NULL,               -- "{name}" substituted per entity
  max_results      INT  NOT NULL DEFAULT 5,      -- sources attached per entity (1-10)
  max_entities     INT  NOT NULL,               -- scope + cost cap (each = 1 paid search)
  est_cost_usd     NUMERIC(10,4) NOT NULL DEFAULT 0,  -- INDICATIVE (items_total × flat)
  status           TEXT NOT NULL DEFAULT 'pending',   -- pending|running|paused_user|complete|failed|cancelled
  items_total      INT  NOT NULL DEFAULT 0,      -- planned scope = min(max_entities, live entities of kind)
  items_processed  INT  NOT NULL DEFAULT 0,      -- entities visited (researched OR skipped-already-done)
  searches_run     INT  NOT NULL DEFAULT 0,      -- actual paid searches issued
  sources_attached INT  NOT NULL DEFAULT 0,      -- reference evidence rows created
  cursor_entity_id UUID,                         -- resume point (last visited entity)
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ
);

-- One live job per (book, kind): a second create while one is pending/running/paused trips
-- this and the handler maps the unique-violation to 409.
CREATE UNIQUE INDEX IF NOT EXISTS entity_research_jobs_one_live
  ON entity_research_jobs (book_id, kind_id)
  WHERE status IN ('pending','running','paused_user');

CREATE INDEX IF NOT EXISTS entity_research_jobs_book
  ON entity_research_jobs (book_id, created_at DESC);
`

// UpEntityResearchJobs creates the entity_research_jobs table (M1). Idempotent; chain 0038.
func UpEntityResearchJobs(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-research-jobs", entityResearchJobsSQL)
}
