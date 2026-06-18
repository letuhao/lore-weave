-- 004_lifecycle_transition_audit.down.sql
-- WARNING: drops 5y append-only audit. Only legitimate in dev teardown.
DROP TABLE IF EXISTS lifecycle_transition_audit CASCADE;
