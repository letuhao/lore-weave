-- 022_feature_flags.up.sql
-- L1.A-4 (cycle 7) — feature flag store (SR05 L4).
-- Source: L1A_meta_tables.md §6.2; owning kernel chunk: SR05 §12AH.4
--
-- @pii_sensitivity: low (flag name + owner uuid; targets are opaque ids)
-- @retention_class: operational
-- @retention_hot: indefinite
-- @erasure_method: hard_delete_on_retire
-- @legal_basis: legitimate_interest

CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name                TEXT            PRIMARY KEY,
    description              TEXT            NOT NULL,
    default_enabled          BOOLEAN         NOT NULL DEFAULT FALSE,
    target_scope             TEXT            NOT NULL DEFAULT 'global',  -- global|reality|user|cohort|tier
    enabled_realities        UUID[]          NOT NULL DEFAULT ARRAY[]::UUID[],
    enabled_users            UUID[]          NOT NULL DEFAULT ARRAY[]::UUID[],
    enabled_cohorts          INT[]           NOT NULL DEFAULT ARRAY[]::INT[],
    enabled_tiers            TEXT[]          NOT NULL DEFAULT ARRAY[]::TEXT[],
    owner                    UUID            NOT NULL,
    expires_at               TIMESTAMPTZ     NULL,
    last_toggled_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    created_at               TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT feature_flags_name_nonempty CHECK (length(flag_name) > 0),
    CONSTRAINT feature_flags_target_scope_enum CHECK (
        target_scope IN ('global', 'reality', 'user', 'cohort', 'tier')
    ),
    CONSTRAINT feature_flags_expires_after_created CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

CREATE INDEX IF NOT EXISTS idx_feature_flags_owner
    ON feature_flags (owner);

CREATE INDEX IF NOT EXISTS idx_feature_flags_expiring
    ON feature_flags (expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feature_flags_default_enabled
    ON feature_flags (default_enabled, target_scope);

COMMENT ON TABLE feature_flags IS
    'L1.A-4 §6.2 / SR05 — runtime feature flags. Operational retention; SR05 ages stale flags.';
