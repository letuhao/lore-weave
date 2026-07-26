package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpCrossKindDedupIndex — chain step 0042 (#38/#39 cross-kind entity dedup).
//
// The extraction writeback now resolves a name across ALL kinds before creating an
// entity (findEntityCrossKind), so the same character tagged under several kinds —
// or re-extracted under a changed kind set — reuses one entity instead of spawning
// a per-kind duplicate. That lookup filters by (book_id, normalized_name) with NO
// kind, but the only matching index is uq_entity_dedup (book_id, kind_id,
// normalized_name) — kind_id sits between the two columns we filter, so the planner
// can only range-scan ALL of a book's entries per lookup. On a large book (15k+
// entities) doing hundreds of new-name lookups that is O(book × new-names) — the
// exact "extraction is slow" surface (#38).
//
// This adds a NON-unique partial index on (book_id, normalized_name) so the
// cross-kind lookup is a direct index seek. NON-unique deliberately: it is a lookup
// accelerator, not a constraint — pre-existing cross-kind duplicates (the very rows
// #40 / the dedup remediation clean up) must not make this index build fail, and the
// per-kind uq_entity_dedup remains the write-time uniqueness backstop. Partial to
// match the lookup's predicate (live, named rows only) and stay small.
//
// Idempotent (IF NOT EXISTS), routed through execGuarded like every chain step.
func UpCrossKindDedupIndex(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "cross-kind-dedup-index", `
		CREATE INDEX IF NOT EXISTS idx_entity_book_normname
		  ON glossary_entities (book_id, normalized_name)
		  WHERE deleted_at IS NULL AND normalized_name <> '';`)
}
