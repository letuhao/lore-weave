-- contracts/migrations/per_reality/0010_canon_projection_indexes.up.sql
--
-- L5.D.2 — Indexes on canon_projection.
--
-- LOCKED decisions consumed:
--   * Q-L5-3: single-table-with-canon_layer pattern → (book_id, canon_layer)
--     is the natural lookup for "all L1 canon for book X" and
--     "all L2 canon for book X" prompt-assembly queries.
--   * Q-L5-1: event-driven cache invalidation → meta-worker writes
--     last_synced_at on every successful write; an index on
--     (last_synced_at) supports the L5.E cache's "since" probe (cycle 25).
--   * Q-L3-4: VerificationMeta + applied_at / event_id pattern (carry from
--     cycle 13 L3.A — matches the 10 projection tables' index convention).
--
-- L5.D plan §L5.D.2 index list:
--   1. (book_id, canon_layer)              — composite for prompt assembly
--   2. partial (attribute_path) WHERE overridden_by_l3_event_id IS NULL
--                                          — HOT path: prompt-assembly
--                                            ignores shadowed entries
--   3. (last_synced_at)                    — cache invalidation probe
--   4. (applied_at DESC)                   — L3.E sampler convention
--   5. (event_id)                          — drift investigation convention
--
-- ⚠️  Index ordering matters for the composite — (book_id, canon_layer) is
--     a far better leading index than (canon_layer, book_id) because the
--     query pattern is "for this book, give me all canon" — book_id is
--     always present, layer-filter is optional / both.

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.2.1  Composite — prompt assembly main lookup
-- ───────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS canon_projection_book_layer_idx
    ON canon_projection (book_id, canon_layer);

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.2.2  Partial — HOT path: skip shadowed (L3-overridden) rows
-- ───────────────────────────────────────────────────────────────────────────
-- The [WORLD_CANON] prompt section (S09 §12Y.4) does NOT emit overridden
-- canon — instead the L3 event value replaces it. Using a PARTIAL index
-- WHERE overridden_by_l3_event_id IS NULL makes the prompt assembly query
-- skip overridden rows without index bloat.
CREATE INDEX IF NOT EXISTS canon_projection_attribute_path_active_idx
    ON canon_projection (attribute_path)
    WHERE overridden_by_l3_event_id IS NULL;

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.2.3  Cache invalidation probe
-- ───────────────────────────────────────────────────────────────────────────
-- L5.E cache (cycle 25) compares last_synced_at to its cached timestamp
-- to detect invalidations. An index supports the "WHERE last_synced_at > ?"
-- query pattern.
CREATE INDEX IF NOT EXISTS canon_projection_last_synced_idx
    ON canon_projection (last_synced_at);

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.2.4  L3.E sampler convention
-- ───────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS canon_projection_applied_at_idx
    ON canon_projection (applied_at DESC);

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.2.5  Drift investigation convention
-- ───────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS canon_projection_event_id_idx
    ON canon_projection (event_id);

-- ───────────────────────────────────────────────────────────────────────────
-- Bonus: cascade-source lookup. Cycle 24+ multiverse cascade orchestrator
-- will query "rows cascaded FROM reality X" to invalidate when X's canon
-- updates. Cardinality bounded by ancestry depth — typically < 100 per
-- reality in V1.
-- ───────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS canon_projection_cascade_source_idx
    ON canon_projection (cascaded_from_reality_id)
    WHERE cascaded_from_reality_id IS NOT NULL;

COMMIT;
