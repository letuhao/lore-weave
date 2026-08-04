-- contracts/migrations/per_reality/0017_drop_pc_npc_projections.up.sql
--
-- Drop the seven `pc_*` / `npc_*` projection tables shipped by 0006, and shrink
-- 0007's drift allowlist to match.
--
-- WHY — two independent reasons, both measured 2026-08-04:
--
--   1. NO PRODUCER. Every occurrence of `pc.created`, `pc.moved`, `pc.spawned`,
--      `npc.created`, `npc.relationship_changed` in the tree was a fixture, a
--      bench input or a test. No production code emitted one. Seven of the ten
--      L3.A tables could therefore only ever be rebuilt from events that nothing
--      wrote — machinery with no input, exercised only by its own tests.
--
--   2. VOCABULARY IN AN ENGINE TABLE. `pc_projection` declared `name`,
--      `stats JSONB` and `status IN ('active','inactive','deleted')` — hardcoded
--      game nouns. The actor-hub round (2026-08-02, `D-2`) sealed the opposite
--      rule: *the engine closes on MECHANISM; the manifest closes on
--      VOCABULARY. A hardcoded noun is a manifest that cannot grow.* `D-3` had
--      already killed this exact shape at three levels (`Actor.hp`, `VitalKind`,
--      `StatSlot::MaxHp`).
--
--      `stats` was the sharpest edge: written ONCE at `pc.created` as an opaque
--      pass-through of the event payload, read by nothing, with
--      `// TODO(cycle 17+ L4): pc.stats_changed` sitting beside it. The day
--      anyone implemented that TODO, an opaque blob would have become a second
--      SSOT for an actor's numbers — competing with the fold in
--      `crates/actor-hub`, which addresses quantities by ordinal and can explain
--      every one of them. The TODO was an invitation; this migration withdraws
--      it.
--
-- WHAT SURVIVES: `region_projection`, `world_kv_projection`,
-- `session_participants`, `canon_projection` — each with a real producer.
--
-- CONSEQUENCE, STATED RATHER THAN HIDDEN: `session.started` and `session.ended`
-- are produced but their ONLY projection target was `npc_session_memory_projection`.
-- They now project to nothing. That is a real gap and it is recorded here rather
-- than papered over with a table nobody writes.

DROP TABLE IF EXISTS npc_session_memory_embedding;
DROP TABLE IF EXISTS npc_pc_relationship_projection;
DROP TABLE IF EXISTS npc_session_memory_projection;
DROP TABLE IF EXISTS npc_projection;
DROP TABLE IF EXISTS pc_relationship_projection;
DROP TABLE IF EXISTS pc_inventory_projection;
DROP TABLE IF EXISTS pc_projection;

-- 0007's allowlist fenced `table_name` to the ten L3.A tables. It must shrink
-- with them, or the drift state can still name a table that no longer exists.
DELETE FROM projection_drift_state
 WHERE table_name IN (
     'pc_projection',
     'pc_inventory_projection',
     'pc_relationship_projection',
     'npc_projection',
     'npc_session_memory_projection',
     'npc_pc_relationship_projection',
     'npc_session_memory_embedding'
 );

ALTER TABLE projection_drift_state
    DROP CONSTRAINT IF EXISTS projection_drift_table_name_allowlist;

ALTER TABLE projection_drift_state
    ADD CONSTRAINT projection_drift_table_name_allowlist
    CHECK (table_name IN (
        'region_projection',
        'world_kv_projection',
        'session_participants'
    ));

COMMENT ON CONSTRAINT projection_drift_table_name_allowlist ON projection_drift_state IS
    'Cardinality fence, shrunk from ten to three by 0017 when the pc/npc projections were removed. A new table added in L4+ MUST extend this CHECK.';
