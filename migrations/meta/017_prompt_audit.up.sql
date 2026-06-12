-- 017_prompt_audit.up.sql
-- L1.A-3 (cycle 4) — LLM prompt assembly audit; body is NEVER stored.
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §3.5
-- Owning kernel chunk: S09 §12Y
-- Retention: 90d hot / 2y cold (S08 §12X.4)
-- Append-only enforcement: REVOKE UPDATE/DELETE from app_service_role + app_admin_role
-- Written by: contracts/prompt/ internal (every AssemblePrompt() call) — for now
-- this surface is wrapped by contracts/meta/prompt_audit.go's PromptAudit interface,
-- which the prompt assembly library will adopt when it lands (cycle 21+).
--
-- Body-never-stored invariant:
--   - There is NO `body`, `prompt_text`, `assembled_text` column.
--   - prompt_context_hash is a SHA-256 over the assembled prompt; lets incident
--     replay confirm two reports point at the same exact assembly without
--     persisting the text. Template + version + the prompt assembler's
--     deterministic context retrieval lets ops reconstruct the prompt on
--     demand from the hash + audit_id (S09 §12Y).
--   - log.Sensitive() (cycle 32 logging library) enforces the same invariant
--     at the log-write layer.

CREATE TABLE IF NOT EXISTS prompt_audit (
    audit_id                UUID            PRIMARY KEY,

    -- Hash of the assembled prompt — replaces the body
    prompt_context_hash     BYTEA           NOT NULL,

    -- Template identity
    template_id             TEXT            NOT NULL,
    template_version        INTEGER         NOT NULL,

    -- Assembly intent + scope
    intent                  TEXT            NOT NULL,        -- e.g. 'turn_resolution' | 'npc_dialogue' | …
    actor_user_ref_id       UUID            NOT NULL,
    reality_id              UUID            NOT NULL,
    session_id              UUID            NULL,

    -- Cost projection at assembly time (refined by ledger when call completes)
    estimated_cost_usd      NUMERIC(12, 6)  NOT NULL DEFAULT 0,

    -- Refs the assembler chose NOT to include (capacity / consent / staleness)
    -- — JSONB array of {ref_id, reason}.
    rejected_refs           JSONB           NOT NULL DEFAULT '[]'::jsonb,

    created_at_nanos        BIGINT          NOT NULL,
    created_at              TIMESTAMPTZ     GENERATED ALWAYS AS
        (to_timestamp(created_at_nanos::double precision / 1e9)) STORED,

    CONSTRAINT prompt_audit_context_hash_sha256 CHECK (length(prompt_context_hash) = 32),
    CONSTRAINT prompt_audit_template_id_nonempty CHECK (length(template_id) > 0),
    CONSTRAINT prompt_audit_template_version_positive CHECK (template_version >= 1),
    CONSTRAINT prompt_audit_intent_nonempty CHECK (length(intent) > 0),
    CONSTRAINT prompt_audit_cost_nonneg CHECK (estimated_cost_usd >= 0),
    CONSTRAINT prompt_audit_created_at_nanos_plausible CHECK (
        created_at_nanos > 1577836800000000000
    )
);

-- L1A §3.5 indexes
CREATE INDEX IF NOT EXISTS idx_prompt_audit_user_created
    ON prompt_audit (actor_user_ref_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_prompt_audit_reality_created
    ON prompt_audit (reality_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_prompt_audit_template_created
    ON prompt_audit (template_id, template_version, created_at DESC);

-- Incident replay hot path: hash lookup
CREATE INDEX IF NOT EXISTS idx_prompt_audit_context_hash
    ON prompt_audit (prompt_context_hash);

-- Append-only — REVOKE UPDATE/DELETE on application roles.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE prompt_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE prompt_audit FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE prompt_audit IS
    'L1.A-3 — LLM prompt assembly audit. BODY IS NEVER STORED — only SHA-256 context hash + template id/version. Retention 90d hot / 2y cold. Append-only.';
COMMENT ON COLUMN prompt_audit.prompt_context_hash IS
    'SHA-256 of the assembled prompt text. Lets incident replay reconstruct via (hash + template + version + deterministic context retrieval). NEVER store the raw text.';
COMMENT ON COLUMN prompt_audit.rejected_refs IS
    'JSONB array of {ref_id, reason} — capacity/consent/staleness rejections during assembly. Used by capacity tuning and consent forensics.';
