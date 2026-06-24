-- 023_deploy_audit.up.sql
-- L1.A-4 (cycle 7) — per-deploy audit (SR05). Foundation for canary-controller (cycle 38).
-- Source: L1A_meta_tables.md §6.3; owning kernel chunk: SR05 §12AH
--
-- @pii_sensitivity: low (triggered_by uuid only)
-- @retention_class: ops_metrics
-- @retention_hot: 1y
-- @erasure_method: hard_delete
-- @legal_basis: legitimate_interest
--
-- Append-only

CREATE TABLE IF NOT EXISTS deploy_audit (
    deploy_id                UUID            PRIMARY KEY,
    class                    TEXT            NOT NULL,         -- patch|minor|major|emergency
    services_touched         TEXT[]          NOT NULL DEFAULT ARRAY[]::TEXT[],
    migration_ids            TEXT[]          NOT NULL DEFAULT ARRAY[]::TEXT[],
    canary_stage             INT             NOT NULL DEFAULT 0,
    canary_history           JSONB           NOT NULL DEFAULT '[]'::jsonb,
    rolled_back              BOOLEAN         NOT NULL DEFAULT FALSE,
    rollback_reason          TEXT            NULL,
    triggered_by             UUID            NOT NULL,
    git_commit_sha           TEXT            NOT NULL,
    started_at               TIMESTAMPTZ     NOT NULL DEFAULT now(),
    completed_at             TIMESTAMPTZ     NULL,

    CONSTRAINT deploy_audit_class_enum CHECK (
        class IN ('patch', 'minor', 'major', 'emergency')
    ),
    CONSTRAINT deploy_audit_canary_stage_nonneg CHECK (canary_stage >= 0),
    CONSTRAINT deploy_audit_completed_after_started CHECK (
        completed_at IS NULL OR completed_at >= started_at
    ),
    CONSTRAINT deploy_audit_git_commit_sha_format CHECK (
        length(git_commit_sha) >= 7
    ),
    CONSTRAINT deploy_audit_rollback_reason_consistent CHECK (
        (rolled_back = FALSE AND rollback_reason IS NULL)
        OR
        (rolled_back = TRUE AND rollback_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_deploy_audit_started
    ON deploy_audit (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_deploy_audit_rolled_back
    ON deploy_audit (started_at DESC)
    WHERE rolled_back = TRUE;

CREATE INDEX IF NOT EXISTS idx_deploy_audit_class_started
    ON deploy_audit (class, started_at DESC);

-- Append-only enforcement
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE deploy_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

-- Canary controller IS allowed UPDATE to set canary_history + completed_at;
-- the dedicated role app_canary_role gets that grant when canary-controller ships
-- (cycle 38). For V1 admin/SRE only marks completed/rolled_back via admin-cli.

COMMENT ON TABLE deploy_audit IS
    'L1.A-4 §6.3 / SR05 — per-deploy audit. 1y retention. Canary controller (cycle 38) UPDATEs canary_history.';
