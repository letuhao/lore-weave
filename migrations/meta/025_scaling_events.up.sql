-- 025_scaling_events.up.sql
-- L1.A-4 (cycle 7) — capacity action audit (SR08). Needed by L1.L capacity-override flow.
-- Source: L1A_meta_tables.md §6.5; owning kernel chunk: SR08 §12AK
--
-- @pii_sensitivity: low (initiated_by uuid)
-- @retention_class: admin_audit
-- @retention_hot: 1y
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest
--
-- Append-only

CREATE TABLE IF NOT EXISTS scaling_events (
    scaling_event_id         UUID            PRIMARY KEY,
    event_type               TEXT            NOT NULL,        -- allocation|rebalance|freeze|override|capacity_warning
    shard_host               TEXT            NULL,
    reality_id               UUID            NULL,
    initiated_by             UUID            NOT NULL,
    initiator_type           TEXT            NOT NULL,        -- capacity_planner|admin|cron|alert
    -- For Tier-2 admin override: 24h auto-expire window (S5-D5)
    override_expires_at      TIMESTAMPTZ     NULL,
    payload                  JSONB           NOT NULL DEFAULT '{}'::jsonb,
    reason                   TEXT            NOT NULL,
    created_at               TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT scaling_events_event_type_enum CHECK (
        event_type IN ('allocation', 'rebalance', 'freeze', 'override', 'capacity_warning')
    ),
    CONSTRAINT scaling_events_initiator_type_enum CHECK (
        initiator_type IN ('capacity_planner', 'admin', 'cron', 'alert', 'system')
    ),
    -- Override events MUST set expiry (24h cap enforced by app code, audited here)
    CONSTRAINT scaling_events_override_has_expiry CHECK (
        (event_type = 'override' AND override_expires_at IS NOT NULL)
        OR
        (event_type <> 'override')
    ),
    CONSTRAINT scaling_events_override_expiry_within_24h CHECK (
        override_expires_at IS NULL
        OR override_expires_at <= created_at + INTERVAL '24 hours'
    ),
    CONSTRAINT scaling_events_reason_nonempty CHECK (length(reason) > 0)
);

CREATE INDEX IF NOT EXISTS idx_scaling_events_created
    ON scaling_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scaling_events_type_created
    ON scaling_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scaling_events_shard_created
    ON scaling_events (shard_host, created_at DESC)
    WHERE shard_host IS NOT NULL;

-- Active overrides (capacity admission check reads this)
CREATE INDEX IF NOT EXISTS idx_scaling_events_active_overrides
    ON scaling_events (override_expires_at)
    WHERE event_type = 'override' AND override_expires_at IS NOT NULL;

-- Append-only
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE scaling_events FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE scaling_events FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE scaling_events IS
    'L1.A-4 §6.5 / SR08 — capacity decision audit. 1y retention. Tier-2 overrides auto-expire 24h (S5-D5).';
