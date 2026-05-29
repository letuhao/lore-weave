-- contracts/migrations/per_reality/0007_drift_metadata.up.sql
--
-- L3.K — Drift detection metadata table.
--
-- LIGHT state-tracking table that records the result of each
-- projection-drift-check.sh run (DPS 2 of cycle 13). The actual
-- integrity-checker service (L3.E daily sampler, L3.F monthly full check)
-- ships in cycle 14 — this migration ships ONLY the metadata table + a
-- supporting view so the cron skeleton (scripts/projection-drift-check.sh)
-- and the future integrity service can both read/write the same shape.
--
-- LOCKED decisions consumed:
--   * Q-L3-4 (OPEN_QUESTIONS_LOCKED §5): per-table verification HWM cols
--     (`last_verified_event_version`, `last_verified_at`) live ON each
--     projection row (added in cycle-13 0006_projections.up.sql). The
--     `projection_drift_state` table here aggregates that information at the
--     TABLE level so the alert system can ask "what was the last time we
--     verified table X overall?" in O(1) without scanning N rows.
--   * Q-L3E-1 (§5): integrity-checker is a SEPARATE service (cycle 14). The
--     drift metadata table is in the per-reality DB so both world-service
--     readers AND the future integrity-checker service can populate it
--     without cross-DB FK plumbing.
--   * Q-L3-5 (§5): NO V2 blue-green migration scaffolding. THIS table is
--     V1-only state; V2+ work (concurrent shadow projections) would add a
--     `projection_variant` column at that time.
--
-- Cross-cycle contracts:
--   * Cycle 13 (this cycle, DPS 1): adds VerificationMeta cols per row on
--     the 10 L3.A projection tables. THIS table is the table-level summary.
--   * Cycle 13 (this cycle, DPS 2): `scripts/projection-drift-check.sh`
--     cron skeleton WRITES rows here.
--   * Cycle 14 (L3.E sampler): replaces the cron skeleton with a real Go
--     daemon (`services/integrity-checker/`) that does sample re-replay
--     against event store + diff against the projection row.
--   * Cycle 14 (L3.J): emits `lw_projection_drift_count` from the rows in
--     this table (per-reality + per-table cardinality bounded by 10
--     projection tables × N realities).
--
-- ⚠️  DO NOT widen this table with sample-row payloads. It's a per-table
--    SUMMARY only. Drift INVESTIGATION queries should be issued live
--    against the projection tables' (event_id) index by SRE.

BEGIN;

CREATE TABLE IF NOT EXISTS projection_drift_state (
    -- One row per projection table. PK is the table_name string so the
    -- cron skeleton can SELECT/UPSERT without surrogate keys.
    table_name                   TEXT NOT NULL PRIMARY KEY,
    -- Last successful verification sweep (from L3.E daily sampler or L3.F
    -- monthly full check, post-cycle-14). NULL = never verified.
    last_verified_at             TIMESTAMPTZ,
    -- Sample size on the last sweep (config = sample_size from
    -- contracts/integrity/config.yaml, cycle-14). NULL = never run.
    last_sample_size             INTEGER,
    -- Drift count = rows where projection state didn't match re-replay
    -- result. 0 = healthy. Reset on every sweep — cumulative tracking is
    -- left to the metrics layer (lw_projection_drift_total counter,
    -- cycle 14).
    drift_count                  INTEGER NOT NULL DEFAULT 0,
    -- Last drifted aggregate (UUID); convenience for SRE investigation.
    -- NULL if `drift_count = 0`.
    last_drifted_aggregate_id    UUID,
    last_drifted_event_id        UUID,
    -- When the next scheduled sweep is expected. Used by alerting:
    -- "if NOW() > expected_next_sweep_at + grace, alert STALE_VERIFICATION".
    expected_next_sweep_at       TIMESTAMPTZ,
    -- Free-form note for SRE (e.g. "skipped — pgvector ext missing").
    notes                        TEXT,
    -- Always present.
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT projection_drift_count_nonneg
        CHECK (drift_count >= 0),
    CONSTRAINT projection_drift_table_name_allowlist
        -- Restricted to the 10 L3.A projection tables. New tables added in
        -- L4+ MUST extend this CHECK or use a different state table. This
        -- is deliberate cardinality fencing per I19.
        CHECK (table_name IN (
            'pc_projection',
            'pc_inventory_projection',
            'pc_relationship_projection',
            'npc_projection',
            'npc_session_memory_projection',
            'npc_pc_relationship_projection',
            'npc_session_memory_embedding',
            'region_projection',
            'world_kv_projection',
            'session_participants'
        ))
);

COMMENT ON TABLE projection_drift_state IS
    'L3.K — per-projection-table drift summary. Populated by L3.E/L3.F (cycle 14 integrity-checker). Read by L3.J alerts. Cardinality fenced to the 10 L3.A tables.';
COMMENT ON COLUMN projection_drift_state.last_verified_at IS
    'L3.E/F writes NOW() on every successful sweep regardless of drift_count. If NULL = never verified (CI gate via stale-verification alert).';
COMMENT ON COLUMN projection_drift_state.expected_next_sweep_at IS
    'Driven by the scheduler in contracts/integrity/config.yaml (cycle 14). Cron skeleton sets this = NOW() + 24h as a placeholder.';

-- ─────────────────────────────────────────────────────────────────────────
-- Seed all 10 projection table rows on first migration run so the cron
-- skeleton and integrity checker can UPDATE without an INSERT-first probe.
-- Idempotent: ON CONFLICT DO NOTHING.
-- ─────────────────────────────────────────────────────────────────────────
INSERT INTO projection_drift_state (table_name)
    VALUES
        ('pc_projection'),
        ('pc_inventory_projection'),
        ('pc_relationship_projection'),
        ('npc_projection'),
        ('npc_session_memory_projection'),
        ('npc_pc_relationship_projection'),
        ('npc_session_memory_embedding'),
        ('region_projection'),
        ('world_kv_projection'),
        ('session_participants')
ON CONFLICT (table_name) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────
-- View: stale_projections — for alert source-of-truth.
-- "Stale" = no verification ever, OR last_verified_at > 7 days ago.
-- Cycle 14 L3.J alert reads this.
-- ─────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW stale_projections AS
SELECT
    table_name,
    last_verified_at,
    drift_count,
    CASE
        WHEN last_verified_at IS NULL THEN 'never_verified'
        WHEN last_verified_at < NOW() - INTERVAL '7 days' THEN 'stale_over_7d'
        ELSE 'fresh'
    END AS staleness_state
FROM projection_drift_state
WHERE last_verified_at IS NULL
   OR last_verified_at < NOW() - INTERVAL '7 days';

COMMENT ON VIEW stale_projections IS
    'L3.K alert source. NULL last_verified_at = never run; > 7d = stale. Cycle 14 L3.J Prometheus alert reads this.';

COMMIT;
