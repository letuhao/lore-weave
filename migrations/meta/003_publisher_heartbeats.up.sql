-- 003_publisher_heartbeats.up.sql
-- L1.A-1 (cycle 2) — outbox publisher liveness.
-- Source: L1A_meta_tables.md §1.3  (chunk R06 §12F.3)
-- Retention: Ephemeral (24h rolling; old `dead` rows cleaned by retention worker)
-- Written by: publisher (own heartbeat) + meta-worker (mark dead on no-heartbeat detection)
-- Read by: meta-worker (leader election) + SRE dashboard
-- Events: none (direct table write)

CREATE TABLE IF NOT EXISTS publisher_heartbeats (
    publisher_id        TEXT            PRIMARY KEY,
    shard_host          TEXT            NOT NULL,
    assigned_ranges     JSONB           NOT NULL DEFAULT '[]'::jsonb,
    last_heartbeat_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),
    status              TEXT            NOT NULL DEFAULT 'active',
    CONSTRAINT publisher_heartbeats_status_enum CHECK (
        status IN ('active', 'draining', 'dead')
    ),
    CONSTRAINT publisher_heartbeats_publisher_id_format CHECK (
        length(publisher_id) BETWEEN 1 AND 128
    )
);

-- L1A §1.3 index: (shard_host, last_heartbeat_at) for retention sweeps + dashboard
CREATE INDEX IF NOT EXISTS idx_publisher_heartbeats_shard_host_last_hb
    ON publisher_heartbeats (shard_host, last_heartbeat_at);

-- Partial index for leader-election hot path (active publishers only)
CREATE INDEX IF NOT EXISTS idx_publisher_heartbeats_active_partial
    ON publisher_heartbeats (publisher_id, last_heartbeat_at DESC)
    WHERE status = 'active';

COMMENT ON TABLE publisher_heartbeats IS
    'L1.A-1 — outbox publisher liveness; ephemeral 24h rolling; meta-worker monitors.';
