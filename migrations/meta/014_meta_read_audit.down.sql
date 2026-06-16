-- 014_meta_read_audit.down.sql — reverses 014_meta_read_audit.up.sql

DROP INDEX IF EXISTS idx_meta_read_audit_high_result_partial;
DROP INDEX IF EXISTS idx_meta_read_audit_query_type_created;
DROP INDEX IF EXISTS idx_meta_read_audit_actor_created;

DROP TABLE IF EXISTS meta_read_audit;
