-- 016_service_to_service_audit.up.sql
-- L1.A-3 (cycle 4) — inter-service RPC audit; FULL audit per Q-L1A-3 (no sampling).
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §3.4
-- Owning kernel chunk: S11 §12AA
-- Retention: 5y (high-volume — see capacity note below)
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role
-- Written by: entry middleware on every service (records inbound RPC; ships with
-- the RPC middleware library — cycle 18+ L4 surface).
--
-- Q-L1A-3 (LOCKED 2026-05-29) capacity rationale:
--   V1 (~10 active realities × 100 RPC/turn × 100K turns/h)  → ~100K rows/day
--   V2 (~100 active realities × same rate)                    → ~1M rows/day
--   V3 (~1K active realities × same rate)                     → ~10M rows/day → ~3.6B/year
--   5y retention at V3 ≈ ~2 TB/year compressed → ~10 TB total.
--   Justifies dedicated audit DB cluster at V2+ per C03 §12O.10 (NOT this cycle —
--   V1 ships into shared meta DB sized for cycle 7 capacity buffer).

CREATE TABLE IF NOT EXISTS service_to_service_audit (
    audit_id            UUID            PRIMARY KEY,

    -- Edge identity
    caller_service      TEXT            NOT NULL,
    callee_service      TEXT            NOT NULL,
    rpc_name            TEXT            NOT NULL,

    -- Principal mode (S11 §12AA terminology)
    principal_mode      TEXT            NOT NULL,
    user_ref_id         UUID            NULL,            -- present when principal_mode requires/either

    -- Outcome
    result              TEXT            NOT NULL,        -- ok|deny|error|timeout
    latency_ms          INTEGER         NOT NULL DEFAULT 0,

    -- Correlation
    trace_id            TEXT            NOT NULL DEFAULT '',
    request_id          TEXT            NOT NULL DEFAULT '',

    created_at_nanos    BIGINT          NOT NULL,
    created_at          TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT s2s_audit_principal_mode_enum CHECK (
        principal_mode IN ('requires_user', 'system_only', 'either')
    ),
    CONSTRAINT s2s_audit_result_enum CHECK (
        result IN ('ok', 'deny', 'error', 'timeout')
    ),
    CONSTRAINT s2s_audit_caller_nonempty CHECK (length(caller_service) > 0),
    CONSTRAINT s2s_audit_callee_nonempty CHECK (length(callee_service) > 0),
    CONSTRAINT s2s_audit_rpc_nonempty CHECK (length(rpc_name) > 0),
    CONSTRAINT s2s_audit_latency_nonneg CHECK (latency_ms >= 0),
    CONSTRAINT s2s_audit_created_at_nanos_plausible CHECK (
        created_at_nanos > 1577836800000000000
    ),
    CONSTRAINT s2s_audit_user_ref_present_when_required CHECK (
        principal_mode <> 'requires_user' OR user_ref_id IS NOT NULL
    )
);

-- L1A §3.4 indexes
CREATE INDEX IF NOT EXISTS idx_s2s_audit_callee_rpc_created
    ON service_to_service_audit (callee_service, rpc_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_s2s_audit_caller_created
    ON service_to_service_audit (caller_service, created_at DESC);

-- Hot path: "user-scoped RPC trace by user_ref_id"
CREATE INDEX IF NOT EXISTS idx_s2s_audit_user_ref_partial
    ON service_to_service_audit (user_ref_id, created_at DESC)
    WHERE user_ref_id IS NOT NULL;

-- Deny+error spike alert hot path
CREATE INDEX IF NOT EXISTS idx_s2s_audit_failed_partial
    ON service_to_service_audit (callee_service, created_at DESC)
    WHERE result IN ('deny', 'error', 'timeout');

-- Append-only — REVOKE UPDATE/DELETE on application roles.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE service_to_service_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE service_to_service_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE service_to_service_audit IS
    'L1.A-3 — inter-service RPC audit. Append-only. Full audit (no sampling) per Q-L1A-3. Retention 5y. V2+ dedicated audit cluster scope.';
COMMENT ON COLUMN service_to_service_audit.principal_mode IS
    'Match against S11 §12AA — requires_user enforces user_ref_id presence; system_only forbids it (in middleware, not DB); either allows both.';
