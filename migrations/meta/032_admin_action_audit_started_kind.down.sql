-- 032 DOWN — restore the migration-015 result_kind enum (drop 'started').
-- NOTE: any rows with result_kind='started' must be removed before this is
-- applied (admin_action_audit is append-only; a manual cleanup is required —
-- down migrations on append-only audit tables are dev/test only).

ALTER TABLE admin_action_audit DROP CONSTRAINT IF EXISTS admin_action_audit_result_kind_enum;

ALTER TABLE admin_action_audit ADD CONSTRAINT admin_action_audit_result_kind_enum CHECK (
    result_kind IN ('success', 'dry_run', 'error')
);
