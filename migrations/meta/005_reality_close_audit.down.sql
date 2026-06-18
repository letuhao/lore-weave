-- 005_reality_close_audit.down.sql
-- WARNING: drops 7y compliance audit. Only legitimate in dev teardown.
DROP TABLE IF EXISTS reality_close_audit CASCADE;
