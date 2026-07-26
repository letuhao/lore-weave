package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpMergePolicy — chain step 0034 (extraction pipeline MERGE/M5, P4). Adds the two
// columns the merge-integrity contract needs (architecture rev 2 §8.6, detailed-design
// §2.5 / INV-8):
//
//   - entity_attribute_values.confidence — the per-SOURCE-value trust marker
//     ('machine' | 'draft' | 'verified'). Today only attribute_translations carried a
//     confidence, so a re-extraction `overwrite` could silently clobber a human-curated
//     SOURCE value (threat T2). With this marker the verified-clobber guard can refuse to
//     overwrite a value a human authored (the editor/apply-edit paths now stamp 'verified';
//     machine extraction writes leave the DEFAULT 'machine'). Backfill stays 'machine' —
//     every pre-existing source value was machine-written or pre-dates human verification,
//     so defaulting them to 'machine' is correct (a human re-verifies via the editor).
//
//   - {system_attributes,user_attributes,book_attributes}.merge_strategy — the
//     AUTHORED default strategy per attribute ('replace'|'fill_if_empty'|'append'|
//     'overwrite'|'manual'), provisioned now with the safe System default 'fill_if_empty'
//     (admin-only writes on the System tier). The runtime profile still drives the action
//     in Slice 1; the authored default + the trust-tier×strategy matrix are consumed in
//     Slice 2 (D-MERGE-STRATEGY-ONTOLOGY). Provisioning here keeps that a no-migration change.
//
// Additive + idempotent, routed through execGuarded. No data rewrite.
func UpMergePolicy(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "merge-policy", `
		ALTER TABLE entity_attribute_values
		  ADD COLUMN IF NOT EXISTS confidence TEXT NOT NULL DEFAULT 'machine';
		ALTER TABLE system_attributes
		  ADD COLUMN IF NOT EXISTS merge_strategy TEXT NOT NULL DEFAULT 'fill_if_empty';
		ALTER TABLE user_attributes
		  ADD COLUMN IF NOT EXISTS merge_strategy TEXT NOT NULL DEFAULT 'fill_if_empty';
		ALTER TABLE book_attributes
		  ADD COLUMN IF NOT EXISTS merge_strategy TEXT NOT NULL DEFAULT 'fill_if_empty';`)
}
