-- 027_meta_write_audit_scrub_version.down.sql
-- Rollback: drop the additive scrub_version column. Reverses 027 up.
ALTER TABLE meta_write_audit DROP COLUMN IF EXISTS scrub_version;
