-- contracts/migrations/per_reality/0016_events_ruleset_digest.down.sql
--
-- Reverses 0016: drops the RLS-A13 ruleset pin column. Metadata-only on the
-- partitioned table; IF EXISTS for idempotent re-apply.
--
-- NOTE: dropping this column does not merely lose a field — it makes every
-- event written after 0016 unpinnable again, so a replay can no longer detect
-- that the rules moved. Reverse only to unblock a migration, never as cleanup.

BEGIN;

ALTER TABLE events DROP COLUMN IF EXISTS ruleset_digest;

COMMIT;
