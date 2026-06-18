-- contracts/migrations/per_reality/0001_initial.down.sql
--
-- Reverse the L1.C.5 SKELETON migration.
--
-- DOWN is intended for dev / integration test reset ONLY. Production
-- per-reality DBs are dropped by the deprovisioner (L1.C.2) wholesale —
-- there is never a use case for selectively rolling back a per-reality
-- DB schema in prod.
--
-- Order: drop in reverse dependency order. outbox FK-references events,
-- so drop outbox first.

BEGIN;

DROP TABLE IF EXISTS projection_meta;
DROP TABLE IF EXISTS snapshots;
DROP TABLE IF EXISTS outbox;
DROP TABLE IF EXISTS events;

COMMIT;
