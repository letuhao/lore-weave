-- 023_deploy_audit.down.sql
DROP INDEX IF EXISTS idx_deploy_audit_class_started;
DROP INDEX IF EXISTS idx_deploy_audit_rolled_back;
DROP INDEX IF EXISTS idx_deploy_audit_started;
DROP TABLE IF EXISTS deploy_audit;
