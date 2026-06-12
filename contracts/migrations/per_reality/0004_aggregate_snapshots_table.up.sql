-- contracts/migrations/per_reality/0004_aggregate_snapshots_table.up.sql
--
-- L2.E.1 — `aggregate_snapshots` table.
--
-- Production-shape snapshot table that replaces the cycle-5 SKELETON
-- `snapshots` placeholder. Used by aggregate loaders to short-circuit full
-- event-replay: instead of replaying 10K events for an aggregate, load
-- snapshot at v9500 + replay events.aggregate_version > 9500.
--
-- LOCKED decisions consumed:
--   * Q-L2-1 (OPEN_QUESTIONS_LOCKED §4): V1 sync projection. Snapshots are
--     a sync write-path optimization, not async projection infra.
--
-- Snapshot policy (OPT-IN, V1):
--   * No aggregate type takes snapshots by default. Opt-in per aggregate_type
--     via `contracts/events/snapshot_policy.yaml` (cycle 9 DPS 3 sibling).
--   * The policy file declares `every_n_events` (e.g. 500) — a separate
--     snapshot worker (lands cycle 14, L3 rebuild) honors the policy.
--   * Reader-side helper (cycle 12, L3 projection runtime) loads the latest
--     snapshot for an aggregate, falls back to full event replay when no
--     snapshot row exists (handled as the "no snapshot yet" base case).
--
-- Cross-cycle contracts:
--   * Cycle 12 (L3.B): projection runtime adds `crates/dp-kernel/src/snapshot.rs`
--     with the `LoadAggregate(reality_id, agg_type, agg_id)` helper.
--   * Cycle 14 (L3.D): rebuild orchestrator uses snapshots as fast-forward
--     checkpoints.
--   * Q-L3-4 (verification metadata): the cycle-13 projection migration adds
--     `verification_metadata` columns; for THIS L2.E table the verification
--     metadata is OUT of scope (snapshots are a write-path cache, not the
--     SSOT — events table is the SSOT).

BEGIN;

-- Drop cycle-5 skeleton snapshots placeholder (it had no reality_id col +
-- wrong PK shape for production).
DROP TABLE IF EXISTS snapshots;

CREATE TABLE IF NOT EXISTS aggregate_snapshots (
    -- Tenant + aggregate identity
    reality_id         UUID NOT NULL,
    aggregate_type     TEXT NOT NULL,
    aggregate_id       TEXT NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    -- Snapshot payload (the aggregate's projected state at this version)
    snapshot_data      JSONB NOT NULL,
    -- Metadata
    snapshot_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Schema-aware: which registry version was active when snapshot taken.
    -- Allows the loader to detect "snapshot taken under old schema; safer
    -- to re-replay" and fall back to full replay.
    registry_version   INTEGER,
    -- Constraints
    CONSTRAINT aggregate_snapshots_data_is_object
        CHECK (jsonb_typeof(snapshot_data) = 'object'),
    CONSTRAINT aggregate_snapshots_version_pos
        CHECK (aggregate_version > 0),
    -- PK includes reality_id for tenant isolation + aggregate_version so
    -- multiple snapshots per aggregate can co-exist (keep_last_3 policy in
    -- snapshot_policy.yaml — older rows pruned by the snapshot worker).
    PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version)
);

-- Compression on the payload JSONB
DO $$
BEGIN
    BEGIN
        ALTER TABLE aggregate_snapshots
            ALTER COLUMN snapshot_data SET COMPRESSION lz4;
    EXCEPTION WHEN feature_not_supported OR undefined_object THEN
        RAISE NOTICE 'aggregate_snapshots: lz4 unavailable; using default pglz';
    END;
END$$;

COMMENT ON TABLE  aggregate_snapshots IS
    'L2.E snapshot store. OPT-IN per aggregate_type via contracts/events/snapshot_policy.yaml. Loader falls back to full event replay when no snapshot row exists.';
COMMENT ON COLUMN aggregate_snapshots.registry_version IS
    'Active _registry.yaml version when snapshot was taken. Loader uses this to detect schema drift and fall back to full replay if mismatch.';

-- ─────────────────────────────────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────────────────────────────────
--
-- Latest-snapshot lookup is the hot path:
--   SELECT * FROM aggregate_snapshots
--     WHERE reality_id=$1 AND aggregate_type=$2 AND aggregate_id=$3
--     ORDER BY aggregate_version DESC LIMIT 1
-- The PK index already covers this (DESC scan on the trailing column is cheap
-- under btree). No extra index needed.
--
-- Prune scan by snapshot_at (when policy = "keep last N OR younger than T"):
--   index on (reality_id, snapshot_at).

CREATE INDEX IF NOT EXISTS aggregate_snapshots_prune_idx
    ON aggregate_snapshots (reality_id, snapshot_at);

COMMIT;
