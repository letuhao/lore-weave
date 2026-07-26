package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpExtractionConcurrency — chain step 0032 (extraction pipeline FND/M1). The
// two-ledger + constraint-backed-dedup foundation every later extraction
// milestone (PROV, MERGE, CACHE) writes through.
//
// Why this exists (architecture rev 2 §8.1–8.2): the extraction writeback had
// NO database-level dedup — concurrent jobs on the same chapter both ran the
// app-layer findEntityByNameOrAlias resolver, both missed, and both CREATED the
// same entity (a TOCTOU duplicate). And a failed writeback left no record, so a
// retry could not tell "never landed" from "already landed" → either re-spent the
// LLM or silently dropped entities. This migration closes both:
//
//   - normalized_name (GENERATED/STORED off the trigger-maintained cached_name)
//     + a partial UNIQUE index = constraint-backed dedup (INV-C2). The per-book
//     advisory lock the handler takes makes the resolver race-free; this index is
//     the backstop AND the ON CONFLICT target. Partial so it ignores soft-deleted
//     rows and the transient empty-name state (the entity row is inserted before
//     its 'name' EAV value lands and fires the cached_name trigger).
//   - uq_evidence_dedup = idempotent evidence (INV-C5): the same quote for the
//     same (attr_value, type) cannot duplicate across re-extraction/replay/redelivery.
//   - extraction_writeback_log = the WRITEBACK ledger (INV-C3), DISTINCT from the
//     EXECUTE ledger (extraction_raw_outputs, translation-service/M6): a unique
//     writeback_key makes a duplicate apply (retry = replay = concurrent fresh) a
//     no-op that returns the original counts. Carries owner_user_id + book_id
//     (INV-6 tenancy) and content_hash (INV-C4 source-drift precondition).
//
// All statements idempotent (IF NOT EXISTS), routed through execGuarded (the
// migration advisory lock) like every chain step. normalize(...,NFC) + the
// regexp/lower/btrim are all IMMUTABLE, so the generated-column expression is
// valid; it mirrors the Go normalizeEntity() used by the resolver so DB-side
// dedup and app-side resolution agree.
//
// NOTE on existing data: ADD COLUMN ... GENERATED rewrites the table to compute
// the column for present rows, and the UNIQUE index build FAILS LOUDLY if a book
// already holds two live entities of the same kind+normalized name (a pre-existing
// duplicate from the bug this fixes). That is intentional — we do not silently
// auto-merge user rows in a migration; a colliding DB must be deduped consciously
// first. (Verified 0 such collisions on the dev DB at authoring time.)
func UpExtractionConcurrency(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "extraction-concurrency", `
		ALTER TABLE glossary_entities
		  ADD COLUMN IF NOT EXISTS normalized_name TEXT
		  GENERATED ALWAYS AS (
		    lower(btrim(regexp_replace(normalize(coalesce(cached_name, ''), NFC), '\s+', ' ', 'g')))
		  ) STORED;

		CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_dedup
		  ON glossary_entities (book_id, kind_id, normalized_name)
		  WHERE deleted_at IS NULL AND normalized_name <> '';

		CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_dedup
		  ON evidences (attr_value_id, evidence_type, md5(original_text));

		CREATE TABLE IF NOT EXISTS extraction_writeback_log (
		  id               UUID PRIMARY KEY DEFAULT uuidv7(),
		  owner_user_id    UUID,
		  book_id          UUID NOT NULL,
		  chapter_id       UUID NOT NULL,
		  writeback_key    TEXT NOT NULL UNIQUE,
		  content_hash     TEXT NOT NULL DEFAULT '',
		  status           TEXT NOT NULL,
		  entities_created INT  NOT NULL DEFAULT 0,
		  entities_updated INT  NOT NULL DEFAULT 0,
		  entities_skipped INT  NOT NULL DEFAULT 0,
		  committed_at     TIMESTAMPTZ,
		  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
		);
		CREATE INDEX IF NOT EXISTS idx_ewl_chapter ON extraction_writeback_log(book_id, chapter_id);`)
}
