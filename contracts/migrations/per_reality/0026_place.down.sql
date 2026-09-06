-- 0026_place.down.sql
--
-- Reverting removes every node's MEANING. The nodes survive, their kinds
-- survive, and the things standing in them survive -- so a revert leaves a
-- world that is structurally intact and narratively mute: an actor can be in a
-- Domain, and nothing can say whether it is a tavern or a cave.
--
-- That is the honest cost rather than a defect. `canon_ref` and
-- `narrative_drift` are authored content and go with it, which is the real
-- reason this down is worth reading twice before running.
--
-- `map_layout_kind_uq` is dropped too, because `0026` added it and a down that
-- left it behind would make the up non-idempotent in the other direction: the
-- ALTER guards itself with DROP CONSTRAINT IF EXISTS, but leaving a constraint
-- that belongs to a reverted migration is exactly the kind of residue that
-- makes a later chain replay disagree with a fresh one.

BEGIN;

DROP INDEX IF EXISTS place_by_type;
DROP TABLE IF EXISTS place;

ALTER TABLE IF EXISTS map_layout
    DROP CONSTRAINT IF EXISTS map_layout_kind_uq;

COMMIT;
