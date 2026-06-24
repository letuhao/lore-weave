-- 009_pii_registry.down.sql
-- WARNING: drops user PII registry. Only legitimate in dev teardown.
-- Production erasure path is crypto-shred (set pii_kek.destroyed_at), NOT DROP TABLE.
DROP TABLE IF EXISTS pii_registry CASCADE;
