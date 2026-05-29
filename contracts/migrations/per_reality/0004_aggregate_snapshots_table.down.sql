-- contracts/migrations/per_reality/0004_aggregate_snapshots_table.down.sql
--
-- Reverse cycle-9 L2.E migration. Dev / integration only.

BEGIN;

DROP TABLE IF EXISTS aggregate_snapshots CASCADE;

COMMIT;
