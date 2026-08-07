-- contracts/migrations/per_reality/0018_drop_region_session_world_kv_projections.up.sql
--
-- Drop the last three producer-less projections, and repoint the drift
-- allowlist at `canon_projection` — the only projection in this schema that
-- anything actually writes.
--
-- WHY — the same measurement that produced `0017`, run again with a hole closed.
--
--   `0017` removed seven `pc_*`/`npc_*` tables because no production code emitted
--   their events. It left four. One day later `orphan-model-gate` was taught that
--   Rust keeps its unit tests INSIDE the `src/` file, not under `/tests/` — and the
--   answer changed:
--
--     canon_projection      canon.entry.*        PRODUCED  (meta-worker canon_writer)
--     world_kv_projection   world.kv_set         not produced — the only occurrence
--                                                outside an excluded path was a
--                                                `#[cfg(test)]` fixture in
--                                                crates/rebuilder/src/lib.rs:542
--     world_kv_projection   world.kv_unset       not produced
--     region_projection     region.*             not produced
--     session_participants  session.participant_*  not produced
--
--   So three of the four survivors were in exactly the state the seven dropped
--   ones were in, and a test had been vouching for the fourth.
--
-- AND THE PO'S REASON, which is the load-bearing one: `session_participants` was
-- built on the OLD world/map feature. That feature is being redesigned and the new
-- version is not designed yet; there is no mechanism to spawn an actor anywhere at
-- all. A membership table for sessions nobody can join, keyed by a
-- `participant_type` fenced to `('pc','npc')` — game vocabulary in an engine
-- table, the exact `D-2` shape `0017` removed — is not a foundation to build on.
-- `region_projection` is the same feature's other half.
--
-- WHAT SURVIVES: `canon_projection`, with a real producer, and it now enters the
-- drift allowlist. It never was in it — 0007 fenced the ten L3.A tables and canon
-- arrived later in 0009 — so the ONE projection worth drift-checking was the one
-- the drift machinery could not name. That asymmetry outlived every table it was
-- written for.
--
-- CONSEQUENCE, STATED RATHER THAN HIDDEN: `world.kv_set` is emitted by nothing,
-- so nothing regresses. But if a later slice lands a world-KV writer it must
-- author the projection forward — this migration is not a pause, it is a removal.

BEGIN;

DROP TABLE IF EXISTS session_participants;
DROP TABLE IF EXISTS region_projection;
DROP TABLE IF EXISTS world_kv_projection;

DELETE FROM projection_drift_state
 WHERE table_name IN (
     'session_participants',
     'region_projection',
     'world_kv_projection'
 );

-- The allowlist cannot simply shrink to nothing: `table_name IN ()` is not valid
-- SQL, and a CHECK that admits nothing would make the drift table unwritable.
-- It repoints instead, onto the single projection that has an input.
ALTER TABLE projection_drift_state
    DROP CONSTRAINT IF EXISTS projection_drift_table_name_allowlist;

ALTER TABLE projection_drift_state
    ADD CONSTRAINT projection_drift_table_name_allowlist
    CHECK (table_name IN (
        'canon_projection'
    ));

COMMENT ON CONSTRAINT projection_drift_table_name_allowlist ON projection_drift_state IS
    'Cardinality fence. Ten (0007) -> three (0017) -> one (0018), as each projection with no producer was removed. A new table added in L4+ MUST extend this CHECK.';

COMMIT;
