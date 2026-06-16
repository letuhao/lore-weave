-- 006_archive_verification_log.down.sql
-- WARNING: drops 7y compliance audit. Only legitimate in dev teardown.
DROP TABLE IF EXISTS archive_verification_log CASCADE;
