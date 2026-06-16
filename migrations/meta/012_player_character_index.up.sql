-- 012_player_character_index.up.sql
-- L1.A-2 (cycle 3) — user-facing PC index (which user owns which PCs across realities).
-- Source: docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md §2.4
-- Owning kernel chunks: 04_player_character §A (PC-A1..A3) + S04 §12T.3 CHECK
-- Retention: Operational (until status='deleted' + GC)
-- Written by: world-service via MetaWrite()
-- Read by: world-service (PC lookup), gateway-BFF (dashboard),
--          other PCs' prompt assembly (cross-user reads = sensitive)
--
-- Sensitive-read enumeration:
--   Non-owner SELECT on this table is tagged id="player_index_cross_user"
--   in contracts/meta/meta-sensitive-read-paths.yml — every such read writes
--   a meta_read_audit row.
--
-- Risk: identity-manipulation attack (alter rows → impersonation, cross-user
-- data leak). Defense: S4 §12T.6 sensitive-read audit on non-owner queries,
-- plus REVOKE on app roles below.

CREATE TABLE IF NOT EXISTS player_character_index (
    pc_index_id        UUID            PRIMARY KEY,

    user_ref_id        UUID            NOT NULL,
    reality_id         UUID            NOT NULL,
    pc_id              UUID            NOT NULL,  -- per-reality PC identifier (FK lives in per-reality DB)

    pc_name            TEXT            NOT NULL,

    -- Status enum per L1A §2.4
    -- active            — in active play
    -- offline           — logged out / not actively playing
    -- hidden            — owner has hidden from dashboard (still owns)
    -- npc_converted     — PC was promoted to permanent NPC; owner relinquished
    -- deceased          — in-game death (final IF permadeath reality rules)
    -- deleted           — owner-initiated delete; eligible for GC after retention
    status             TEXT            NOT NULL,

    created_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    last_seen_at       TIMESTAMPTZ     NULL,
    updated_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT player_character_index_status_enum CHECK (
        status IN (
            'active',
            'offline',
            'hidden',
            'npc_converted',
            'deceased',
            'deleted'
        )
    ),
    CONSTRAINT player_character_index_pc_name_format CHECK (
        length(pc_name) BETWEEN 1 AND 64
    ),
    -- Same (reality, pc) MUST be unique — one row per per-reality PC ever
    CONSTRAINT player_character_index_reality_pc_unique UNIQUE (reality_id, pc_id)
);

-- Hot lookup: "PCs owned by user" (dashboard query — owner-only, not sensitive)
CREATE INDEX IF NOT EXISTS idx_player_character_index_user_status
    ON player_character_index (user_ref_id, status, last_seen_at DESC);

-- Reality-scoped lookup (world-service uses)
CREATE INDEX IF NOT EXISTS idx_player_character_index_reality
    ON player_character_index (reality_id, status);

-- Active-only partial index for "online players in reality"
CREATE INDEX IF NOT EXISTS idx_player_character_index_active_partial
    ON player_character_index (reality_id, user_ref_id)
    WHERE status = 'active';

-- updated_at touch trigger
CREATE OR REPLACE FUNCTION player_character_index_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS player_character_index_touch_updated_at_trg ON player_character_index;
CREATE TRIGGER player_character_index_touch_updated_at_trg
    BEFORE UPDATE ON player_character_index
    FOR EACH ROW EXECUTE FUNCTION player_character_index_touch_updated_at();

-- DELETE is allowed (owner-initiated PC deletion is real), but BULK
-- exports / cross-user reads must go through ReadSensitive path. CI lint
-- detects direct SELECTs outside the library helper (L1.K, cycle later).

COMMENT ON TABLE player_character_index IS
    'L1.A-2 — cross-reality PC index. Cross-user reads = sensitive (player_index_cross_user audit path).';
COMMENT ON COLUMN player_character_index.user_ref_id IS
    'Opaque user identifier. Cross-user lookups (caller != owner) MUST go through ReadSensitive with id="player_index_cross_user".';
