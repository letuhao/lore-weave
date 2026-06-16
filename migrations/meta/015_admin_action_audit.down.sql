-- 015_admin_action_audit.down.sql — reverses 015_admin_action_audit.up.sql

DROP INDEX IF EXISTS idx_admin_action_audit_errors_partial;
DROP INDEX IF EXISTS idx_admin_action_audit_reality_created;
DROP INDEX IF EXISTS idx_admin_action_audit_actor_created;

DROP TABLE IF EXISTS admin_action_audit;
