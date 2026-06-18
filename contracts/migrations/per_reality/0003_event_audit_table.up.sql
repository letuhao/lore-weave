-- contracts/migrations/per_reality/0003_event_audit_table.up.sql
--
-- L2.B.1 — `event_audit` table.
--
-- High-volume forensic ledger for LLM-touching events (R01 §12A.1). Lives
-- per-reality, partitioned monthly, lz4-compressed. Separate table from
-- `events` so the high-churn audit rows can be pruned aggressively (30d
-- non-flagged, 90d flagged) WITHOUT affecting the long-retention canonical
-- event log.
--
-- LOCKED decisions consumed:
--   * Q-L2-3 (OPEN_QUESTIONS_LOCKED §4): linkage to `events` is a UUID pointer
--     `event_ref`, NOT a FK. Rationale: events are archived/dropped per L2.J
--     partition lifecycle independently of audit rows; a FK would break after
--     archival. The reverse pointer (`events.audit_ref`) is also a UUID, not
--     an FK, for the same reason.
--   * Q-L1D-1: this migration is `breaking: true` in
--     `contracts/migrations/manifest.yaml`; orchestrator routes through canary.
--
-- Partitioning:
--   * PARTITION BY RANGE (recorded_at) — monthly window, same as `events`.
--     Initial partition `event_audit_p_<YYYY_MM>` created at migration time.
--   * `scripts/per-reality-partition-manager.sh` (cycle 9 DPS 1) creates
--     next-month partition 7d in advance.
--   * `scripts/event-audit-retention-cron.sh` (cycle 9 DPS 2) prunes per
--     `flagged` + age.
--
-- Compression: lz4 on `prompt_text`, `response_text`, `metadata` (the JSONB
-- + TEXT heavy hitters). Falls back to pglz on older Postgres.
--
-- ⚠️ Body-never-stored contract (cycle 4): for prompt audits, the OpenPII
-- crypto-shred semantics apply via `pii_kek`. This table stores the
-- llm_prompt_audit body fields only when policy permits; redaction happens
-- in the Go-side helper, not the SQL layer.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────
-- event_audit — high-volume forensic ledger
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS event_audit (
    -- Identity
    audit_id           UUID NOT NULL,
    -- Tenant + event reference (UUID pointer; not FK — Q-L2-3)
    reality_id         UUID NOT NULL,
    event_ref          UUID,                   -- pointer to events.event_id; may be NULL for audit-only rows
    -- Event identification (kept duplicated from events to survive archival)
    event_type         TEXT NOT NULL,
    event_version      INTEGER NOT NULL DEFAULT 1,
    aggregate_type     TEXT NOT NULL,
    aggregate_id       TEXT NOT NULL,
    -- LLM forensic payload (NULL when audit is non-LLM)
    actor_type         TEXT NOT NULL DEFAULT 'system',  -- system|user|service|llm
    actor_id           TEXT,
    prompt_hash        TEXT,                   -- SHA-256 of the prompt sent to LLM
    prompt_text        TEXT,                   -- gated by privacy policy; may be NULL
    response_text      TEXT,                   -- gated by privacy policy; may be NULL
    model_ref          TEXT,                   -- provider:model:version
    -- Flagging (90d retention) vs non-flagged (30d retention) per R01 §12A.3
    flagged            BOOLEAN NOT NULL DEFAULT FALSE,
    flag_reason        TEXT,                   -- nullable; populated when flagged=true
    -- Free-form context
    metadata           JSONB,
    -- Timestamps
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Constraints
    CONSTRAINT event_audit_metadata_is_object_or_null
        CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object'),
    CONSTRAINT event_audit_actor_type_enum
        CHECK (actor_type IN ('system', 'user', 'service', 'llm')),
    CONSTRAINT event_audit_event_version_pos
        CHECK (event_version >= 1),
    CONSTRAINT event_audit_flag_reason_required_when_flagged
        CHECK ((flagged = FALSE) OR (flag_reason IS NOT NULL AND flag_reason <> '')),
    PRIMARY KEY (reality_id, audit_id, recorded_at)
) PARTITION BY RANGE (recorded_at);

DO $$
BEGIN
    BEGIN
        ALTER TABLE event_audit ALTER COLUMN prompt_text  SET COMPRESSION lz4;
        ALTER TABLE event_audit ALTER COLUMN response_text SET COMPRESSION lz4;
        ALTER TABLE event_audit ALTER COLUMN metadata     SET COMPRESSION lz4;
    EXCEPTION WHEN feature_not_supported OR undefined_object THEN
        RAISE NOTICE 'event_audit: lz4 compression unavailable; using default pglz';
    END;
END$$;

COMMENT ON TABLE  event_audit IS
    'L2.B forensic audit ledger. Monthly partitions. event_ref is UUID pointer (NOT FK) per Q-L2-3.';
COMMENT ON COLUMN event_audit.event_ref IS
    'UUID pointer to events.event_id (NOT FK — events archived independently). NULL OK for audit-only entries.';
COMMENT ON COLUMN event_audit.flagged IS
    'When TRUE: row kept 90d per R01 §12A.3. When FALSE: pruned at 30d by event-audit-retention-cron.sh.';
COMMENT ON COLUMN event_audit.prompt_text IS
    'LLM prompt text — gated by privacy policy in Go-side helper (cycle 4 body-never-stored contract enforces NULL by default).';

-- ─────────────────────────────────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────────────────────────────────
--
-- Index strategy:
--   1. PK already covers ordered scans per reality+audit.
--   2. Reverse-pointer lookup (events.event_id → event_audit row):
--      (event_ref) WHERE event_ref IS NOT NULL.
--   3. Flagged audit forensics (rare query, but cardinality is small):
--      (reality_id, recorded_at) WHERE flagged.
--   4. Retention cron's daily scan: (reality_id, recorded_at) — picks rows
--      older than threshold for the per-flagged class.

CREATE INDEX IF NOT EXISTS event_audit_event_ref_idx
    ON event_audit (event_ref)
    WHERE event_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS event_audit_flagged_idx
    ON event_audit (reality_id, recorded_at)
    WHERE flagged;

CREATE INDEX IF NOT EXISTS event_audit_recorded_idx
    ON event_audit (reality_id, recorded_at);

-- ─────────────────────────────────────────────────────────────────────────
-- Initial partition (current month).
-- ─────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    p_start DATE := date_trunc('month', NOW())::DATE;
    p_end   DATE := (date_trunc('month', NOW()) + INTERVAL '1 month')::DATE;
    p_name  TEXT := format('event_audit_p_%s', to_char(p_start, 'YYYY_MM'));
    sql_text TEXT;
BEGIN
    sql_text := format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF event_audit
             FOR VALUES FROM (%L) TO (%L);',
        p_name, p_start, p_end
    );
    EXECUTE sql_text;
END$$;

COMMIT;
