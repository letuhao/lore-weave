-- 040_tier_policy.down.sql — reverse of 040.
--
-- `tier_capability` first: it holds the FK, so dropping `tier_policy` before it
-- fails. Order is the mirror of the up, which is the only order that works.
--
-- No CASCADE, deliberately. A CASCADE here would silently take anything a later
-- migration attached to these tables, and a down-migration that removes more
-- than its up added is how a rollback becomes a data-loss event.

BEGIN;

DROP INDEX IF EXISTS tier_capability_live_idx;
DROP TABLE IF EXISTS tier_capability;
DROP TABLE IF EXISTS tier_policy;

COMMIT;
