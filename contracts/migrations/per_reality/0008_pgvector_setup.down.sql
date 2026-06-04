-- contracts/migrations/per_reality/0008_pgvector_setup.down.sql
--
-- Reverse L3.I pgvector setup. Idempotent.
--
-- We do NOT drop the `vector` extension (other future tables may rely on it,
-- and `DROP EXTENSION vector CASCADE` would silently remove any column that
-- depends on it). We also do NOT reverse the ALTER COLUMN — there is no
-- lossless way to convert VECTOR(1536) back to BYTEA(6144), and the
-- cycle-13 0006_projections.up.sql already conditionally creates the table
-- with either type, so a fresh `down → up` cycle will not be broken.
--
-- What this down DOES:
--   - DROPs the HNSW index (the only object this migration uniquely owns).

BEGIN;

DROP INDEX IF EXISTS npc_embedding_hnsw_idx;

COMMIT;
