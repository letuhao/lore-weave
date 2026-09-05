-- 0028_portal.down.sql
--
-- Reverting removes every way between places. The nodes survive, their kinds
-- survive, their places survive and their occupants survive -- so a revert
-- leaves a world that is fully described and completely disconnected: every
-- room exists, and no door does.
--
-- That is the honest cost. It is also recoverable in a way the other downs are
-- not: portals are authored edges, so the declaration that created them can
-- re-create them, whereas `0026`'s revert destroys authored `canon_ref` and
-- narrative drift that nothing else holds.

BEGIN;

DROP INDEX IF EXISTS portal_by_node_b;
DROP INDEX IF EXISTS portal_by_node_a;
DROP INDEX IF EXISTS portal_unordered_pair_uq;
DROP TABLE IF EXISTS portal;

COMMIT;
