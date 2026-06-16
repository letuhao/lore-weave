-- 004_lifecycle_transition_audit.up.sql
-- L1.A-1 (cycle 2) — every reality status transition (success + concurrency conflict + invalid)
-- Source: L1A_meta_tables.md §1.4  (chunk C05 §12Q.4)
-- Q-L1A-3: FULL audit from V1, no sampling.
-- Retention: `meta_write_audit` tier (5y) — see S04 §12T cross-ref
-- Written by: MetaWrite() internal via AttemptStateTransition() wrapper
-- Read by: SRE dashboard, conflict-heatmap (DF11)
-- Append-only enforcement: REVOKE UPDATE/DELETE on app_service_role + app_admin_role (S04 §12T.4)

CREATE TABLE IF NOT EXISTS lifecycle_transition_audit (
    audit_id          UUID            PRIMARY KEY,
    reality_id        UUID            NOT NULL,
    from_status       TEXT            NOT NULL,
    to_status         TEXT            NOT NULL,
    actor_id          UUID            NOT NULL,
    actor_type        TEXT            NOT NULL,
    succeeded         BOOLEAN         NOT NULL,
    failure_reason    TEXT            NULL,
    payload           JSONB           NOT NULL DEFAULT '{}'::jsonb,
    attempted_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT lifecycle_transition_audit_actor_type_enum CHECK (
        actor_type IN ('owner', 'admin', 'system', 'cron')
    ),
    CONSTRAINT lifecycle_transition_audit_failure_reason_when_failed CHECK (
        (succeeded = TRUE  AND failure_reason IS NULL) OR
        (succeeded = FALSE AND failure_reason IS NOT NULL)
    ),
    CONSTRAINT lifecycle_transition_audit_failure_reason_enum CHECK (
        failure_reason IS NULL OR failure_reason IN (
            'concurrent_modification',
            'invalid_transition',
            'mutual_exclusion',
            'precondition_failed',
            'database_error'
        )
    )
);

-- L1A §1.4 indexes
CREATE INDEX IF NOT EXISTS idx_lifecycle_transition_audit_reality_attempted
    ON lifecycle_transition_audit (reality_id, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_lifecycle_transition_audit_failures_partial
    ON lifecycle_transition_audit (attempted_at DESC, reality_id)
    WHERE succeeded = FALSE;

-- Append-only — REVOKE UPDATE/DELETE on application roles (S04 §12T.4).
-- Idempotent: DO/EXCEPTION so dev stacks without these roles don't fail.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE lifecycle_transition_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE lifecycle_transition_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE lifecycle_transition_audit IS
    'L1.A-1 — every reality status transition attempt (success/conflict/invalid). FULL audit per Q-L1A-3. Append-only (S04 §12T.4). Retention 5y.';
