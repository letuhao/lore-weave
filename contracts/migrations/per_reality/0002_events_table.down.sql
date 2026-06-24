-- contracts/migrations/per_reality/0002_events_table.down.sql
--
-- Reverse cycle-9 L2.A migration. Dev / integration only — production
-- per-reality DBs are dropped wholesale by the deprovisioner, never
-- selectively rolled back (per L1.C deprovisioner contract).
--
-- Drops the production-shape partitioned `events` table along with all
-- its monthly partitions (cascade).
--
-- We DO NOT re-create the cycle-5 skeleton here. Re-applying 0001_initial
-- (idempotent) is the documented recovery path.

BEGIN;

-- Drop child partitions first via CASCADE to detach cleanly.
DROP TABLE IF EXISTS events CASCADE;

COMMIT;
