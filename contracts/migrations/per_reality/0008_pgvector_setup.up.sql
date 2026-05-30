-- contracts/migrations/per_reality/0008_pgvector_setup.up.sql
--
-- L3.I.1 + L3.I.2 — pgvector extension install + npc_session_memory_embedding
--                  ALTER COLUMN BYTEA → VECTOR(1536) + HNSW index.
--
-- RAID cycle 16 (L3.I finalizer). This is the **L3 layer-closing** migration:
-- the entire L3 snapshot/projection runtime (L3.A through L3.K minus L3.J) is
-- shipped after this lands.
--
-- ## Why this is its own migration (vs being part of 0006)
--
-- Cycle 13's 0006_projections.up.sql conditionally created the embedding
-- table either with `VECTOR(1536)` (when the pgvector extension was already
-- installed on the per-reality DB) or with a `BYTEA NOT NULL` placeholder
-- (when the extension was absent — typical of dev/test stacks that booted
-- before the foundation provisioner started installing the extension).
-- Cycle 13's table comment explicitly named "Cycle 14 L3.I" as the swap
-- point; cycle 14 was rerouted to L3.D/G/H so this cycle (16) inherits the
-- responsibility. The carry-forward chain is documented in CYCLE_LOG.md
-- (cycle 13 → cycle 16, two-step swap pattern).
--
-- ## What this migration does
--
-- Steps, in order, all idempotent:
--
--   1. `CREATE EXTENSION IF NOT EXISTS vector` — installs pgvector on the
--      per-reality DB. Requires the database image to ship the extension
--      (cycle 16 also extends infra/foundation-dev/docker-compose.yml to use
--      `pgvector/pgvector:pg16` for the foundation-dev postgres container).
--
--   2. **Idempotency probe**: if `npc_session_memory_embedding.embedding`
--      is ALREADY `VECTOR(1536)` (cycle-13 path A: extension was present at
--      table-create time) → SKIP the ALTER COLUMN. Just ensure the HNSW
--      index exists.
--
--   3. ALTER COLUMN path: if the column is `BYTEA` (cycle-13 path B: BYTEA
--      placeholder), perform the swap:
--      - DROP CONSTRAINT npc_embedding_bytea_dim_1536 (the BYTEA-shape check)
--      - ALTER COLUMN ... TYPE VECTOR(1536) USING NULL::VECTOR(1536)
--        rationale: cycle 13 ships at V1 pre-launch; no real rows exist; the
--        BYTEA placeholder rows (if any landed in dev experiments) cannot be
--        meaningfully converted to VECTOR (the cycle-13 comment notes they'd
--        be "8192-byte raw fp32 vector" but no test fixture writes them).
--        Setting all existing rows to NULL is acceptable — the embedding
--        queue (cycle 16 DPS 1) backfills on next memory event.
--      - ALTER COLUMN ... DROP NOT NULL (NULL = "pending embedding compute")
--
--   4. CREATE INDEX IF NOT EXISTS for the HNSW index. The cycle-13 migration
--      attempted this only inside the `vector` extension branch; cycle 16
--      makes it unconditional (the extension is now guaranteed present).
--      Parameters: `m = 16, ef_construction = 64` — pgvector documented
--      defaults that balance build time vs query recall for ~100K vector
--      working sets per reality (per L3.I.2 acceptance: < 10ms P99 query).
--
-- ## LOCKED decisions consumed
--
-- - **Q-L3I-1** (OPEN_QUESTIONS_LOCKED §5 line 77): dim=1536 hard-coded V1.
--   V2+ will introduce per-table per-dimension flexibility — DO NOT widen
--   to 768 or 3072 in V1.
-- - **Q-L3-1** (line 73): embedding worker placement = V1 in world-service
--   async queue. THIS migration prepares the SCHEMA; the queue itself lives
--   in `services/world-service/src/embedding_queue/`. V1+30d extraction to
--   a dedicated `embedding-worker` service is an explicit out-of-scope item
--   (DEFERRED).
--
-- ## Partition note
--
-- The `npc_session_memory_embedding` table is NOT partitioned (cycle 13
-- created it with PK `(npc_id, session_id)`, no `PARTITION BY`). Cycle 9's
-- monthly partitioning applies only to `events` and `event_audit` (RANGE
-- on `recorded_at`). Therefore the HNSW index here is a SINGLE GLOBAL
-- index, not a per-partition concern. If a future cycle introduces
-- partitioning on this table, the per-partition HNSW requirement noted in
-- the cycle-16 brief carryforward becomes live and a follow-up migration
-- will be needed.
--
-- ## Down migration
--
-- 0008_pgvector_setup.down.sql DROPs the HNSW index but does NOT drop the
-- extension (other tables may consume `vector` in the future). It also
-- does NOT reverse the ALTER COLUMN — there is no safe way to convert
-- VECTOR back to BYTEA without losing data, and the cycle-13 table-create
-- already supports both shapes at apply-time.

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 1 — Install pgvector extension.
-- ───────────────────────────────────────────────────────────────────────────
-- Idempotent: IF NOT EXISTS is the Postgres-recommended form.
CREATE EXTENSION IF NOT EXISTS vector;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 2 + 3 — Conditional ALTER COLUMN.
-- ───────────────────────────────────────────────────────────────────────────
DO $alter_embedding$
DECLARE
    col_type TEXT;
    bytea_constraint_exists BOOLEAN;
BEGIN
    -- Discover current type. Returns NULL if the table is absent (would be
    -- a setup error — cycle 13's 0006 should always have run first; we let
    -- the DO block exit cleanly in that case).
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO col_type
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
     WHERE c.relname = 'npc_session_memory_embedding'
       AND a.attname = 'embedding'
       AND NOT a.attisdropped;

    IF col_type IS NULL THEN
        RAISE NOTICE 'npc_session_memory_embedding.embedding column not found — '
                     'cycle 13 0006_projections.up.sql must run before this migration';
        RETURN;
    END IF;

    IF col_type = 'vector(1536)' THEN
        -- Cycle-13 path A: extension was present, table already shipped with
        -- the correct VECTOR(1536) type — but 0006 created it `NOT NULL`. The
        -- embedding-queue design (L3.I.3) REQUIRES the column to be nullable:
        -- the projection INSERTs a row with `embedding = NULL` ("pending
        -- compute") and the async queue backfills the real vector. Path B
        -- below already does this DROP NOT NULL after its type swap; path A
        -- must do it too, or the NULL-sentinel contract is broken on every
        -- fresh pgvector DB (the projection insert + the queue's
        -- `UPDATE … WHERE embedding IS NULL` would never work). Idempotent.
        RAISE NOTICE 'npc_session_memory_embedding.embedding already VECTOR(1536) — ensuring nullable';
        EXECUTE 'ALTER TABLE npc_session_memory_embedding '
             || 'ALTER COLUMN embedding DROP NOT NULL';
    ELSIF col_type = 'bytea' THEN
        -- Cycle-13 path B: BYTEA placeholder. Perform the swap.
        RAISE NOTICE 'npc_session_memory_embedding.embedding is BYTEA — performing ALTER COLUMN to VECTOR(1536)';

        -- 3a. Drop the BYTEA-shape CHECK constraint (only present on path B).
        SELECT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'npc_embedding_bytea_dim_1536'
        ) INTO bytea_constraint_exists;
        IF bytea_constraint_exists THEN
            EXECUTE 'ALTER TABLE npc_session_memory_embedding '
                 || 'DROP CONSTRAINT npc_embedding_bytea_dim_1536';
        END IF;

        -- 3b. Swap the column type. Cycle 16 ships pre-launch (no real rows
        --     in production); any BYTEA placeholder rows from dev/test
        --     experiments are set to NULL (the embedding queue refills on
        --     next memory event — see services/world-service/src/embedding_queue).
        EXECUTE 'ALTER TABLE npc_session_memory_embedding '
             || 'ALTER COLUMN embedding TYPE VECTOR(1536) USING NULL::VECTOR(1536)';

        -- 3c. NULL is now a valid sentinel for "pending embedding compute".
        --     The queue worker writes a real VECTOR(1536) once the BYOK
        --     provider returns. This matches the L3.I.3 contract.
        EXECUTE 'ALTER TABLE npc_session_memory_embedding '
             || 'ALTER COLUMN embedding DROP NOT NULL';
    ELSE
        -- Unknown shape — fail loud rather than silently leaving the column
        -- in an inconsistent state. SRE will see this in the migration log.
        RAISE EXCEPTION 'npc_session_memory_embedding.embedding has unexpected type: % '
                        '(expected vector(1536) or bytea)', col_type;
    END IF;
END
$alter_embedding$;

-- ───────────────────────────────────────────────────────────────────────────
-- Step 4 — HNSW index.
-- ───────────────────────────────────────────────────────────────────────────
-- Idempotent: IF NOT EXISTS. Cycle 13 may have created this already inside
-- the vector branch of 0006; the IF NOT EXISTS makes a re-run safe.
--
-- Parameters chosen per L3.I.2 + pgvector documentation:
--   m = 16              — graph degree; pgvector default
--   ef_construction = 64 — build-time candidate list; pgvector default
-- Query-time `ef_search` is set per-session by the embedding queue caller
-- (default 40; tunable for recall/latency trade-offs).
--
-- vector_cosine_ops is correct for normalized embedding vectors (OpenAI
-- text-embedding-ada-002 + most modern embedding models return unit-norm
-- vectors; cosine distance == 1 - dot product in that case).
CREATE INDEX IF NOT EXISTS npc_embedding_hnsw_idx
    ON npc_session_memory_embedding
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ───────────────────────────────────────────────────────────────────────────
-- Step 5 — Table comment refresh (records the L3.I completion).
-- ───────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE npc_session_memory_embedding IS
    'L3.A.7 + L3.I — NPC session memory embedding (pgvector). '
    'Q-L3I-1 dim=1536 LOCKED V1. Cycle 16 (L3.I) installed pgvector + '
    'HNSW(m=16,ef_construction=64) + made embedding column NULL-able as '
    '"pending compute" sentinel. Backfilled async by '
    'services/world-service/src/embedding_queue (Q-L3-1 V1 placement).';

COMMIT;
