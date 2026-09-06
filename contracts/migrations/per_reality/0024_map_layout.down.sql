-- 0024_map_layout.down.sql
--
-- Reverting drops every node's KIND, and with it the only thing that makes the
-- `channels` tree a SPACE rather than a tree. The tree survives -- `channels` is
-- a different table and this file does not touch it -- so a revert leaves a
-- structurally valid hierarchy that no containment rule can be evaluated
-- against: `allowed(parent.kind, child.kind)` has no left or right operand.
--
-- That is the honest cost of the revert rather than a defect in it. The
-- alternative -- a down that also removed the channels those layouts described
-- -- would delete authored world structure to undo a schema change, which is a
-- far worse thing than a tree the engine cannot type.
--
-- ON DELETE CASCADE on the FK means the reverse direction is already handled:
-- dropping a channel takes its layout with it. Nothing here needs to.

BEGIN;

DROP INDEX IF EXISTS map_layout_by_kind;
DROP TABLE IF EXISTS map_layout;

COMMIT;
