-- 0030_encounter.down.sql
--
-- Reverting removes the closure boundary. Any fight in flight loses the record
-- of WHAT IT SNAPSHOTTED AT SITING, which is the one thing that made an in-place
-- fight replayable in an open world (R-7). The nodes survive and the combatants
-- survive; what is destroyed is the evidence that a bounded thing was happening
-- between them.
--
-- So this down is safe only while no encounter is `open`. It does not enforce
-- that -- a down that refused to run would strand an operator mid-rollback --
-- but the cost is stated here rather than discovered during one.

BEGIN;

DROP INDEX IF EXISTS encounter_by_site;
DROP TABLE IF EXISTS encounter;

COMMIT;
