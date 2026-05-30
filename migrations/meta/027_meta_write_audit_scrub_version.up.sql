-- 027_meta_write_audit_scrub_version.up.sql
-- 076 D-PII-PRODUCTION Slice A — record which scrubber ruleset redacted a
-- meta_write_audit row's before/after/reason, so retroactive re-scrub jobs can
-- target rows by ruleset version.
--
-- Additive + idempotent (ADD COLUMN IF NOT EXISTS). DEFAULT '' keeps every
-- pre-existing row + any audit-insert path that omits the column valid (e.g. the
-- out-of-band meta-worker pgwrite writer until it is updated).
--
-- Semantics (NOT a PII-presence flag): scrub_version names the ruleset that
-- RAN over the structured values, regardless of whether any leaf actually
-- matched a PII pattern. '' = no scrubber was configured for that write.
--
-- Lossy-diff caveat: when set, before_values/after_values are PII-redacted via
-- the 7-pattern regex applied to string leaves (security-first, over-redaction
-- acceptable per contracts/meta/scrubber.go) — the audit diff is intentionally
-- lossy (a UUID/nanos string may redact to a placeholder). Consumers must not
-- assume the scrubbed values are byte-faithful to the persisted row.

ALTER TABLE meta_write_audit
    ADD COLUMN IF NOT EXISTS scrub_version TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN meta_write_audit.scrub_version IS
    '076 Slice A — scrubber ruleset id (e.g. regex-v1) applied to before/after/reason; '''' = no scrubber configured. Marks ruleset for retroactive re-scrub, NOT PII presence.';
