package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpKindIsPerson — C4 / SD-C4 (D-WIKI-PERSON-FLAG). A STRUCTURAL flag on every kind tier marking a
// kind as a REAL, private, non-consenting PERSON (a work colleague, the user's self, a custom
// "client"/"coworker" kind). The wiki-gen + enrichment guards (PP-4) refuse to LLM-manufacture a
// biography for a real person; they used to filter on the literal kind CODE 'colleague', so a
// RENAMED or CUSTOM person-kind leaked (a real person under a non-'colleague' code could still get an
// AI bio). This replaces that literal with the structural flag.
//
// SCOPE (human-amended 2026-07-15): `is_person` = REAL person only. `colleague` is seeded true;
// fiction `character` STAYS false — a fiction character is not a real person and MUST still get an AI
// wiki page (the blanket `NOT is_person` filter would otherwise exclude it, breaking fiction wiki-gen).
//
// Additive + non-destructive: every existing row defaults is_person=false, so nothing changes for
// existing kinds; the backfill then marks the seeded work-person kind 'colleague' true across all three
// tiers (system = the SoT seed, user = a cloned custom copy, book = the adopted copy the guards read).
// Idempotent: ADD COLUMN IF NOT EXISTS + an UPDATE that re-asserts the same rows.
func UpKindIsPerson(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "kind-is-person", `
		ALTER TABLE system_kinds ADD COLUMN IF NOT EXISTS is_person BOOLEAN NOT NULL DEFAULT false;
		ALTER TABLE user_kinds   ADD COLUMN IF NOT EXISTS is_person BOOLEAN NOT NULL DEFAULT false;
		ALTER TABLE book_kinds   ADD COLUMN IF NOT EXISTS is_person BOOLEAN NOT NULL DEFAULT false;

		-- Backfill the seeded work-person kind across every tier. 'colleague' is the only seeded REAL
		-- person kind (the other 6 work kinds — project/meeting/decision/task/jargon/org — are not
		-- people); fiction 'character' is deliberately NOT marked (see SCOPE above).
		UPDATE system_kinds SET is_person = true WHERE code = 'colleague' AND is_person = false;
		UPDATE user_kinds   SET is_person = true WHERE code = 'colleague' AND is_person = false;
		UPDATE book_kinds   SET is_person = true WHERE code = 'colleague' AND is_person = false;`)
}
