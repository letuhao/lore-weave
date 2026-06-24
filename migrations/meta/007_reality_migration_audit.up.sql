-- 007_reality_migration_audit.up.sql
-- L1.A-1 (cycle 2) — per-reality migration run audit (start, attempts, success, failure_detail)
-- Source: L1A_meta_tables.md §1.7  (chunks R04 §12D.2 + SR05 §12AH deploy classification)
-- Retention: 1y
-- Written by: migration-orchestrator
-- Append-only (S04 §12T.4)

CREATE TABLE IF NOT EXISTS reality_migration_audit (
    audit_id            UUID            PRIMARY KEY,
    reality_id          UUID            NOT NULL,
    migration_id        TEXT            NOT NULL,
    run_id              UUID            NOT NULL,
    event_type          TEXT            NOT NULL,
    attempt_number      INT             NOT NULL DEFAULT 1,
    deploy_cohort       INT             NULL,
    failure_detail      JSONB           NULL,
    occurred_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT reality_migration_audit_event_type_enum CHECK (
        event_type IN (
            'migration_started',
            'migration_succeeded',
            'migration_failed',
            'migration_aborted',
            'migration_rolled_back'
        )
    ),
    CONSTRAINT reality_migration_audit_attempt_number_pos CHECK (attempt_number >= 1),
    CONSTRAINT reality_migration_audit_deploy_cohort_range CHECK (
        deploy_cohort IS NULL OR deploy_cohort BETWEEN 0 AND 99
    )
);

CREATE INDEX IF NOT EXISTS idx_reality_migration_audit_reality_occurred
    ON reality_migration_audit (reality_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_reality_migration_audit_run
    ON reality_migration_audit (run_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_reality_migration_audit_failures_partial
    ON reality_migration_audit (reality_id, occurred_at DESC)
    WHERE event_type IN ('migration_failed', 'migration_aborted', 'migration_rolled_back');

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_migration_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_service_role missing; skip REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_migration_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_admin_role missing; skip REVOKE';
END $$;

COMMENT ON TABLE reality_migration_audit IS
    'L1.A-1 — per-reality migration run audit. 1y retention. Append-only (S04 §12T.4).';
