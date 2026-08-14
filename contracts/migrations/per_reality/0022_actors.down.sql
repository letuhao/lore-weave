-- 0022_actors.down.sql
--
-- Reverting removes the mapping between the platform's `actor_id UUID` and the
-- island's `EntityId(u64)`. Every `actor_control_binding` row in the META
-- database survives — it lives in a different database and this file cannot
-- reach it — and each one is left pointing at a uuid nothing resolves, which is
-- the exact state `S-9` describes and this migration exists to end.
--
-- That is the honest cost of the revert, not a defect in it: a `down` that also
-- deleted the bindings would be a per-reality migration reaching across the
-- control-plane boundary, which is a worse thing than a dangling pointer.

DROP INDEX IF EXISTS actors_by_entity_id;
DROP TABLE IF EXISTS actors;
