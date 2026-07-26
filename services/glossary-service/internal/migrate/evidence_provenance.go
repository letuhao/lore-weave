package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpEvidenceProvenance — chain step 0033 (extraction pipeline PROV/M3). Adds the
// offset + trust columns that let an extracted evidence quote trace to a specific
// location in the source AND record how trustworthy that location is.
//
// The gap (architecture rev 2 §P3): extraction wrote evidence with only chapter_id
// + original_text. chapter_index/chapter_title/block_or_line existed but were never
// populated, and there was no char offset and no trust marker — so a quote could not
// be traced to a paragraph/line, and a hallucinated quote was indistinguishable from
// a verified one.
//
// This adds:
//   - char_start / char_end — chapter-relative character offsets of the quote.
//   - provenance_status — the trust taxonomy (INV-7: model offsets are HINTS,
//     validated against the real text, never persisted as truth unverified):
//       'exact'      — offset matched the quote verbatim in the source
//       'resolved'   — quote found in the chapter, offset corrected to where it is
//       'ambiguous'  — quote occurs multiple times; a best-effort offset
//       'unmatched'  — quote not found in the chapter (likely a hallucination)
//       'unverified' — DEFAULT: not yet checked (chapter-level provenance only)
//
// Additive + idempotent, routed through execGuarded. The offsets/validation are
// POPULATED by the translation-side preprocess (the model-offset-trust step); this
// migration only provisions the columns + the safe default so the chapter-level
// provenance population can land first without exposing unvalidated offsets.
func UpEvidenceProvenance(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "evidence-provenance", `
		ALTER TABLE evidences ADD COLUMN IF NOT EXISTS char_start INT;
		ALTER TABLE evidences ADD COLUMN IF NOT EXISTS char_end   INT;
		ALTER TABLE evidences ADD COLUMN IF NOT EXISTS provenance_status TEXT NOT NULL DEFAULT 'unverified';
		CREATE INDEX IF NOT EXISTS idx_ev_provenance ON evidences(provenance_status);`)
}
