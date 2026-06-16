-- 021_incidents.up.sql
-- L1.A-4 (cycle 7) — incident lifecycle tracker (SR02).
-- Source: L1A_meta_tables.md §6.1; owning kernel chunk: SR02 §12AE
--
-- @pii_sensitivity: low (incident commander id is opaque user_ref_id)
-- @retention_class: admin_audit
-- @retention_hot: 7y
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest (also GDPR Art. 33 breach notification)

CREATE TABLE IF NOT EXISTS incidents (
    incident_id              UUID            PRIMARY KEY,
    severity                 TEXT            NOT NULL,
    severity_history         JSONB           NOT NULL DEFAULT '[]'::jsonb,
    status                   TEXT            NOT NULL,
    declared_at              TIMESTAMPTZ     NOT NULL,
    triaged_at               TIMESTAMPTZ     NULL,
    mitigated_at             TIMESTAMPTZ     NULL,
    resolved_at              TIMESTAMPTZ     NULL,
    postmortem_due_at        TIMESTAMPTZ     NULL,
    postmortem_url           TEXT            NULL,
    incident_commander       UUID            NULL,
    affected_services        TEXT[]          NOT NULL DEFAULT ARRAY[]::TEXT[],
    declared_by              UUID            NOT NULL,
    declaration_source       TEXT            NOT NULL,         -- manual|auto_alert|chaos_drill
    summary                  TEXT            NOT NULL,
    last_status_at           TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT incidents_severity_enum CHECK (
        severity IN ('SEV0', 'SEV1', 'SEV2', 'SEV3')
    ),
    CONSTRAINT incidents_status_enum CHECK (
        status IN ('declared', 'triaged', 'mitigated', 'resolved', 'postmortem', 'closed')
    ),
    CONSTRAINT incidents_declaration_source_enum CHECK (
        declaration_source IN ('manual', 'auto_alert', 'chaos_drill', 'sentinel')
    ),
    -- timeline monotonic forward
    CONSTRAINT incidents_triaged_after_declared CHECK (
        triaged_at IS NULL OR triaged_at >= declared_at
    ),
    CONSTRAINT incidents_mitigated_after_triaged CHECK (
        mitigated_at IS NULL OR (triaged_at IS NOT NULL AND mitigated_at >= triaged_at)
    ),
    CONSTRAINT incidents_resolved_after_mitigated CHECK (
        resolved_at IS NULL OR (mitigated_at IS NOT NULL AND resolved_at >= mitigated_at)
    ),
    CONSTRAINT incidents_postmortem_when_sev01_resolved CHECK (
        -- SEV0/SEV1 closed requires a postmortem reference
        NOT (status = 'closed' AND severity IN ('SEV0', 'SEV1') AND postmortem_url IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_incidents_status_declared
    ON incidents (status, declared_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_severity_declared
    ON incidents (severity, declared_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_active
    ON incidents (last_status_at DESC)
    WHERE status NOT IN ('closed');

CREATE INDEX IF NOT EXISTS idx_incidents_postmortem_due
    ON incidents (postmortem_due_at)
    WHERE postmortem_due_at IS NOT NULL AND postmortem_url IS NULL;

-- Lifecycle state-machine drives status via AttemptStateTransition;
-- UPDATE allowed by app_admin_role (SRE), no DELETE.
DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE incidents FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE incidents FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE incidents IS
    'L1.A-4 §6.1 / SR02 — incident lifecycle tracker. 7y retention; state machine via contracts/meta lifecycle.';
