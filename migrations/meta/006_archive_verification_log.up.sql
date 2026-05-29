-- 006_archive_verification_log.up.sql
-- L1.A-1 (cycle 2) — archive 5-step verification record (R9 hard gate before archived→archived_verified)
-- Source: L1A_meta_tables.md §1.6  (chunk R09 §12I.3)
-- Retention: 7y compliance
-- Append-only (S04 §12T.4)

CREATE TABLE IF NOT EXISTS archive_verification_log (
    verification_id   UUID            PRIMARY KEY,
    reality_id        UUID            NOT NULL,
    verifier_id       TEXT            NOT NULL,
    checks_passed     JSONB           NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT            NOT NULL,
    failure_reason    TEXT            NULL,
    sample_size       INT             NOT NULL DEFAULT 0,
    temp_db_host      TEXT            NULL,
    verified_at       TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT archive_verification_log_status_enum CHECK (
        status IN ('passed', 'failed', 'inconclusive')
    ),
    CONSTRAINT archive_verification_log_sample_size_nonneg CHECK (
        sample_size >= 0
    ),
    CONSTRAINT archive_verification_log_failure_reason_when_failed CHECK (
        (status = 'passed' AND failure_reason IS NULL) OR
        (status <> 'passed')
    )
);

-- Hot lookup: AttemptStateTransition('archived' → 'archived_verified') queries
-- the latest 'passed' row for the reality.
CREATE INDEX IF NOT EXISTS idx_archive_verification_log_reality_status_verified
    ON archive_verification_log (reality_id, status, verified_at DESC);

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE archive_verification_log FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_service_role missing; skip REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE archive_verification_log FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_admin_role missing; skip REVOKE';
END $$;

COMMENT ON TABLE archive_verification_log IS
    'L1.A-1 — archive 5-step verification record. 7y retention. Append-only (S04 §12T.4). Gates archived→archived_verified transition.';
