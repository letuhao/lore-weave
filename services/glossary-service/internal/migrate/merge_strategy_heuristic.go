package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpMergeStrategyHeuristic — chain step 0039 (D-EXTRACT-ATTR-MERGE-DEFAULTS, M1).
//
// Re-seeds each ontology attribute's authored `merge_strategy` from a type-based
// heuristic, replacing the blanket `fill_if_empty` default (0034_merge_policy) that
// FROZE every already-filled attribute on re-extraction — `fill` means
// write-only-if-empty, so a recurring entity's attributes never advanced past the
// first chapter (only evidence kept accumulating). The heuristic restores the intent
// of extraction-as-automation: accumulate new knowledge as chapters advance.
//
//	identity   — code IN ('name','term') OR a required text key  → fill_if_empty (don't churn the key)
//	list/multi — field_type = 'tags'                             → append        (accumulate across chapters)
//	state/narr — everything else                                 → overwrite     (advance to the latest)
//
// Scope/tenancy: every tier is re-seeded ONLY where the strategy is still the
// untouched `fill_if_empty` default, so a deliberate admin (System) / author
// (per-user, per-book) override is NEVER clobbered — and a NEW attribute seeded
// later (which lands on the column DEFAULT 'fill_if_empty') is picked up on the
// next run. The CASE is deterministic, so re-running is a no-op on already-mapped
// rows (identity rows resolve back to 'fill_if_empty' = unchanged; append/overwrite
// rows no longer match the WHERE).
//
// This step only provisions the authored DEFAULTS the merge resolver falls through
// to; the accumulation becomes visible at runtime once the worker/FE stop forcing an
// explicit `fill` action (M2). Additive, idempotent, no schema change.
func UpMergeStrategyHeuristic(ctx context.Context, pool *pgxpool.Pool) error {
	const heuristic = `CASE
		    WHEN code IN ('name','term') THEN 'fill_if_empty'
		    WHEN is_required AND field_type = 'text' THEN 'fill_if_empty'
		    WHEN field_type = 'tags' THEN 'append'
		    ELSE 'overwrite'
		END`
	return execGuarded(ctx, pool, "merge-strategy-heuristic", `
		UPDATE system_attributes SET merge_strategy = `+heuristic+` WHERE merge_strategy = 'fill_if_empty';
		UPDATE user_attributes   SET merge_strategy = `+heuristic+` WHERE merge_strategy = 'fill_if_empty';
		UPDATE book_attributes   SET merge_strategy = `+heuristic+` WHERE merge_strategy = 'fill_if_empty';`)
}
