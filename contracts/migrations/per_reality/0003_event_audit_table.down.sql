-- contracts/migrations/per_reality/0003_event_audit_table.down.sql
--
-- Reverse cycle-9 L2.B migration. Dev / integration only — production
-- per-reality DBs are dropped wholesale by the deprovisioner.

BEGIN;

DROP TABLE IF EXISTS event_audit CASCADE;

COMMIT;
