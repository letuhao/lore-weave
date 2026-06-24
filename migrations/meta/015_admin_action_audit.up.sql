-- 015_admin_action_audit.up.sql
-- L1.A-3 (cycle 4) — command-level admin audit; complements meta_write_audit
-- (which logs the data-level write, this logs the command intent).
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §3.3
-- Owning kernel chunk: R13 §12L.3
-- Retention: 2y default; 7y if classed as regulated activity (per-command config)
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role
-- Written by: admin-cli via MetaWrite() (admin-cli ships cycle 36; this table
-- precedes the writer so the audit surface is available when commands start landing).
--
-- Free-text safety (S08 §12X.5):
--   `error_detail` MUST flow through the scrubber. We persist:
--     - error_detail_raw_hash  — SHA-256 of the raw text (forensic match key)
--     - error_detail_scrubbed  — scrubber-rewritten text (PII-free)
--     - scrub_version          — scrubber rule set version applied
--     - scrubbed_at            — scrub timestamp (TIMESTAMPTZ)
--   The raw text NEVER lands in the audit table — only its hash for incident
--   correlation. Pattern is enforced by contracts/meta/scrubber.go's interface
--   shape (no raw-string accessor).

CREATE TABLE IF NOT EXISTS admin_action_audit (
    audit_id                  UUID            PRIMARY KEY,

    -- Command identity
    command_name              TEXT            NOT NULL,
    command_version           TEXT            NOT NULL,

    -- Actor + scope
    actor_id                  UUID            NOT NULL,
    actor_type                TEXT            NOT NULL DEFAULT 'admin',
    reality_id                UUID            NULL,            -- null for global commands

    -- Parameters (scrubbed JSONB — caller responsible for not jamming raw PII here)
    parameters                JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- Result envelope — discriminated union via result_kind
    result_kind               TEXT            NOT NULL,        -- success|dry_run|error
    result                    JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- Error detail — STORED IN SCRUBBED FORM ONLY (see header)
    error_detail_raw_hash     BYTEA           NULL,            -- SHA-256 (32 bytes) or NULL on non-error
    error_detail_scrubbed     TEXT            NULL,
    scrub_version             TEXT            NULL,
    scrubbed_at               TIMESTAMPTZ     NULL,

    created_at_nanos          BIGINT          NOT NULL,
    created_at                TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT admin_action_audit_result_kind_enum CHECK (
        result_kind IN ('success', 'dry_run', 'error')
    ),
    CONSTRAINT admin_action_audit_actor_type_enum CHECK (
        actor_type IN ('admin', 'system', 'service', 'retention_cron', 'owner', 'cron')
    ),
    CONSTRAINT admin_action_audit_command_name_nonempty CHECK (length(command_name) > 0),
    CONSTRAINT admin_action_audit_command_version_nonempty CHECK (length(command_version) > 0),
    CONSTRAINT admin_action_audit_created_at_nanos_plausible CHECK (
        created_at_nanos > 1577836800000000000
    ),
    -- All four scrubber fields are populated together or all NULL.
    CONSTRAINT admin_action_audit_scrubber_quad_consistent CHECK (
        (error_detail_raw_hash IS NULL  AND error_detail_scrubbed IS NULL  AND
         scrub_version IS NULL          AND scrubbed_at IS NULL)
        OR
        (error_detail_raw_hash IS NOT NULL AND error_detail_scrubbed IS NOT NULL AND
         scrub_version IS NOT NULL         AND scrubbed_at IS NOT NULL)
    ),
    -- Hash must be SHA-256 (32 bytes) when present.
    CONSTRAINT admin_action_audit_error_hash_sha256 CHECK (
        error_detail_raw_hash IS NULL OR length(error_detail_raw_hash) = 32
    ),
    -- Error result_kind requires scrubber populated; non-error requires NULL.
    CONSTRAINT admin_action_audit_error_kind_has_scrubber CHECK (
        (result_kind = 'error' AND error_detail_raw_hash IS NOT NULL)
        OR
        (result_kind <> 'error' AND error_detail_raw_hash IS NULL)
    )
);

-- L1A §3.3 indexes
CREATE INDEX IF NOT EXISTS idx_admin_action_audit_actor_created
    ON admin_action_audit (actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_action_audit_reality_created
    ON admin_action_audit (reality_id, created_at DESC)
    WHERE reality_id IS NOT NULL;

-- Forensic: "errors in last N min" hot path
CREATE INDEX IF NOT EXISTS idx_admin_action_audit_errors_partial
    ON admin_action_audit (created_at DESC, command_name)
    WHERE result_kind = 'error';

-- Append-only — REVOKE UPDATE/DELETE on application roles.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE admin_action_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE admin_action_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE admin_action_audit IS
    'L1.A-3 — command-level admin audit. Append-only. Default retention 2y; 7y for regulated commands. error_detail flows through scrubber (S08 §12X.5).';
COMMENT ON COLUMN admin_action_audit.error_detail_raw_hash IS
    'SHA-256 of original error text; lets forensic search match without retaining raw PII.';
COMMENT ON COLUMN admin_action_audit.error_detail_scrubbed IS
    'Scrubber-rewritten error text (PII-redacted). Always paired with scrub_version + scrubbed_at.';
