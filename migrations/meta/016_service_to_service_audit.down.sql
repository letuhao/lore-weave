-- 016_service_to_service_audit.down.sql — reverses 016_service_to_service_audit.up.sql

DROP INDEX IF EXISTS idx_s2s_audit_failed_partial;
DROP INDEX IF EXISTS idx_s2s_audit_user_ref_partial;
DROP INDEX IF EXISTS idx_s2s_audit_caller_created;
DROP INDEX IF EXISTS idx_s2s_audit_callee_rpc_created;

DROP TABLE IF EXISTS service_to_service_audit;
