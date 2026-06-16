-- 013_meta_write_audit.up.sql
-- L1.A-3 (cycle 4) — universal meta-write audit; records EVERY MetaWrite() call.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §3.1
-- Owning kernel chunk: S04 §12T.5
-- Retention: 5y (meta_write_audit tier, S08 §12X.4)
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role (S04 §12T.4)
-- Written by: MetaWrite() internal — one row per call in the SAME TX as the data write
--   (column shape matches contracts/meta/query_builder.go BuildAuditInsert + contracts/meta/metawrite.go).
--
-- Tamper resistance (V1): REVOKE-based append-only on application roles. Only the
-- superuser-owned retention job can shred (`retention_cron` actor — crypto-shred
-- of actor_id after 5y per S08 erasure matrix). V2+ adds hash chain (S08 §12X.7).
--
-- Q-L1A-3 (LOCKED 2026-05-29): full audit from V1, no sampling. Capacity sized
-- accordingly (see §3.4 for service_to_service_audit volume estimate; this table
-- is lower-cardinality than service_to_service_audit — bounded by MetaWrite call rate).

CREATE TABLE IF NOT EXISTS meta_write_audit (
    audit_id            UUID            PRIMARY KEY,

    -- Targeted write
    table_name          TEXT            NOT NULL,
    operation           TEXT            NOT NULL,
    row_pk              JSONB           NOT NULL,
    before_values       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    after_values        JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- Actor + context
    actor_type          TEXT            NOT NULL,
    actor_id            TEXT            NOT NULL,
    reason              TEXT            NOT NULL DEFAULT '',
    request_context     JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- Timing — stored as unix nanos for join-friendly precision with library Clock,
    -- mirrored to a TIMESTAMPTZ for human-readable index/query convenience.
    created_at_nanos    BIGINT          NOT NULL,
    created_at          TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT meta_write_audit_operation_enum CHECK (
        operation IN ('INSERT', 'UPDATE', 'DELETE')
    ),
    CONSTRAINT meta_write_audit_actor_type_enum CHECK (
        actor_type IN ('admin', 'system', 'service', 'retention_cron', 'owner', 'cron')
    ),
    CONSTRAINT meta_write_audit_actor_id_nonempty CHECK (length(actor_id) > 0),
    CONSTRAINT meta_write_audit_table_name_nonempty CHECK (length(table_name) > 0),
    -- created_at_nanos must be plausibly post-epoch (after 2020-01-01) to catch
    -- clock-skew or zero-init bugs at write time.
    CONSTRAINT meta_write_audit_created_at_nanos_plausible CHECK (
        created_at_nanos > 1577836800000000000  -- 2020-01-01T00:00:00Z in nanos
    )
);

-- L1A §3.1 indexes
CREATE INDEX IF NOT EXISTS idx_meta_write_audit_table_created
    ON meta_write_audit (table_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_meta_write_audit_actor_created
    ON meta_write_audit (actor_id, created_at DESC);

-- Partial index for forensics-grade "all admin writes" scan (hot path for DF11)
CREATE INDEX IF NOT EXISTS idx_meta_write_audit_admin_only_partial
    ON meta_write_audit (created_at DESC, actor_id)
    WHERE actor_type = 'admin';

-- Append-only — REVOKE UPDATE/DELETE on application roles (S04 §12T.4).
-- Idempotent: DO/EXCEPTION so dev stacks without these roles don't fail.
-- INSERT remains granted (set by overall migration grants).
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE meta_write_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE meta_write_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE meta_write_audit IS
    'L1.A-3 — universal meta-write audit (one row per MetaWrite call, same TX). Append-only (REVOKE UPDATE/DELETE). Retention 5y. Q-L1A-3 full audit, no sampling.';
COMMENT ON COLUMN meta_write_audit.created_at_nanos IS
    'Unix nanos from contracts/meta Clock — primary timing source; created_at is a derived TIMESTAMPTZ for index/query convenience.';
COMMENT ON COLUMN meta_write_audit.request_context IS
    'JSONB envelope with trace_id, request_id, source_service from contracts/meta RequestContext (S04 §12T.5).';
