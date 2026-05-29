-- 018_user_cost_ledger.up.sql
-- L1.A-4 (cycle 7) — per-user LLM cost tracking (the FOUNDATIONAL billing table).
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §4.1
-- Owning kernel chunk: S06 §12V (ledger spec)
--
-- LOCKED Q-IDs honored:
--   * Q-L1A-3 (full audit no sampling) — every INSERT lands a meta_write_audit
--     row via MetaWrite() in the same TX; the application code MUST go through
--     the contracts/meta library so the financial-grade audit invariant holds.
--
-- @pii_sensitivity: low (user_ref_id is opaque; provider/model not PII; cost numeric)
-- @retention_class: billing_ledger
-- @retention_hot: 7y
-- @erasure_method: pseudonymize_user_ref_at_2y
-- @legal_basis: legal_obligation (tax/regulatory)
--
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role
-- (financial ledger; corrections land as offset INSERTs with reason='correction').

CREATE TABLE IF NOT EXISTS user_cost_ledger (
    ledger_id                UUID            PRIMARY KEY,
    user_ref_id              UUID            NOT NULL,
    reality_id               UUID            NULL,           -- nullable for non-reality LLM calls
    session_id               UUID            NULL,
    provider_id              TEXT            NOT NULL,
    model_id                 TEXT            NOT NULL,
    prompt_tokens            BIGINT          NOT NULL DEFAULT 0,
    completion_tokens        BIGINT          NOT NULL DEFAULT 0,
    cost_micro_usd           BIGINT          NOT NULL,
    tier                     TEXT            NOT NULL,        -- free|paid|trial|grant
    -- correlation back to prompt_audit (forensic match without re-storing body)
    prompt_audit_id          UUID            NULL,
    -- reason='charge' | 'correction' | 'refund' (correction must reference original)
    reason                   TEXT            NOT NULL DEFAULT 'charge',
    original_ledger_id       UUID            NULL,            -- non-null only for reason='correction'|'refund'
    -- pseudonymization marker (Q-L1A-3 + retention matrix S08 §12X.4 row 'billing_ledger')
    pseudonymized_at         TIMESTAMPTZ     NULL,
    pseudonymization_method  TEXT            NULL,
    created_at_nanos         BIGINT          NOT NULL,
    created_at               TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT user_cost_ledger_provider_nonempty CHECK (length(provider_id) > 0),
    CONSTRAINT user_cost_ledger_model_nonempty CHECK (length(model_id) > 0),
    CONSTRAINT user_cost_ledger_tokens_nonneg CHECK (
        prompt_tokens >= 0 AND completion_tokens >= 0
    ),
    CONSTRAINT user_cost_ledger_tier_enum CHECK (
        tier IN ('free', 'paid', 'trial', 'grant')
    ),
    CONSTRAINT user_cost_ledger_reason_enum CHECK (
        reason IN ('charge', 'correction', 'refund')
    ),
    CONSTRAINT user_cost_ledger_corrections_reference CHECK (
        (reason = 'charge' AND original_ledger_id IS NULL)
        OR
        (reason IN ('correction', 'refund') AND original_ledger_id IS NOT NULL)
    ),
    CONSTRAINT user_cost_ledger_pseudonymization_quad_consistent CHECK (
        (pseudonymized_at IS NULL AND pseudonymization_method IS NULL)
        OR
        (pseudonymized_at IS NOT NULL AND pseudonymization_method IS NOT NULL)
    ),
    CONSTRAINT user_cost_ledger_created_at_plausible CHECK (
        created_at_nanos > 1577836800000000000
    )
);

-- Billing dashboards hot paths
CREATE INDEX IF NOT EXISTS idx_user_cost_ledger_user_created
    ON user_cost_ledger (user_ref_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_cost_ledger_reality_created
    ON user_cost_ledger (reality_id, created_at DESC)
    WHERE reality_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_cost_ledger_session_created
    ON user_cost_ledger (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

-- Pseudonymization sweeper: find rows due
CREATE INDEX IF NOT EXISTS idx_user_cost_ledger_pseudonymization_due
    ON user_cost_ledger (created_at)
    WHERE pseudonymized_at IS NULL;

-- Forensic: corrections & refunds index
CREATE INDEX IF NOT EXISTS idx_user_cost_ledger_corrections
    ON user_cost_ledger (original_ledger_id, created_at DESC)
    WHERE reason IN ('correction', 'refund');

-- Append-only enforcement
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE user_cost_ledger FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE user_cost_ledger FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

-- Pseudonymization sweeper IS allowed UPDATE to set pseudonymized_at + method,
-- but is intentionally NOT granted here in V1; it ships as part of the
-- retention-worker (cycle 11). When that ships, grant a dedicated role
-- app_pseudonymization_role with UPDATE (pseudonymized_at, pseudonymization_method, user_ref_id).

COMMENT ON TABLE user_cost_ledger IS
    'L1.A-4 §4.1 — per-user LLM cost ledger. 7y retention; pseudonymize at 2y. Append-only; corrections via offset INSERTs.';
COMMENT ON COLUMN user_cost_ledger.cost_micro_usd IS
    'Cost in micro-USD (1 USD = 1_000_000); integer for exact accounting.';
COMMENT ON COLUMN user_cost_ledger.prompt_audit_id IS
    'Optional forensic link to prompt_audit row (S09 §12Y); body never stored, hash only.';
