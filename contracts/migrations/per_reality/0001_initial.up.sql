-- contracts/migrations/per_reality/0001_initial.up.sql
--
-- L1.C.5 — Initial per-reality schema migration **SKELETON**.
--
-- This migration runs ONCE on every per-reality database when the
-- provisioner (L1.C.1) reaches step 5 (apply_initial_migration). Its
-- ONLY job is to scaffold the table set every per-reality DB needs:
--
--   * events          — append-only event log (event-sourcing kernel; L2)
--   * outbox          — transactional outbox for cross-reality events (L2)
--   * snapshots       — aggregate snapshot table (L3)
--   * projection_meta — per-projection bookkeeping (L3)
--
-- ALL FOUR are PLACEHOLDERS in cycle 5. The actual column lists,
-- partition strategy (monthly per Q-L2-2), indexes, and RLS policies
-- ship in:
--
--   * Cycle 8  — L2 schema infra (events partitioning, outbox dispatch)
--   * Cycle 9  — L2 per-reality tables (event_audit + outbox FK shape)
--   * Cycle 12 — L3 projection trait + snapshot read runtime
--
-- This file deliberately ships the **minimal placeholder** so:
--   1. the provisioner's step 5 has something concrete to apply
--   2. the integration test (reality_lifecycle_test.go) can verify the
--      tables exist after provisioning
--   3. L2/L3 cycles can ADD columns / indexes / partitions via subsequent
--      per_reality/000N migrations without rewriting this one
--
-- ⚠️ DO NOT add per-reality DOMAIN tables here (canon_projection, etc.).
-- Those belong in L2/L3 cycles. This file is **infrastructure only**.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────
-- events — append-only event log (skeleton; full DDL in cycle 8)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    event_id          UUID PRIMARY KEY,
    aggregate_type    TEXT NOT NULL,
    aggregate_id      TEXT NOT NULL,
    event_name        TEXT NOT NULL,
    event_version     INTEGER NOT NULL DEFAULT 1,
    payload           JSONB NOT NULL,
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Cycle 8 will add: monotonic sequence, partitioning column, schema_version,
    --                    correlation_id, causation_id, actor_type/id, etc.
    CONSTRAINT events_payload_is_object CHECK (jsonb_typeof(payload) = 'object')
);

COMMENT ON TABLE events IS
    'L1.C.5 SKELETON — append-only event log. Cycle 8 adds monthly partitioning per Q-L2-2.';

-- ─────────────────────────────────────────────────────────────────────────
-- outbox — transactional outbox (skeleton; cycle 8 ships dispatcher)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id         UUID PRIMARY KEY,
    event_id          UUID NOT NULL REFERENCES events(event_id) ON DELETE RESTRICT,
    topic             TEXT NOT NULL,
    dispatched_at     TIMESTAMPTZ,   -- NULL = pending; set on publisher ack
    attempts          INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    -- Cycle 8 adds: dispatch_lease (publisher claim), partition_key, ttl, etc.
    CONSTRAINT outbox_attempts_nonneg CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS outbox_pending_idx
    ON outbox (dispatched_at)
    WHERE dispatched_at IS NULL;

COMMENT ON TABLE outbox IS
    'L1.C.5 SKELETON — transactional outbox. Cycle 8 ships publisher claim leasing.';

-- ─────────────────────────────────────────────────────────────────────────
-- snapshots — aggregate snapshots (skeleton; cycle 12 ships projection)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS snapshots (
    aggregate_type    TEXT NOT NULL,
    aggregate_id      TEXT NOT NULL,
    snapshot_version  BIGINT NOT NULL,
    state             JSONB NOT NULL,
    taken_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Cycle 12 adds: verification_metadata column pair (Q-L3-4)
    PRIMARY KEY (aggregate_type, aggregate_id, snapshot_version),
    CONSTRAINT snapshots_state_is_object CHECK (jsonb_typeof(state) = 'object'),
    CONSTRAINT snapshots_version_pos CHECK (snapshot_version > 0)
);

COMMENT ON TABLE snapshots IS
    'L1.C.5 SKELETON — aggregate snapshot table. Cycle 12 adds verification metadata per Q-L3-4.';

-- ─────────────────────────────────────────────────────────────────────────
-- projection_meta — per-projection cursor + verification (skeleton)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS projection_meta (
    projection_name   TEXT PRIMARY KEY,
    last_event_id     UUID,
    last_applied_at   TIMESTAMPTZ,
    rebuild_state     TEXT NOT NULL DEFAULT 'idle',
    -- Cycle 13 adds: verification_metadata column pair (Q-L3-4); rebuild epoch.
    CONSTRAINT projection_meta_rebuild_state_enum
        CHECK (rebuild_state IN ('idle', 'rebuilding', 'failed'))
);

COMMENT ON TABLE projection_meta IS
    'L1.C.5 SKELETON — per-projection bookkeeping. Cycle 13 ships projection trait integration.';

COMMIT;
