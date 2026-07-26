package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpCanonicalSummary — chain step 0043 (#26/#7 — the `summarize` merge-rewrite mode).
//
// The new `summarize` merge action keeps the lossless RAW item layer that `append`
// already maintains (per-item rows with chapter provenance) AND adds a synthesized
// CANONICAL layer: ONE deduped description an LLM rewrites from the accumulated raw
// mentions. These three columns hold that canonical layer on the EAV (1:1 with the
// attribute value, so columns — not a side table):
//
//   - canonical_value      — the synthesized text (NULL until the first resummarize pass).
//   - canonical_dirty       — set true by the writeback when a summarize attr's raw set
//                             changed; the end-of-extraction-job resummarize pass consumes
//                             it (fetch dirty → LLM rewrite → write canonical → clear).
//   - canonical_synced_at   — when the canonical value was last (re)synthesized.
//
// Additive + idempotent, routed through execGuarded. No data rewrite — existing rows get
// canonical_value=NULL / canonical_dirty=false, so non-summarize attributes are inert.
func UpCanonicalSummary(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "canonical-summary", `
		ALTER TABLE entity_attribute_values
		  ADD COLUMN IF NOT EXISTS canonical_value TEXT;
		ALTER TABLE entity_attribute_values
		  ADD COLUMN IF NOT EXISTS canonical_dirty BOOLEAN NOT NULL DEFAULT false;
		ALTER TABLE entity_attribute_values
		  ADD COLUMN IF NOT EXISTS canonical_synced_at TIMESTAMPTZ;`)
}
