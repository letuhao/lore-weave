-- contracts/migrations/per_reality/0006_projections.down.sql
--
-- Reverse L3.A 10 projection tables migration.
-- Idempotent (DROP TABLE IF EXISTS).

BEGIN;

DROP TABLE IF EXISTS session_participants;
DROP TABLE IF EXISTS world_kv_projection;
DROP TABLE IF EXISTS region_projection;
DROP TABLE IF EXISTS npc_session_memory_embedding;
DROP TABLE IF EXISTS npc_pc_relationship_projection;
DROP TABLE IF EXISTS npc_session_memory_projection;
DROP TABLE IF EXISTS npc_projection;
DROP TABLE IF EXISTS pc_relationship_projection;
DROP TABLE IF EXISTS pc_inventory_projection;
DROP TABLE IF EXISTS pc_projection;

COMMIT;
