-- contracts/migrations/per_reality/0002_events_table.up.sql
--
-- L2.A.1 — `events` table (production shape).
--
-- Replaces the cycle-5 SKELETON `events` table with the real append-only
-- event log per the L2 layer plan (docs/plans/2026-05-29-foundation-mega-task/L2_event_sourcing.md
-- §L2.A) + R01 §12A volume mitigation.
--
-- LOCKED decisions consumed:
--   * Q-L2-2 (OPEN_QUESTIONS_LOCKED §4): MONTHLY range partition by recorded_at
--     — matches R01 §12A.4 archive cadence.
--   * Q-L2-3 (OPEN_QUESTIONS_LOCKED §4): `audit_ref UUID` is a POINTER (not FK)
--     to `event_audit.audit_id`. Events are archived independently of audit
--     rows; a FK would break post-archive. Wired logically in cycle-9 DPS 2.
--   * Q-L1D-1 (OPEN_QUESTIONS_LOCKED §1): no auto-rollback; this migration is
--     declared `breaking: true` in `contracts/migrations/manifest.yaml` so the
--     L1.D orchestrator routes it through the 1-reality canary.
--
-- Partitioning strategy:
--   * PARTITION BY RANGE (recorded_at) with one PARTITION per calendar month.
--   * Initial partition `events_p_initial` covers the [start_of_current_month,
--     start_of_current_month + 1 month) window. Real ops creates partitions
--     7d-ahead via `scripts/per-reality-partition-manager.sh` (cycle 9 DPS 1).
--   * Older partitions are detached + archived by L2.J archive-worker (cycle 11).
--
-- Compression:
--   * Postgres ≥14 supports per-column compression. Set `lz4` on `payload`
--     + `metadata` (the JSONB heavy hitters). Falls back to default `pglz`
--     if the cluster was built without lz4 — non-fatal.
--
-- Cross-cycle contracts:
--   * Cycle 8 (L2.F+G+I): every row's `event_type` + `event_version` MUST exist
--     in `contracts/events/_registry.yaml`; the L2.I validators_go layer
--     enforces this at write-time before INSERT.
--   * Cycle 8 (L2.A.4): `contracts/events/envelope.go` is the canonical row
--     shape — column names below match the JSON tags 1:1.
--   * Cycle 10 (L2.C): `outbox` table will reference `events.event_id`
--     transactionally — that wiring lands in DPS 1 of cycle 10.
--   * Cycle 11 (L2.J+K): retention + archive workers consume this table.
--
-- ⚠️ DO NOT add per-reality DOMAIN tables here. This file is L2 infra ONLY.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────
-- Drop cycle-5 skeleton (and the cycle-5 outbox FK depending on it)
-- ─────────────────────────────────────────────────────────────────────────
--
-- Cycle 5 shipped a non-partitioned placeholder `events` + a skeleton `outbox`
-- with `outbox.event_id REFERENCES events(event_id)`. Cycle 10 will re-create
-- `outbox` with its production shape. We drop the placeholder here so the new
-- partitioned `events` can be created cleanly. The outbox FK is implicitly
-- dropped with `outbox` table.
--
-- Idempotency: DROP ... IF EXISTS — safe to re-apply.

DROP TABLE IF EXISTS outbox;
DROP TABLE IF EXISTS events;

-- ─────────────────────────────────────────────────────────────────────────
-- events — append-only event log (partitioned, lz4-compressed)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    -- Identity
    event_id           UUID NOT NULL,
    -- Tenant + aggregate
    reality_id         UUID NOT NULL,
    aggregate_type     TEXT NOT NULL,
    aggregate_id       TEXT NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    -- Schema lookup (matches contracts/events/_registry.yaml entries)
    event_type         TEXT NOT NULL,
    event_version      INTEGER NOT NULL DEFAULT 1,
    -- Payload + envelope-level metadata
    payload            JSONB NOT NULL,
    metadata           JSONB,
    -- Timestamps
    occurred_at        TIMESTAMPTZ NOT NULL,
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Audit pointer (Q-L2-3: NOT a FK; points to event_audit.audit_id when set;
    -- NULL when no audit row was paired — common for non-LLM events).
    audit_ref          UUID,
    -- Forward-compat: schema-validator stamps the registry version it used.
    -- Enables L2.H upcaster-chain debug ("which schema did this row pass at
    -- write time"). NULL for pre-validator rows.
    registry_version   INTEGER,
    -- Constraints
    CONSTRAINT events_payload_is_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT events_metadata_is_object_or_null
        CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object'),
    CONSTRAINT events_aggregate_version_pos CHECK (aggregate_version > 0),
    CONSTRAINT events_event_version_pos CHECK (event_version >= 1),
    -- PK INCLUDES the partition key (recorded_at) per Postgres partitioning
    -- requirement. The logical uniqueness contract per the layer plan is
    -- (reality_id, aggregate_type, aggregate_id, aggregate_version) — that
    -- contract is enforced by the partial unique index below, which can omit
    -- recorded_at because each `(aggregate_id, aggregate_version)` slot is
    -- written exactly once (optimistic CC ⇒ second writer fails before INSERT).
    PRIMARY KEY (reality_id, aggregate_type, aggregate_id, aggregate_version, recorded_at)
) PARTITION BY RANGE (recorded_at);

-- Column compression: prefer lz4 (PG14+). If the cluster lacks lz4 the ALTER
-- silently keeps the default pglz; we guard via DO block to keep the migration
-- non-fatal on older clusters.
DO $$
BEGIN
    BEGIN
        ALTER TABLE events ALTER COLUMN payload  SET COMPRESSION lz4;
        ALTER TABLE events ALTER COLUMN metadata SET COMPRESSION lz4;
    EXCEPTION WHEN feature_not_supported OR undefined_object THEN
        RAISE NOTICE 'events: lz4 compression unavailable (PG<14 or build without lz4); using default pglz';
    END;
END$$;

COMMENT ON TABLE  events IS
    'L2.A append-only event log. Partitioned monthly on recorded_at (Q-L2-2). lz4-compressed JSONB. audit_ref is a UUID pointer, NOT FK (Q-L2-3).';
COMMENT ON COLUMN events.audit_ref IS
    'UUID pointer to event_audit.audit_id (NOT FK; events archived independently of audit). NULL when no audit row paired.';
COMMENT ON COLUMN events.registry_version IS
    'Snapshot of _registry.yaml `version:` at write time. Used by L2.H upcaster chain for debug.';

-- ─────────────────────────────────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────────────────────────────────
--
-- Index strategy (per L2.A layer plan + R01 §12A.6):
--   1. PK already covers per-aggregate ordered scans (reality_id, agg_type,
--      agg_id, agg_version, recorded_at).
--   2. By-time scan per reality (used by partition_manager + retention worker):
--      (reality_id, recorded_at).
--   3. By event_type filter (used by L2.J archive worker + admin tools):
--      (event_type, recorded_at).
--   4. Audit join (used to resurrect audit row from event id when LLM forensics
--      needs to walk events.event_id → event_audit.audit_id): on (event_id).
--   5. Logical uniqueness invariant cross-partition (defense in depth — PK is
--      already unique per partition; this catches the rare case where a writer
--      sets recorded_at twice for the same agg version): partial unique index.

CREATE INDEX IF NOT EXISTS events_by_reality_recorded_idx
    ON events (reality_id, recorded_at);

CREATE INDEX IF NOT EXISTS events_by_type_recorded_idx
    ON events (event_type, recorded_at);

CREATE INDEX IF NOT EXISTS events_event_id_idx
    ON events (event_id);

CREATE INDEX IF NOT EXISTS events_audit_ref_idx
    ON events (audit_ref)
    WHERE audit_ref IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────
-- Initial partition (current month). Subsequent partitions created by
-- scripts/per-reality-partition-manager.sh — see DPS 1 README.
-- ─────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    p_start DATE := date_trunc('month', NOW())::DATE;
    p_end   DATE := (date_trunc('month', NOW()) + INTERVAL '1 month')::DATE;
    p_name  TEXT := format('events_p_%s', to_char(p_start, 'YYYY_MM'));
    sql_text TEXT;
BEGIN
    sql_text := format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF events
             FOR VALUES FROM (%L) TO (%L);',
        p_name, p_start, p_end
    );
    EXECUTE sql_text;
END$$;

COMMIT;
