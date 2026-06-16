-- 024_shard_utilization.up.sql
-- L1.A-4 (cycle 7) — Postgres shard live metrics (SR08). Needed by L1.L capacity planner.
-- Source: L1A_meta_tables.md §6.4; owning kernel chunk: SR08 §12AK
--
-- @pii_sensitivity: none
-- @retention_class: ops_metrics
-- @retention_hot: 90d
-- @erasure_method: hard_delete
-- @legal_basis: legitimate_interest

CREATE TABLE IF NOT EXISTS shard_utilization (
    snapshot_id              UUID            PRIMARY KEY,
    shard_host               TEXT            NOT NULL,
    snapshot_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    current_db_count         INT             NOT NULL DEFAULT 0,
    total_storage_bytes      BIGINT          NOT NULL DEFAULT 0,
    cpu_load_pct             NUMERIC(5,2)    NOT NULL DEFAULT 0,
    connection_count         INT             NOT NULL DEFAULT 0,
    capacity_max_dbs         INT             NOT NULL,
    capacity_max_bytes       BIGINT          NOT NULL,

    CONSTRAINT shard_utilization_shard_host_format CHECK (
        shard_host ~ '^pg-shard-[0-9]+\.(internal|prod|staging|dev|local)$'
    ),
    CONSTRAINT shard_utilization_counters_nonneg CHECK (
        current_db_count >= 0 AND total_storage_bytes >= 0
        AND connection_count >= 0
    ),
    CONSTRAINT shard_utilization_cpu_range CHECK (
        cpu_load_pct >= 0 AND cpu_load_pct <= 100
    ),
    CONSTRAINT shard_utilization_capacity_positive CHECK (
        capacity_max_dbs > 0 AND capacity_max_bytes > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_shard_utilization_host_at
    ON shard_utilization (shard_host, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_shard_utilization_at
    ON shard_utilization (snapshot_at DESC);

COMMENT ON TABLE shard_utilization IS
    'L1.A-4 §6.4 / SR08 — per-shard utilization snapshots. 90d rolling. Read by capacity_planner (L1.C).';
