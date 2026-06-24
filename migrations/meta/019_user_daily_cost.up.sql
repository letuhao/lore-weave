-- 019_user_daily_cost.up.sql
-- L1.A-4 (cycle 7) — per-user daily aggregate cap (V1+30d enforcement; table
-- exists at V1 launch so the rollup job can backfill on first run).
-- Source: L1A_meta_tables.md §4.3
-- Owning kernel chunk: S06 §12V.4
--
-- @pii_sensitivity: low
-- @retention_class: billing_ledger
-- @retention_hot: 7y
-- @erasure_method: pseudonymize_user_ref_at_2y
-- @legal_basis: legal_obligation

CREATE TABLE IF NOT EXISTS user_daily_cost (
    user_ref_id              UUID            NOT NULL,
    cost_date                DATE            NOT NULL,
    spent_micro_usd          BIGINT          NOT NULL DEFAULT 0,
    cap_micro_usd            BIGINT          NOT NULL,
    capped_at                TIMESTAMPTZ     NULL,
    last_rollup_at           TIMESTAMPTZ     NOT NULL DEFAULT now(),
    pseudonymized_at         TIMESTAMPTZ     NULL,
    pseudonymization_method  TEXT            NULL,
    PRIMARY KEY (user_ref_id, cost_date),
    CONSTRAINT user_daily_cost_spent_nonneg CHECK (spent_micro_usd >= 0),
    CONSTRAINT user_daily_cost_cap_positive CHECK (cap_micro_usd > 0),
    CONSTRAINT user_daily_cost_pseudonymization_quad_consistent CHECK (
        (pseudonymized_at IS NULL AND pseudonymization_method IS NULL)
        OR
        (pseudonymized_at IS NOT NULL AND pseudonymization_method IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_user_daily_cost_date_capped
    ON user_daily_cost (cost_date, capped_at)
    WHERE capped_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_daily_cost_pseudonymization_due
    ON user_daily_cost (cost_date)
    WHERE pseudonymized_at IS NULL;

DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE user_daily_cost FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE user_daily_cost FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE user_daily_cost IS
    'L1.A-4 §4.3 — per-user daily cost cap. 7y retention; pseudonymize at 2y. UPDATE allowed (rollup); no DELETE.';
