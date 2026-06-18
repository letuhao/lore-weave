-- contracts/migrations/per_reality/0009_canon_projection.up.sql
--
-- L5.D — Per-reality `canon_projection` table.
--
-- The 11th projection table on the per-reality DB (cycle 13 L3.A shipped 10
-- + cycle 23 L5.D adds canon_projection). PURPOSE: cached per-reality view of
-- the authored canon (L1_axiom + L2_seeded layers) so prompt assembly hot
-- path (`[WORLD_CANON]` section per S09 §12Y.4) reads from per-reality DB
-- without RPC to glossary-service every turn. Writers: meta-worker only (I7
-- sole-writer invariant) — populated by canon.entry.* event consumers
-- (cycle 24+ L5.B).
--
-- LOCKED decisions consumed:
--   * Q-L1A-2 (OPEN_QUESTIONS_LOCKED §3 line 23): canon TABLES
--     (canon_entries, canonization_audit, book_authorship, canon_change_log)
--     live in glossary-service's `glossary` DB — NOT meta. This per-reality
--     `canon_projection` is a DIFFERENT concern: it is the per-reality CACHE
--     of authored canon, written by meta-worker via the cross-reality fan-
--     out flow (cycle 10 xreality protocol + cycle 24+ L5.B consumer +
--     this migration's schema). The relationship:
--
--       glossary DB.canon_entries   (SSOT, authored by glossary-service)
--                ↓ outbox emission (Q-L5A-1 sub-program)
--                ↓ publisher fan-out (xreality.book.canon.updated)
--                ↓ meta-worker consumer (cycle 24+ L5.B)
--                ↓ per-reality DB.canon_projection (THIS TABLE)
--
--   * Q-L5-3 (OPEN_QUESTIONS_LOCKED §7 line 107): SINGLE TABLE with a
--     `canon_layer` column carrying `L1_axiom` or `L2_seeded`. NOT
--     separate canon_l1_projection / canon_l2_projection tables — that
--     would multiply the meta-worker writer paths and make L3-override
--     joins ugly. Single table + CHECK constraint on the enum.
--
--   * Q-L3-4 (carry-forward from cycle 13 L3.A): EVERY projection table
--     carries the canonical 5-col VerificationMeta block:
--       event_id                     UUID NOT NULL
--       aggregate_version            BIGINT NOT NULL
--       applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
--       last_verified_event_version  BIGINT
--       last_verified_at             TIMESTAMPTZ
--     + index on (applied_at DESC) for the L3.E sampler "find me rows
--     touched in the last X" query
--     + index on (event_id) for drift-investigation lookups.
--
--   * Q-L5-1 (line 105): Canon cache invalidation = event-driven primary
--     (this table's `last_synced_at` is updated by meta-worker on every
--     write; L5.E cache compares timestamp on `last_synced_at` change to
--     invalidate); 60s TTL fallback applies at the in-process cache
--     (L5.E.1) — NOT at this storage layer.
--
-- Multi-verse cascade contract (00_overview MV5 + L5_inbound_canon §1):
--
--   - `cascaded_from_reality_id` NULL → this row was sourced from THIS
--     reality's own subscription to a canon book (publisher → meta-worker
--     write).
--   - `cascaded_from_reality_id` = <ancestor reality_id> → this row was
--     populated by cascade read-through from an ancestor reality
--     (multiverse §3: child realities inherit parent canon until an L3
--     event overrides).
--   - `overridden_by_l3_event_id` NULL → this canon entry is currently
--     authoritative for this reality (no L3 event has overridden it).
--   - `overridden_by_l3_event_id` = <event_id> → this canon entry is
--     SHADOWED by a per-reality L3 event. The shadow is per-reality; the
--     canon row stays in the table for historical / audit lookup, but
--     prompt assembly resolves to the L3 event value via L5.E read path.
--
-- Cross-cycle contracts:
--   * Cycle 9 L2.A migrations (events / event_audit / outbox / snapshots) —
--     this table is per-reality, NOT meta, so all FKs are intra-DB or NULL.
--   * Cycle 13 L3.A 10 projection tables — this is the 11th, SAME
--     VerificationMeta pattern + index conventions.
--   * Cycle 13 L3.K projection_drift_state.table_name CHECK allowlist
--     does NOT include canon_projection (that allowlist is for the 10 L3.A
--     tables only; L5.K drift tracking will extend it in cycle 24+ as a
--     follow-up — for now canon_projection is OUTSIDE the L3.E sampler
--     scope but inside the cycle-14 L3.J alerting scope through generic
--     freshness metrics added in cycle 25+).
--   * Cycle 12 Projection trait — `crates/projections/canon/` ships in
--     this cycle (L5.D.3) implementing `Projection` for canon.* events.
--   * Cycle 24+ L5.B meta-worker canon writer — sole writer per I7.
--
-- ⚠️  DO NOT widen this table with reality-scoped overrides — those live
--     in L3 events (per-reality event store), NOT in this projection.
--     The `overridden_by_l3_event_id` field POINTS at the L3 event; it
--     does NOT carry its value.

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- L5.D.1  canon_projection
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS canon_projection (
    -- Single-canon-id PK per Q-L5-3 + L5.D.1 spec. The id is canonical
    -- across all realities; cascade tracking lives on `cascaded_from_reality_id`,
    -- override tracking lives on `overridden_by_l3_event_id`. UPSERT
    -- semantics (canon update = upsert, not insert) keys on this PK.
    canon_entry_id               UUID NOT NULL PRIMARY KEY,

    -- Book this canon entry belongs to (FK target lives in glossary DB
    -- per Q-L1A-2; cross-DB FK prohibited per I7 — so no REFERENCES clause).
    book_id                      UUID NOT NULL,

    -- Logical attribute path (e.g. "characters/alice/race",
    -- "regions/whispering_woods/climate"). Format-controlled by
    -- glossary-service; foundation treats as opaque TEXT.
    attribute_path               TEXT NOT NULL,

    -- The canon VALUE as authored. Stored as JSONB so the meta-worker
    -- writer can populate from event payload directly without parsing,
    -- and downstream L5.E [WORLD_CANON] reader can inspect typed shape.
    -- Empty default for INSERT-then-UPDATE flows (rare; meta-worker
    -- typically writes full row at once).
    value                        JSONB NOT NULL DEFAULT 'null'::jsonb,

    -- Q-L5-3 LOCKED: enum {L1_axiom, L2_seeded}. Single table with this
    -- column distinguishes the two canon layers.
    canon_layer                  TEXT NOT NULL,

    -- Lock level (typed by glossary-service: hard / soft / archived /
    -- experimental). Foundation treats as opaque TEXT; downstream tooling
    -- branches on the value.
    lock_level                   TEXT NOT NULL DEFAULT 'soft',

    -- The event_id that LAST WROTE this row from the canon stream.
    -- NULL is permitted only for cascade-sourced rows
    -- (`cascaded_from_reality_id` IS NOT NULL) — meta-worker writes
    -- from the canon.* event source; cascade reads write NULL here +
    -- populate `cascaded_from_reality_id`.
    source_event_id              UUID,

    -- Cascade read-through tracking (multiverse §3). NULL = this row was
    -- sourced from THIS reality's own canon subscription. Non-NULL =
    -- populated by inheritance from the ancestor reality_id. When the
    -- child later subscribes to its OWN canon update, meta-worker writes
    -- NULL back (replacing the cascade-sourced row with an own-source row).
    cascaded_from_reality_id     UUID,

    -- L3 override tracking. NULL = this canon entry is currently
    -- authoritative for this reality. Non-NULL = SHADOWED by a per-reality
    -- L3 event with this id. Index below filters HOT path
    -- (`overridden_by_l3_event_id IS NULL`) for prompt assembly.
    overridden_by_l3_event_id    UUID,

    -- last_synced_at: meta-worker writes NOW() on every successful write.
    -- L5.E (cycle 25) reads this for cache invalidation: cache invalidates
    -- entry on observing a newer last_synced_at than its cached value.
    last_synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ─────────────────────────────────────────────────────────────────
    -- VerificationMeta (Q-L3-4 set a) — same shape as cycle-13 L3.A.
    -- ─────────────────────────────────────────────────────────────────
    event_id                     UUID NOT NULL,
    aggregate_version            BIGINT NOT NULL,
    applied_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ─────────────────────────────────────────────────────────────────
    -- Integrity HWM (Q-L3-4 set b) — written by L3.E/F (cycle 14+).
    -- ─────────────────────────────────────────────────────────────────
    last_verified_event_version  BIGINT,
    last_verified_at             TIMESTAMPTZ,

    -- ─────────────────────────────────────────────────────────────────
    -- CHECK constraints.
    -- ─────────────────────────────────────────────────────────────────
    -- Q-L5-3 enum CHECK — defense-in-depth vs producer drift past wire-
    -- layer enum (see contracts/events/canon.go CanonLayer.IsValid).
    CONSTRAINT canon_projection_layer_valid
        CHECK (canon_layer IN ('L1_axiom', 'L2_seeded')),

    -- Lock level free-form but bounded; reject unknown values at storage
    -- layer (mirrors glossary-service authoring contract).
    CONSTRAINT canon_projection_lock_level_valid
        CHECK (lock_level IN ('hard', 'soft', 'archived', 'experimental')),

    -- value shape sanity — JSONB must not be SQL NULL (DEFAULT 'null'::jsonb
    -- is JSON null, not SQL null). Stops a programming bug from poisoning
    -- the projection.
    CONSTRAINT canon_projection_value_not_sql_null
        CHECK (value IS NOT NULL),

    -- Cascade XOR source_event semantics: a row is either
    --   (a) own-source — source_event_id IS NOT NULL,
    --                    cascaded_from_reality_id IS NULL
    --   (b) cascade    — source_event_id IS NULL,
    --                    cascaded_from_reality_id IS NOT NULL
    -- Never both (would mean canon writer + cascade writer raced).
    CONSTRAINT canon_projection_origin_xor
        CHECK (
            (source_event_id IS NOT NULL AND cascaded_from_reality_id IS NULL)
            OR
            (source_event_id IS NULL AND cascaded_from_reality_id IS NOT NULL)
        )
);

COMMENT ON TABLE canon_projection IS
    'L5.D.1 — Per-reality cache of authored canon (L1_axiom + L2_seeded). 11th projection table (cycle 13 L3.A shipped 10). Writers: meta-worker only (I7 sole-writer). Readers: roleplay-service [WORLD_CANON] prompt section via L5.E cache. Cascade + L3-override tracked via cascaded_from_reality_id + overridden_by_l3_event_id. VerificationMeta per Q-L3-4.';
COMMENT ON COLUMN canon_projection.canon_entry_id IS
    'Canonical UUID of the canon entry (matches glossary DB canon_entries.canon_entry_id). Single id across all realities; per-reality cascade/override tracked separately.';
COMMENT ON COLUMN canon_projection.canon_layer IS
    'Q-L5-3 LOCKED enum {L1_axiom, L2_seeded}. Single-table-with-column pattern (not separate tables per layer).';
COMMENT ON COLUMN canon_projection.cascaded_from_reality_id IS
    'NULL = own-source canon (meta-worker wrote from canon.* event stream). Non-NULL = inherited from ancestor reality (multiverse §3 cascade read-through). XOR with source_event_id.';
COMMENT ON COLUMN canon_projection.overridden_by_l3_event_id IS
    'NULL = this canon entry is currently authoritative. Non-NULL = SHADOWED by a per-reality L3 event with this id. Prompt assembly (L5.E) filters on IS NULL.';
COMMENT ON COLUMN canon_projection.last_synced_at IS
    'Meta-worker writes NOW() on every successful write. L5.E cache invalidation key (Q-L5-1 event-driven primary).';

COMMIT;
