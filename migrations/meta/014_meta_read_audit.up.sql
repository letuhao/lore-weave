-- 014_meta_read_audit.up.sql
-- L1.A-3 (cycle 4) — enumerated sensitive-path read audit.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §3.2
-- Owning kernel chunk: S04 §12T.6
-- Retention: 2y (meta_read_audit tier, S08 §12X.4)
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role
-- Written by: instrumentation library wrapping enumerated sensitive-read paths
--   (see contracts/meta/meta-sensitive-read-paths.yml for the enumerated set).
--
-- Performance posture: NOT every read. Only the enumerated sensitive paths
-- (`player_index_cross_user`, `audit_query`, `admin_bulk_export`, and any
-- query exceeding 1000-row LIMIT or lacking a WHERE filter on hot meta tables).
-- The enumeration is reviewed quarterly by the security team.
--
-- Cardinality budget: ~10% of total meta reads (heuristic from S04 §12T.6).
-- Storage estimate: ~50M rows/year at V3 active-realities load → 100M rows for
-- 2y retention. Single shared meta DB still adequate; V2+ dedicated audit cluster
-- per C03 §12O.10 captures both read+write audit when service_to_service_audit
-- volume forces the split.

CREATE TABLE IF NOT EXISTS meta_read_audit (
    audit_id            UUID            PRIMARY KEY,

    -- Which enumerated sensitive path was traversed
    query_type          TEXT            NOT NULL,

    -- The enumerated set is FROZEN by meta-sensitive-read-paths.yml; library
    -- rejects writes with a query_type not in the loaded set at insert time.
    -- CHECK below is a defense-in-depth subset; the YAML file is the source
    -- of truth and may grow (CHECK can be relaxed in a later migration).
    parameters          JSONB           NOT NULL DEFAULT '{}'::jsonb,
    actor_id            TEXT            NOT NULL,
    actor_type          TEXT            NOT NULL,
    result_count        INTEGER         NOT NULL DEFAULT 0,

    created_at_nanos    BIGINT          NOT NULL,
    created_at          TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT meta_read_audit_query_type_enum CHECK (
        query_type IN (
            'player_index_cross_user',
            'audit_query',
            'admin_bulk_export',
            'unbounded_select',
            'bulk_pii_read',
            'consent_audit_export'
        )
    ),
    CONSTRAINT meta_read_audit_actor_type_enum CHECK (
        actor_type IN ('admin', 'system', 'service', 'retention_cron', 'owner', 'cron')
    ),
    CONSTRAINT meta_read_audit_actor_id_nonempty CHECK (length(actor_id) > 0),
    CONSTRAINT meta_read_audit_result_count_nonneg CHECK (result_count >= 0),
    CONSTRAINT meta_read_audit_created_at_nanos_plausible CHECK (
        created_at_nanos > 1577836800000000000
    )
);

-- L1A §3.2 indexes
CREATE INDEX IF NOT EXISTS idx_meta_read_audit_actor_created
    ON meta_read_audit (actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_meta_read_audit_query_type_created
    ON meta_read_audit (query_type, created_at DESC);

-- Anomaly-detector hot path: "bulk-read spike for actor X in last 1h"
CREATE INDEX IF NOT EXISTS idx_meta_read_audit_high_result_partial
    ON meta_read_audit (actor_id, created_at DESC)
    WHERE result_count > 1000;

-- Append-only — REVOKE UPDATE/DELETE on application roles (S04 §12T.4).
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE meta_read_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE meta_read_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE meta_read_audit IS
    'L1.A-3 — enumerated sensitive-read audit. Append-only. Retention 2y. Enumeration source: contracts/meta/meta-sensitive-read-paths.yml.';
COMMENT ON COLUMN meta_read_audit.query_type IS
    'Identifies the enumerated sensitive path (see meta-sensitive-read-paths.yml). CHECK enum may lag the YAML source; library is the gate.';
COMMENT ON COLUMN meta_read_audit.parameters IS
    'JSONB of caller-supplied query parameters AFTER scrubbing through S08 §12X.5 scrubber (no raw PII).';
