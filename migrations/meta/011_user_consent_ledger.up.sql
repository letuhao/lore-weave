-- 011_user_consent_ledger.up.sql
-- L1.A-2 (cycle 3) — GDPR Art. 6 legal-basis tracking.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §2.3
-- Owning kernel chunk: S08 §12X.9
-- Retention: consent_ledger tier — retain while account active + 2y (S08 §12X.4)
-- Written by: auth-service, world-service (book authorship requires consent),
--             admin-cli via MetaWrite()
-- Read by: every service before processing consent-gated data (cached 5min per §12X.11)
--
-- Q-L5H-1 (LOCKED 2026-05-29): force-propagate consent timeout = 24h,
-- default-to-consent on no-response. This table records the grant/revoke
-- ledger; the 24h force-propagate timer enforcement ships in L5.H (later cycle).
--
-- Scope enum V1 (per §2.3 layer plan):
--   core_service           — required to use the platform at all
--   byok_telemetry         — anonymized provider-call metrics for ops
--   derivative_analytics   — aggregated cross-user trend analytics
--   ip_derivative_use      — user's created IP usable in platform-wide features
--   cross_reality_aggregation — user's stats aggregated across realities
--   marketing_comms        — email/notification opt-in
--
-- PK is (user_ref_id, consent_scope, scope_version) — every policy-version
-- update creates a NEW row; old rows stay for audit.

CREATE TABLE IF NOT EXISTS user_consent_ledger (
    user_ref_id        UUID            NOT NULL,
    consent_scope      TEXT            NOT NULL,
    scope_version      TEXT            NOT NULL,

    -- Legal basis under GDPR Art. 6 (which lawful basis applies)
    -- 'consent'              — Art. 6(1)(a) — explicit opt-in (default for V1)
    -- 'contract'             — Art. 6(1)(b) — necessary for service contract
    -- 'legal_obligation'     — Art. 6(1)(c) — e.g. billing/tax records
    -- 'legitimate_interest'  — Art. 6(1)(f) — must document balancing test
    legal_basis        TEXT            NOT NULL DEFAULT 'consent',

    -- Grant + revoke timestamps. revoked_at NULL = still granted.
    granted_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    revoked_at         TIMESTAMPTZ     NULL,

    -- Scrubbed context (PII-free) — e.g., {"ip_country": "DE", "ua_family": "mobile-app/v3"}
    -- Free-text PII never lands here; library scrubber gates ingress.
    grant_context      JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- Revocation reason free-text (admin/user-initiated; scrubbed)
    revoke_reason      TEXT            NULL,

    PRIMARY KEY (user_ref_id, consent_scope, scope_version),

    CONSTRAINT user_consent_ledger_scope_enum CHECK (
        consent_scope IN (
            'core_service',
            'byok_telemetry',
            'derivative_analytics',
            'ip_derivative_use',
            'cross_reality_aggregation',
            'marketing_comms'
        )
    ),
    CONSTRAINT user_consent_ledger_legal_basis_enum CHECK (
        legal_basis IN (
            'consent',
            'contract',
            'legal_obligation',
            'legitimate_interest'
        )
    ),
    CONSTRAINT user_consent_ledger_scope_version_nonempty CHECK (
        length(scope_version) BETWEEN 1 AND 64
    ),
    CONSTRAINT user_consent_ledger_revoke_order CHECK (
        revoked_at IS NULL OR revoked_at >= granted_at
    )
);

-- Hot lookup: "is consent for (user, scope) currently granted?"
CREATE INDEX IF NOT EXISTS idx_user_consent_ledger_active
    ON user_consent_ledger (user_ref_id, consent_scope)
    WHERE revoked_at IS NULL;

-- All scopes for a user (consent dashboard view)
CREATE INDEX IF NOT EXISTS idx_user_consent_ledger_user
    ON user_consent_ledger (user_ref_id, granted_at DESC);

-- Revocation audit lookups
CREATE INDEX IF NOT EXISTS idx_user_consent_ledger_revoked
    ON user_consent_ledger (revoked_at DESC)
    WHERE revoked_at IS NOT NULL;

-- Append-only-ish: rows can be UPDATEd to set revoked_at/revoke_reason
-- exactly once. Library enforces via MetaWrite ExpectedBefore (revoked_at IS NULL).
-- We REVOKE DELETE to prevent silent erasure of consent history (audit need).
DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE user_consent_ledger FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE DELETE ON TABLE user_consent_ledger FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE user_consent_ledger IS
    'L1.A-2 — GDPR Art. 6 consent ledger. PK (user, scope, scope_version). Revoke sets revoked_at; rows never DELETEd.';
COMMENT ON COLUMN user_consent_ledger.legal_basis IS
    'GDPR Art. 6 lawful-basis enum. Defaults to consent (opt-in); contract/legal_obligation/legitimate_interest are admin-asserted.';
COMMENT ON COLUMN user_consent_ledger.grant_context IS
    'Scrubbed grant-time context (no raw PII). Library scrubber enforces ingress hygiene (S08 §12X.5).';
