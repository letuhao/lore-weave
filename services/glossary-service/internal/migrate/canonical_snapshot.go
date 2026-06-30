package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpCanonicalSnapshot — chain step 0047. The canonical as a LAZY, VERSIONED,
// REGENERABLE CACHE (spec §12.1, B0 LOCKED) — NOT an immutable append-only series.
// A snapshot is a recomputable performance row; truth always lives in entity_facts
// (INV-FACTS §12.0), so a snapshot may be dropped and rebuilt from facts with no loss.
//
// canonical_snapshot — the cache rows:
//   - PRIMARY KEY (entity_id, attr_scope, as_of_ordinal, fold_algo_version): the cache
//     is keyed by the chapter it projects AND the fold algorithm version (bumped when
//     prompt/model/strategy changes, F6), so a diff never compares across versions.
//   - fact_coverage_xid (xid8): the max(entity_facts.coverage_xid) folded in — the
//     STALENESS key (B3/F6). A snapshot is VALID iff fold_algo_version == current AND no
//     fact with valid_from_ordinal <= as_of_ordinal has a coverage_xid newer than this.
//     A late/back-filled fact bumps the newest coverage_xid → every snapshot@>=its
//     ordinal goes stale → next read rebuilds from facts (self-healing; §4 Path-B
//     step 5 "re-fold cited snapshots" is DELETED — it was keyed on citations the new
//     fact lacks). content_hash (md5) is the translation-cache key (D8).
//   - canonical_status {current, stale, unbuildable}: degrade-safe (B4) — a quarantined
//     entity surfaces 'unbuildable' and the FE shows the structured facts instead of a
//     broken prose card. INV-FACTS guarantees the data is still readable from entity_facts.
//
// canonical_fold_state — the per-entity fold/re-ground bookkeeping (one row per entity):
//   - dirty + the existing compare-and-clear fingerprint guard (C3) drive the debounced
//     batch fold; NOT a bare "mark dirty -> fold".
//   - folds_since_reground / invalidations_since_reground: the DETERMINISTIC re-ground
//     trigger (B2) — re-ground when folds >= K OR invalidations >= J. Both are counters;
//     neither needs the rebuild it gates (no circular "drift signal").
//   - fold_attempts / fold_failed_at: explicit failure state + backoff (B4, mirror the KG
//     RETRY_BUDGET=3) so a poison fact can't wedge an entity into infinite re-fail.
//
// Schema only; the lazy rebuild-on-read, the ordinal-bucketed re-ground tree (B1), and
// the fold LLM call are the application handler (a later F2 slice). All idempotent,
// routed through execGuarded, forward-only.
func UpCanonicalSnapshot(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "canonical-snapshot", `
		CREATE TABLE IF NOT EXISTS canonical_snapshot (
		  entity_id          UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
		  attr_scope         TEXT NOT NULL DEFAULT 'narrative',
		  as_of_ordinal      BIGINT NOT NULL,
		  content            TEXT NOT NULL DEFAULT '',
		  content_hash       TEXT GENERATED ALWAYS AS (md5(content)) STORED,
		  fold_algo_version  INT NOT NULL DEFAULT 1,
		  fact_coverage_xid  xid8,
		  canonical_status   TEXT NOT NULL DEFAULT 'current',
		  built_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
		  PRIMARY KEY (entity_id, attr_scope, as_of_ordinal, fold_algo_version),
		  CONSTRAINT canonical_snapshot_status_chk
		    CHECK (canonical_status IN ('current','stale','unbuildable'))
		);
		CREATE INDEX IF NOT EXISTS idx_canonical_snapshot_entity
		  ON canonical_snapshot (entity_id, attr_scope);

		CREATE TABLE IF NOT EXISTS canonical_fold_state (
		  entity_id                     UUID NOT NULL,
		  attr_scope                    TEXT NOT NULL DEFAULT 'narrative',
		  dirty                         BOOLEAN NOT NULL DEFAULT false,
		  fold_fingerprint              TEXT,
		  folds_since_reground          INT NOT NULL DEFAULT 0,
		  invalidations_since_reground  INT NOT NULL DEFAULT 0,
		  fold_attempts                 INT NOT NULL DEFAULT 0,
		  fold_failed_at                TIMESTAMPTZ,
		  last_folded_at                TIMESTAMPTZ,
		  PRIMARY KEY (entity_id, attr_scope),
		  FOREIGN KEY (entity_id) REFERENCES glossary_entities(entity_id) ON DELETE CASCADE
		);
		-- Work queue: the debounced batch fold consumes dirty rows that are not quarantined.
		CREATE INDEX IF NOT EXISTS idx_canonical_fold_dirty
		  ON canonical_fold_state (entity_id)
		  WHERE dirty = true AND fold_attempts < 3;`)
}
