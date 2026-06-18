-- 010_pii_kek.down.sql
-- WARNING: drops PII KEK envelope. Only legitimate in dev teardown.
-- Production erasure path is set destroyed_at + KMS ScheduleKeyDeletion, NOT DROP TABLE.
DROP TABLE IF EXISTS pii_kek CASCADE;
