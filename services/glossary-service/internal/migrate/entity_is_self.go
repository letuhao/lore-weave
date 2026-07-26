package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpEntityIsSelf — chain step 0053 (WS-1.6 / spec 05 §Q5). The user's OWN identity entity in
// their diary glossary, marked `is_self` so capture and the co-occurrence/salience detectors
// can EXCLUDE it. "I told Alice…" must not mint the user as a colleague, and the user must not
// become the subject of most `statement` facts nor flood every co-occurrence detector. The
// identity entity is seeded once at provisioning; there is exactly ONE self-entity per book.
//
// Additive + non-destructive: every existing row defaults is_self=false, so nothing changes
// for existing entities. The one-self-per-book partial unique EXEMPTS soft-deleted tombstones
// (the partial-unique-must-exempt-tombstones lesson) so a re-provision after a delete is never
// blocked.
func UpEntityIsSelf(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-is-self", `
		ALTER TABLE glossary_entities
		  ADD COLUMN IF NOT EXISTS is_self BOOLEAN NOT NULL DEFAULT false;

		CREATE UNIQUE INDEX IF NOT EXISTS uq_glossary_entities_one_self_per_book
		  ON glossary_entities (book_id)
		  WHERE is_self AND deleted_at IS NULL;`)
}
