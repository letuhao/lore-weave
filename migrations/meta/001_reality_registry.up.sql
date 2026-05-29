-- 001_reality_registry.up.sql
-- L1.A-1 (cycle 2) — primary routing table for `reality_id → physical Postgres DB`.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §1.1
-- Owning kernel chunks: R04 §12D + S04 §12T.3 + R09 §12I.2 + SR05 §12AH.4
-- Retention: until row reaches `dropped` final state (~120d minimum, R9 §12I.1 6-state machine)
-- Read by: ALL services (hot path; cached 30s in Redis per C03 §12O.6)
-- Written by: world-service (lifecycle) + migration-orchestrator (migration fields)
--   ALL writes via contracts/meta MetaWrite() + AttemptStateTransition() (I8 invariant)

CREATE TABLE IF NOT EXISTS reality_registry (
    reality_id              UUID            PRIMARY KEY,

    -- Routing
    db_host                 TEXT            NOT NULL,
    db_name                 TEXT            NOT NULL,

    -- Status + invariants (CHECK enums)
    status                  TEXT            NOT NULL,
    status_transition_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Locale (BCP-47 short form)
    locale                  TEXT            NOT NULL,

    -- Session caps
    session_max_pcs         INT             NOT NULL,
    session_max_npcs        INT             NOT NULL,
    session_max_total       INT             NOT NULL,

    -- Close lifecycle (R09 §12I.2)
    close_initiated_by      UUID            NULL,
    close_initiated_at      TIMESTAMPTZ     NULL,
    close_reason            TEXT            NULL,

    -- Archive verification gate (R09 §12I.3)
    archive_verified_at     TIMESTAMPTZ     NULL,
    archive_verification_id UUID            NULL,

    -- Soft-delete + drop (R09 §12I.1)
    soft_delete_name        TEXT            NULL,
    drop_scheduled_at       TIMESTAMPTZ     NULL,
    drop_approved_by        UUID            NULL,
    drop_approved_at        TIMESTAMPTZ     NULL,

    -- Canary cohort (SR05 §12AH.4): hash(reality_id) % 100, stable for canary rollout
    deploy_cohort           INT             NOT NULL,

    -- Bookkeeping
    last_stats_updated_at   TIMESTAMPTZ     NULL,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT reality_registry_db_host_format CHECK (
        db_host ~ '^pg-shard-[0-9]+\.(internal|prod|staging)$'
    ),
    CONSTRAINT reality_registry_db_name_nonempty CHECK (
        length(db_name) BETWEEN 1 AND 63
    ),
    CONSTRAINT reality_registry_status_enum CHECK (
        status IN (
            'provisioning',
            'seeding',
            'active',
            'pending_close',
            'frozen',
            'migrating',
            'archived',
            'archived_verified',
            'soft_deleted',
            'dropped'
        )
    ),
    CONSTRAINT reality_registry_locale_format CHECK (
        locale ~ '^[a-z]{2}(-[A-Z]{2})?$'
    ),
    CONSTRAINT reality_registry_session_max_pcs_range  CHECK (session_max_pcs  BETWEEN 1 AND 50),
    CONSTRAINT reality_registry_session_max_npcs_range CHECK (session_max_npcs BETWEEN 0 AND 50),
    CONSTRAINT reality_registry_session_max_total_range CHECK (
        session_max_total BETWEEN 2 AND 100
        AND session_max_total >= session_max_pcs
    ),
    CONSTRAINT reality_registry_deploy_cohort_range CHECK (
        deploy_cohort BETWEEN 0 AND 99
    )
);

-- Indexes (L1A §1.1)
CREATE INDEX IF NOT EXISTS idx_reality_registry_db_host
    ON reality_registry (db_host);

CREATE INDEX IF NOT EXISTS idx_reality_registry_status
    ON reality_registry (status);

CREATE INDEX IF NOT EXISTS idx_reality_registry_deploy_cohort
    ON reality_registry (deploy_cohort);

CREATE INDEX IF NOT EXISTS idx_reality_registry_active_partial
    ON reality_registry (reality_id)
    WHERE status = 'active';

-- updated_at trigger (so MetaWrite() doesn't have to remember it; defense-in-depth)
CREATE OR REPLACE FUNCTION reality_registry_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reality_registry_touch_updated_at_trg ON reality_registry;
CREATE TRIGGER reality_registry_touch_updated_at_trg
    BEFORE UPDATE ON reality_registry
    FOR EACH ROW EXECUTE FUNCTION reality_registry_touch_updated_at();

COMMENT ON TABLE reality_registry IS
    'L1.A-1 — primary reality routing table. ALL writes via contracts/meta MetaWrite() + AttemptStateTransition() (I8).';
