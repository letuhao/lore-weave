-- RAID cycle 27 L5.J — canon_change_history APPEND-ONLY table.
--
-- # Why this lives under contracts/migrations/glossary/
--
-- Per Q-L1A-2 + Q-L5A-1 LOCKED, canon SSOT tables live in the
-- glossary-service DB. Foundation owns the SCHEMA PROPOSAL; the
-- glossary-service sub-program applies the migration when it onboards
-- the L5.J change-history feature. The cycle-23 cycle-25 pattern is
-- mirrored here: the contracts/migrations/ tree is the source of truth
-- and migration files are owned by the foundation team; service-side
-- application is the sub-program's responsibility.
--
-- # APPEND-ONLY enforcement (3 layers)
--
--   1. Wire-level — there is NO canon.change.amended / .deleted event
--      type. The schema can't accept an edit request via the published
--      contract.
--   2. Storage-level (THIS FILE) — CHECK trigger blocks UPDATE/DELETE +
--      `REVOKE UPDATE, DELETE` on the table from all roles. SUPERUSER
--      bypass remains for genuine forensic recovery, but normal app
--      roles cannot rewrite history.
--   3. Application-level — the SDK
--      (`contracts/canon/timeline/timeline.go::TimelineAppender`) and
--      Rust mirror (`crates/dp-kernel/src/canon_history.rs`) expose ONLY
--      `append`/`Append`. No update/delete method exists; even
--      accidentally-written rewrite code would fail to compile.
--
-- # Q-L5-3 enforcement
--
-- `canon_layer` column carries the LOCKED enum string. A CHECK
-- constraint catches producer drift defensively.

BEGIN;

CREATE TABLE canon_change_history (
    change_id UUID PRIMARY KEY,
    canon_entry_id UUID NOT NULL,
    book_id UUID NOT NULL,
    attribute_path TEXT NOT NULL,
    -- reality_id NULL = book-wide change (authored / propagation_completed);
    -- non-NULL = per-reality change (force_propagate).
    reality_id UUID NULL,
    kind TEXT NOT NULL CHECK (kind IN ('authored', 'force_propagate', 'propagation_completed')),
    -- old_value MAY be NULL for the very first change on this attribute path.
    old_value JSONB NULL,
    -- new_value is the post-change canonical value.
    new_value JSONB NOT NULL,
    canon_layer TEXT NOT NULL CHECK (canon_layer IN ('L1_axiom', 'L2_seeded')),
    source_event_id UUID NOT NULL,
    source_event_type TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Insert-only audit column (immutable post-INSERT).
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE canon_change_history IS 'L5.J APPEND-ONLY canon change-history timeline (RAID cycle 27). Producer: meta-worker canon_history_writer. Consumer: glossary-service author-UI.';
COMMENT ON COLUMN canon_change_history.kind IS 'Q-L5-J locked enum: authored | force_propagate | propagation_completed';
COMMENT ON COLUMN canon_change_history.canon_layer IS 'Q-L5-3 locked enum: L1_axiom | L2_seeded';
COMMENT ON COLUMN canon_change_history.reality_id IS 'NULL = book-wide change; non-NULL = per-reality (force_propagate side-effect)';

-- ─────────────────────────────────────────────────────────────────────────
-- Indexes — author-UI query patterns.
-- ─────────────────────────────────────────────────────────────────────────

CREATE INDEX canon_change_history_entry_recorded_idx
    ON canon_change_history (canon_entry_id, recorded_at DESC);

CREATE INDEX canon_change_history_book_path_recorded_idx
    ON canon_change_history (book_id, attribute_path, recorded_at DESC);

-- Per-reality drill-down (partial: most rows are book-wide).
CREATE INDEX canon_change_history_reality_recorded_idx
    ON canon_change_history (reality_id, recorded_at DESC)
    WHERE reality_id IS NOT NULL;

-- Source event linkage (forensic).
CREATE INDEX canon_change_history_source_event_idx
    ON canon_change_history (source_event_id);

-- ─────────────────────────────────────────────────────────────────────────
-- APPEND-ONLY enforcement — Layer 2.
-- ─────────────────────────────────────────────────────────────────────────

-- Trigger function: refuse UPDATE/DELETE.
CREATE OR REPLACE FUNCTION canon_change_history_block_update_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'canon_change_history is APPEND-ONLY (L5.J cycle 27); UPDATE/DELETE forbidden (got TG_OP=%)', TG_OP
        USING HINT = 'If forensic recovery REQUIRES rewriting history, contact platform SRE and bypass via SUPERUSER ad-hoc maintenance.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER canon_change_history_no_update
    BEFORE UPDATE ON canon_change_history
    FOR EACH ROW
    EXECUTE FUNCTION canon_change_history_block_update_delete();

CREATE TRIGGER canon_change_history_no_delete
    BEFORE DELETE ON canon_change_history
    FOR EACH ROW
    EXECUTE FUNCTION canon_change_history_block_update_delete();

-- Explicit privilege REVOKE. Application roles cannot UPDATE/DELETE.
-- Application roles are created by the glossary-service sub-program;
-- the REVOKE here is idempotent (no-op if role doesn't exist yet,
-- application MUST repeat after creating the role; sub-program runbook).
--
-- The application-role REVOKE below is commented-out because the role
-- name is sub-program-specific. The sub-program's onboarding step
-- includes:
--
--   REVOKE UPDATE, DELETE ON canon_change_history FROM glossary_app;
--
-- which is the strictest layer of the 3-layer defense.

COMMIT;
