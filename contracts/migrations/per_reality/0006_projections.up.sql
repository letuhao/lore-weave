-- contracts/migrations/per_reality/0006_projections.up.sql
--
-- L3.A — 10 projection tables (single migration; tightly coupled by FKs +
--        co-rebuilt as a unit per L3 plan §2 L3.A).
--
-- LOCKED decisions consumed:
--   * Q-L3-4 (OPEN_QUESTIONS_LOCKED §5): VerificationMeta cols on EVERY
--     projection table. Two related sets of metadata:
--       (a) per-write VerificationMeta from the Projection trait
--           (`event_id`, `aggregate_version`, `applied_at`) — stamped on
--           every UPSERT by the projection runner. Lets the L3.E integrity
--           sampler ask "which event last touched this row?" without
--           cross-referencing the events table.
--       (b) per-table verification high-water (`last_verified_event_version`,
--           `last_verified_at`) — written by the L3.E daily / L3.F monthly
--           integrity checker. Lets the L3.J alert system fire on stale
--           verification (`last_verified_at > 7d`).
--     Set (a) is the cycle-12 ProjectionRunner contract; set (b) is L3.K
--     migration material (cycle 13 DPS 2 ships a separate light state table
--     for drift; THIS migration adds the per-row HWM cols inline because
--     they sit on the SAME row).
--   * Q-L3-5 (§5): NO V2 blue-green migration scaffolding. Tables are
--     created with the V1 freeze-rebuild assumption (L3.G) — schema
--     additions in future cycles use `ALTER TABLE ... ADD COLUMN IF NOT
--     EXISTS` + reality-frozen status (cycle 14+ L3.G work).
--   * Q-L3I-1 (§5): npc_session_memory_embedding uses `VECTOR(1536)` hard-
--     coded V1 (OpenAI text-embedding-ada-002). pgvector extension itself
--     lands in cycle 14 L3.I migration 0007_pgvector_setup; THIS migration
--     gates the embedding table creation on `vector` extension presence
--     (CREATE TABLE … VECTOR(1536) requires the extension already
--     installed). For cycle-13 verify purposes the table is created
--     CONDITIONALLY — if `vector` is missing we use a `BYTEA` placeholder
--     stub and document the cycle-14 swap. This keeps the migration
--     idempotent and unblocked for foundation-staging DBs that haven't yet
--     installed pgvector.
--   * Q-L3B-1 (§5): Projection trait returns `Vec<ProjectionUpdate>` — the
--     `pc.said` event fan-out path requires `npc_session_memory_projection`
--     and `pc_projection` to BOTH carry VerificationMeta cols so the same
--     event_id can be traced across both tables.
--
-- Cross-cycle contracts:
--   * Cycle 9 (L2.A): `events.event_id`, `events.aggregate_version`,
--     `events.recorded_at` are the source of `event_id` /
--     `aggregate_version` / `applied_at` on every projection row. The
--     projection runtime (cycle 12 `crates/dp-kernel/src/projection.rs`)
--     calls `VerificationMeta::from_envelope(env)` to populate these.
--   * Cycle 12 (L3.B): `ProjectionUpdate::{Insert, Update, Delete,
--     Tombstone}` variants — the per-aggregate projection crates added in
--     this cycle (`crates/projections/...`) implement the `Projection`
--     trait against these tables.
--   * Cycle 14 (L3.E/I): integrity checker writes `last_verified_*` cols;
--     pgvector setup migration runs BEFORE this one in cycle 14 ordering
--     so the cycle-13 placeholder column is replaced by a real
--     `VECTOR(1536)` via `ALTER TABLE ... ALTER COLUMN`.
--
-- ⚠️  DO NOT add domain-specific tables here. This migration ships the L3.A
--    canonical 10 projection tables ONLY. Domain-specific projections (e.g.
--    quest_journal, faction_standings) land in L4-L7 domain cycles.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- Shared VerificationMeta column macros (documentation; no actual macros in
-- standard Postgres SQL — these comments enumerate the consistent shape).
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Every projection table below carries this canonical 5-col block:
--
--   event_id                     UUID NOT NULL,           -- Q-L3-4 (a)
--   aggregate_version            BIGINT NOT NULL,         -- Q-L3-4 (a)
--   applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Q-L3-4 (a)
--   last_verified_event_version  BIGINT,                  -- Q-L3-4 (b)
--   last_verified_at             TIMESTAMPTZ,             -- Q-L3-4 (b)
--
-- Plus one BTree index per table on (applied_at DESC) for the L3.E sampler
-- "find me rows touched in the last X" query, and one on (event_id) for
-- drift-investigation lookups (Q-L3-4 acceptance).
--
-- ───────────────────────────────────────────────────────────────────────────

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.1  pc_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pc_projection (
    pc_id                        UUID NOT NULL PRIMARY KEY,
    user_id                      UUID NOT NULL,
    name                         TEXT NOT NULL,
    current_region_id            UUID,
    status                       TEXT NOT NULL DEFAULT 'active',
    stats                        JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_event_version           BIGINT NOT NULL DEFAULT 0,
    -- VerificationMeta (Q-L3-4 set a)
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Integrity HWM (Q-L3-4 set b; written by L3.E/F)
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    CONSTRAINT pc_projection_stats_is_object CHECK (jsonb_typeof(stats) = 'object'),
    CONSTRAINT pc_projection_status_valid    CHECK (status IN ('active', 'inactive', 'deleted'))
);
CREATE INDEX IF NOT EXISTS pc_projection_applied_at_idx  ON pc_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS pc_projection_event_id_idx    ON pc_projection (event_id);
CREATE INDEX IF NOT EXISTS pc_projection_user_id_idx     ON pc_projection (user_id);
CREATE INDEX IF NOT EXISTS pc_projection_region_idx      ON pc_projection (current_region_id) WHERE current_region_id IS NOT NULL;
COMMENT ON TABLE pc_projection IS 'L3.A.1 — PC primary state. VerificationMeta (event_id/aggregate_version/applied_at) per Q-L3-4. Source: pc.* events via PcProjection.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.2  pc_inventory_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pc_inventory_projection (
    pc_id                        UUID NOT NULL,
    item_code                    TEXT NOT NULL,
    quantity                     INTEGER NOT NULL DEFAULT 0,
    metadata                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- MV5 P5 origin reality (V1 nullable per L3 plan L3.A.2 spec).
    origin_reality_id            UUID,
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    PRIMARY KEY (pc_id, item_code),
    CONSTRAINT pc_inventory_metadata_is_object CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT pc_inventory_qty_nonneg         CHECK (quantity >= 0)
);
CREATE INDEX IF NOT EXISTS pc_inventory_applied_at_idx ON pc_inventory_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS pc_inventory_event_id_idx   ON pc_inventory_projection (event_id);
COMMENT ON TABLE pc_inventory_projection IS 'L3.A.2 — Per-PC items + MV5 origin reality. VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.3  pc_relationship_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pc_relationship_projection (
    pc_id                        UUID NOT NULL,
    other_entity_type            TEXT NOT NULL,
    other_entity_id              UUID NOT NULL,
    score                        INTEGER NOT NULL DEFAULT 0,
    labels                       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    PRIMARY KEY (pc_id, other_entity_type, other_entity_id),
    CONSTRAINT pc_rel_other_type_valid CHECK (other_entity_type IN ('pc', 'npc'))
);
CREATE INDEX IF NOT EXISTS pc_rel_applied_at_idx ON pc_relationship_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS pc_rel_event_id_idx   ON pc_relationship_projection (event_id);
COMMENT ON TABLE pc_relationship_projection IS 'L3.A.3 — PC↔PC, PC↔NPC scores. VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.4  npc_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS npc_projection (
    npc_id                       UUID NOT NULL PRIMARY KEY,
    -- Read-only ref to glossary entity (canonical NPC archetype). NOT a FK
    -- because glossary lives in a separate service DB (cross-DB references
    -- prohibited per I7).
    glossary_entity_id           UUID,
    current_region_id            UUID,
    mood                         TEXT,
    -- Author-locked core beliefs (immutable; LLM cannot mutate).
    core_beliefs                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- LLM-drifted flexible state (mood, recent actions, surface beliefs).
    flexible_state               JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_event_version           BIGINT NOT NULL DEFAULT 0,
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    CONSTRAINT npc_projection_core_is_object   CHECK (jsonb_typeof(core_beliefs)   = 'object'),
    CONSTRAINT npc_projection_flex_is_object   CHECK (jsonb_typeof(flexible_state) = 'object')
);
CREATE INDEX IF NOT EXISTS npc_projection_applied_at_idx  ON npc_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS npc_projection_event_id_idx    ON npc_projection (event_id);
CREATE INDEX IF NOT EXISTS npc_projection_region_idx      ON npc_projection (current_region_id) WHERE current_region_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS npc_projection_glossary_idx    ON npc_projection (glossary_entity_id) WHERE glossary_entity_id IS NOT NULL;
COMMENT ON TABLE npc_projection IS 'L3.A.4 — NPC primary state (mood, beliefs, flexible state). Two-layer per chunk §12S.2: core_beliefs author-locked vs flexible_state LLM-drifted. VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.5  npc_session_memory_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS npc_session_memory_projection (
    npc_id                       UUID NOT NULL,
    session_id                   UUID NOT NULL,
    reality_id                   UUID NOT NULL,
    -- Synthetic per-session aggregate id (uuidv5 of npc_id+session_id per
    -- §12S.2.3). Pre-computed for cheap idempotency lookup.
    aggregate_id                 UUID NOT NULL,
    summary                      TEXT NOT NULL DEFAULT '',
    facts                        JSONB NOT NULL DEFAULT '{}'::jsonb,
    session_started_at           TIMESTAMPTZ NOT NULL,
    session_ended_at             TIMESTAMPTZ,
    interaction_count            INTEGER NOT NULL DEFAULT 0,
    archive_status               TEXT NOT NULL DEFAULT 'active',
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    PRIMARY KEY (npc_id, session_id),
    CONSTRAINT npc_session_facts_is_object    CHECK (jsonb_typeof(facts) = 'object'),
    CONSTRAINT npc_session_archive_valid      CHECK (archive_status IN ('active', 'faded', 'summary_only', 'archived')),
    CONSTRAINT npc_session_interactions_nonneg CHECK (interaction_count >= 0)
);
CREATE INDEX IF NOT EXISTS npc_session_applied_at_idx ON npc_session_memory_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS npc_session_event_id_idx   ON npc_session_memory_projection (event_id);
CREATE INDEX IF NOT EXISTS npc_session_archive_idx    ON npc_session_memory_projection (archive_status) WHERE archive_status <> 'active';
CREATE INDEX IF NOT EXISTS npc_session_aggregate_idx  ON npc_session_memory_projection (aggregate_id);
COMMENT ON TABLE npc_session_memory_projection IS 'L3.A.5 — Per-session NPC memory (S2 capability-scoped). aggregate_id is uuidv5(npc_id, session_id) per §12S.2.3. VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.6  npc_pc_relationship_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS npc_pc_relationship_projection (
    npc_id                       UUID NOT NULL,
    other_entity_id              UUID NOT NULL,
    other_entity_type            TEXT NOT NULL,
    reality_id                   UUID NOT NULL,
    trust_level                  INTEGER NOT NULL DEFAULT 0,
    familiarity_count            INTEGER NOT NULL DEFAULT 0,
    last_session_id              UUID,
    relationship_labels          TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    PRIMARY KEY (npc_id, other_entity_id),
    CONSTRAINT npc_rel_other_type_valid CHECK (other_entity_type IN ('pc', 'npc')),
    CONSTRAINT npc_rel_trust_range      CHECK (trust_level BETWEEN -100 AND 100),
    CONSTRAINT npc_rel_familiarity_nonneg CHECK (familiarity_count >= 0)
);
CREATE INDEX IF NOT EXISTS npc_pc_rel_applied_at_idx ON npc_pc_relationship_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS npc_pc_rel_event_id_idx   ON npc_pc_relationship_projection (event_id);
CREATE INDEX IF NOT EXISTS npc_pc_rel_reality_idx    ON npc_pc_relationship_projection (reality_id);
COMMENT ON TABLE npc_pc_relationship_projection IS 'L3.A.6 — NPC↔PC durable relationship (trust, familiarity). VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.7  npc_session_memory_embedding (pgvector or BYTEA fallback)
-- ───────────────────────────────────────────────────────────────────────────
-- Q-L3I-1: dim 1536 hard-coded V1 (OpenAI text-embedding-ada-002).
-- pgvector extension itself ships in cycle 14 L3.I (0007_pgvector_setup).
-- THIS migration creates the table using `VECTOR(1536)` when the extension
-- is already installed, OR a `BYTEA` placeholder (16-byte hash prefix sized
-- BYTEA for unit-test stack support) when it is not. Cycle-14 migration
-- ALTERs the column to `VECTOR(1536)` if it landed as BYTEA.
DO $vector_create$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        EXECUTE $exec$
            CREATE TABLE IF NOT EXISTS npc_session_memory_embedding (
                npc_id                       UUID NOT NULL,
                session_id                   UUID NOT NULL,
                embedding                    VECTOR(1536) NOT NULL,
                content_hash                 TEXT NOT NULL,
                event_id                     UUID NOT NULL,
                aggregate_version            BIGINT NOT NULL,
                applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_verified_event_version  BIGINT,
                last_verified_at             TIMESTAMPTZ,
                PRIMARY KEY (npc_id, session_id)
            )
        $exec$;
        -- HNSW index per L3.I.2 (vector_cosine_ops). Cycle 14 may tune
        -- m / ef_construction; foundation defaults are pgvector's defaults.
        BEGIN
            EXECUTE 'CREATE INDEX IF NOT EXISTS npc_embedding_hnsw_idx ON npc_session_memory_embedding USING hnsw (embedding vector_cosine_ops)';
        EXCEPTION WHEN feature_not_supported OR undefined_object THEN
            RAISE NOTICE 'npc_session_memory_embedding: HNSW unavailable (pgvector < 0.5.0?); skipping index';
        END;
    ELSE
        EXECUTE $exec$
            CREATE TABLE IF NOT EXISTS npc_session_memory_embedding (
                npc_id                       UUID NOT NULL,
                session_id                   UUID NOT NULL,
                -- Cycle-14 L3.I will ALTER COLUMN to VECTOR(1536). Until
                -- then BYTEA holds an 8192-byte raw fp32 vector
                -- representation (1536 * 4 bytes). Q-L3I-1 dim 1536 LOCKED.
                embedding                    BYTEA NOT NULL,
                content_hash                 TEXT NOT NULL,
                event_id                     UUID NOT NULL,
                aggregate_version            BIGINT NOT NULL,
                applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_verified_event_version  BIGINT,
                last_verified_at             TIMESTAMPTZ,
                PRIMARY KEY (npc_id, session_id),
                CONSTRAINT npc_embedding_bytea_dim_1536
                    CHECK (octet_length(embedding) = 1536 * 4)
            )
        $exec$;
        RAISE NOTICE 'npc_session_memory_embedding: created with BYTEA placeholder. Cycle-14 0007_pgvector_setup will ALTER to VECTOR(1536).';
    END IF;
END
$vector_create$;
CREATE INDEX IF NOT EXISTS npc_embedding_applied_at_idx ON npc_session_memory_embedding (applied_at DESC);
CREATE INDEX IF NOT EXISTS npc_embedding_event_id_idx   ON npc_session_memory_embedding (event_id);
COMMENT ON TABLE npc_session_memory_embedding IS 'L3.A.7 — pgvector embedding for NPC session memory retrieval. Q-L3I-1 dim=1536 LOCKED V1. Cycle 14 L3.I installs pgvector extension + swaps BYTEA placeholder for VECTOR(1536) when needed.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.8  region_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS region_projection (
    region_id                    UUID NOT NULL PRIMARY KEY,
    code                         TEXT NOT NULL,
    display_name                 TEXT NOT NULL,
    description                  TEXT NOT NULL DEFAULT '',
    parent_region_id             UUID,
    exits                        JSONB NOT NULL DEFAULT '[]'::jsonb,
    floor_items                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    ambient_state                JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_event_version           BIGINT NOT NULL DEFAULT 0,
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    CONSTRAINT region_exits_is_array       CHECK (jsonb_typeof(exits)         = 'array'),
    CONSTRAINT region_floor_items_is_array CHECK (jsonb_typeof(floor_items)   = 'array'),
    CONSTRAINT region_ambient_is_object    CHECK (jsonb_typeof(ambient_state) = 'object')
);
CREATE INDEX IF NOT EXISTS region_projection_applied_at_idx ON region_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS region_projection_event_id_idx   ON region_projection (event_id);
CREATE INDEX IF NOT EXISTS region_projection_code_idx       ON region_projection (code);
CREATE INDEX IF NOT EXISTS region_projection_parent_idx     ON region_projection (parent_region_id) WHERE parent_region_id IS NOT NULL;
COMMENT ON TABLE region_projection IS 'L3.A.8 — Region state + exits + floor items + ambient state. VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.9  world_kv_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS world_kv_projection (
    key                          TEXT NOT NULL PRIMARY KEY,
    value                        JSONB NOT NULL DEFAULT 'null'::jsonb,
    last_event_version           BIGINT NOT NULL DEFAULT 0,
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS world_kv_applied_at_idx ON world_kv_projection (applied_at DESC);
CREATE INDEX IF NOT EXISTS world_kv_event_id_idx   ON world_kv_projection (event_id);
COMMENT ON TABLE world_kv_projection IS 'L3.A.9 — Free-form world key-value (quest flags, global events). VerificationMeta per Q-L3-4.';

-- ───────────────────────────────────────────────────────────────────────────
-- L3.A.10  session_participants
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_participants (
    session_id                   UUID NOT NULL,
    participant_type             TEXT NOT NULL,
    participant_id               UUID NOT NULL,
    reality_id                   UUID NOT NULL,
    joined_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- left_at NULL = participant is currently active in this session.
    left_at                      TIMESTAMPTZ,
    -- VerificationMeta
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,
    PRIMARY KEY (session_id, participant_type, participant_id),
    CONSTRAINT session_participants_type_valid CHECK (participant_type IN ('pc', 'npc')),
    CONSTRAINT session_participants_window     CHECK (left_at IS NULL OR left_at >= joined_at)
);
CREATE INDEX IF NOT EXISTS session_participants_applied_at_idx ON session_participants (applied_at DESC);
CREATE INDEX IF NOT EXISTS session_participants_event_id_idx   ON session_participants (event_id);
CREATE INDEX IF NOT EXISTS session_participants_active_idx     ON session_participants (session_id) WHERE left_at IS NULL;
CREATE INDEX IF NOT EXISTS session_participants_reality_idx    ON session_participants (reality_id);
COMMENT ON TABLE session_participants IS 'L3.A.10 — Capability-scoped session membership (S2 foundation). left_at IS NULL = active. VerificationMeta per Q-L3-4.';

COMMIT;
