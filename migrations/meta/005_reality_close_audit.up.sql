-- 005_reality_close_audit.up.sql
-- L1.A-1 (cycle 2) — R9 close-lifecycle compliance trail.
-- Source: L1A_meta_tables.md §1.5  (chunk R09 §12I)
-- Retention: 7y compliance (admin_audit tier extended)
-- Append-only (S04 §12T.4)

CREATE TABLE IF NOT EXISTS reality_close_audit (
    audit_id              UUID            PRIMARY KEY,
    reality_id            UUID            NOT NULL,
    event_type            TEXT            NOT NULL,
    actor_id              UUID            NOT NULL,
    actor_type            TEXT            NOT NULL,
    occurred_at           TIMESTAMPTZ     NOT NULL DEFAULT now(),
    payload               JSONB           NOT NULL DEFAULT '{}'::jsonb,
    -- snapshot of relevant reality_registry columns at the time of the event
    snapshot_status       TEXT            NULL,
    snapshot_close_reason TEXT            NULL,
    CONSTRAINT reality_close_audit_event_type_enum CHECK (
        event_type IN (
            'close_initiated',
            'close_cancelled',
            'archive_completed',
            'archive_verified',
            'soft_deleted',
            'dropped'
        )
    ),
    CONSTRAINT reality_close_audit_actor_type_enum CHECK (
        actor_type IN ('owner', 'admin', 'system', 'cron')
    )
);

CREATE INDEX IF NOT EXISTS idx_reality_close_audit_reality_occurred
    ON reality_close_audit (reality_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_reality_close_audit_event_type_occurred
    ON reality_close_audit (event_type, occurred_at DESC);

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_close_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_service_role missing; skip REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_close_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN RAISE NOTICE 'role app_admin_role missing; skip REVOKE';
END $$;

COMMENT ON TABLE reality_close_audit IS
    'L1.A-1 — R9 close-lifecycle compliance trail. 7y retention. Append-only (S04 §12T.4).';
