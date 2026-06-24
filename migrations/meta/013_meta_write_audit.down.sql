-- 013_meta_write_audit.down.sql — reverses 013_meta_write_audit.up.sql
-- Use only in dev/test; production audit data is regulated, not droppable.

DROP INDEX IF EXISTS idx_meta_write_audit_admin_only_partial;
DROP INDEX IF EXISTS idx_meta_write_audit_actor_created;
DROP INDEX IF EXISTS idx_meta_write_audit_table_created;

DROP TABLE IF EXISTS meta_write_audit;
