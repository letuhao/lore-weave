-- 032 (cycle-4 / D-ADMINAUDIT-INPROGRESS): add 'started' to the
-- admin_action_audit result_kind enum so a destructive command that crashes /
-- is killed AFTER the framework's Before hook but BEFORE its After/Failure hook
-- still leaves a durable forensic trace.
--
-- PII/retention classification (S08 §12X.3/§12X.4; pii-classify-lint). ALTER on
-- the existing admin_action_audit table — classification unchanged from 015.
-- @pii_sensitivity: low (command metadata + params_hash; never raw PII values)
-- @retention_class: admin_audit
-- @retention_hot: 2y
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest
--
-- WHY: migration 015 shipped result_kind IN ('success','dry_run','error') —
-- outcome-only. The framework emits a 'started' Action at Before() but the
-- MetaWriteSink skipped it, so a command panicking between Before and the
-- terminal hook produced NO audit row at all. The admin-cli MetaWriteSink now
-- persists the 'started' row for tier-1-destructive / tier-2-griefing commands
-- (the forensic case); this migration relaxes the CHECK to accept it.
--
-- A 'started' row is NON-error, so the existing
-- admin_action_audit_error_kind_has_scrubber CHECK already requires its
-- error_detail_raw_hash to be NULL (no scrubber quad) — no change needed there.
--
-- Safety: purely additive to the allowed set (no existing row uses 'started');
-- non-breaking. Applies to the test/meta DB only.

ALTER TABLE admin_action_audit DROP CONSTRAINT IF EXISTS admin_action_audit_result_kind_enum;

ALTER TABLE admin_action_audit ADD CONSTRAINT admin_action_audit_result_kind_enum CHECK (
    result_kind IN ('started', 'success', 'dry_run', 'error')
);
