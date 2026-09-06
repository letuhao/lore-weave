-- 034_actor_control_binding.up.sql
-- `SEALED-BINDING` — which HUMAN drives which ACTOR, in which reality.
-- Source: docs/plans/2026-08-06-game-tier-build-RUN-STATE.md §6g (the argument,
--         the column audit of the table this replaces, and the PO's decision)
-- Written by: whoever grants or revokes control of an actor, via
--   contracts/meta MetaWrite() (I8) — never a direct INSERT.
-- Read by: the GDPR erasure cascade (which realities does this user touch), and
--   whatever resolves an authenticated session to its subject.
--
-- @pii_sensitivity: none (three opaque uuids; no name, no presence, no PII)
-- @retention_class: operational
-- @retention_hot: indefinite
-- @erasure_method: hard_delete
-- @legal_basis: contract
--
-- ── WHY THIS TABLE EXISTS, AND WHY IT REPLACES `player_character_index` ──────
--
-- The new framing is that **a player is not a KIND of actor — it is a CONTROL
-- INTERFACE: a human with a GUI driving an actor.** If "player" is no longer a
-- kind, then `(user, reality, actor)` is the only thing that makes a player a
-- player: removing the PC/NPC distinction does not delete the binding, it makes
-- the binding the entire concept.
--
-- `012_player_character_index` held that binding and six things around it. The
-- column audit (§6g) is why it is dropped rather than renamed:
--
--   user_ref_id · reality_id · pc_id   the binding — but `pc_id`'s NAME is the
--                                       vocabulary the framing deleted
--   pc_name                            the table's last PII, and two-kind
--                                       vocabulary
--   status                             5 of 6 members wrong: `npc_converted`
--                                       dead · `deceased` a second SSOT for
--                                       death (GoneState holds it) ·
--                                       `active`/`offline` are PRESENCE, which
--                                       belongs to the transport, not to a
--                                       durable binding · `hidden` is a UI
--                                       preference (CLAUDE.md routes those to
--                                       /v1/me/preferences). Only `deleted` was
--                                       about the binding, and it wanted to be
--                                       a timestamp.
--   last_seen_at                       presence again
--   pc_index_id                        a surrogate PK where (reality_id, pc_id)
--                                       was already UNIQUE
--
-- And it had **no INSERT anywhere in the tree**, so it was empty by
-- construction: nothing is preserved by keeping it. The precedent is this
-- project's own — `per_reality/0017_drop_pc_npc_projections` DROPPED the sibling
-- pc/npc artifacts rather than renaming around them.
--
-- ⚠ The deepest reason is the NAME. `pc_id` renamed to `actor_id` inside a table
-- still called `player_character_index` is `quantity[0] = "hp"` one tier over:
-- it passes every check and changes nothing.
--
-- ── WHY THE META DATABASE (the PO asked which is standard, and why) ──────────
--
-- The binding is **CONTROL, not SIMULATION.** Control questions are
-- cross-instance by nature, so control data in a data-plane database is the
-- anti-pattern. Four measured reasons:
--
--   1. A human exists ACROSS realities. In a per-reality DB, "which actors do I
--      drive?" — the first question a character-select screen asks — becomes a
--      fan-out over N databases.
--   2. The meta DB already carries per-user control rows on purpose, with the
--      machinery this needs: 009_pii_registry · 011_user_consent_ledger ·
--      018_user_cost_ledger · 026_book_reality_subscription · 014_meta_read_audit
--      plus contracts/meta/meta-sensitive-read-paths.yml.
--   3. `actor_id`'s FK lives in the PER-REALITY database. A control-plane
--      pointer into a data-plane identity is exactly what 033's
--      `reality_ruleset_binding` is to a content-addressed artifact, and
--      `ruleset_boot.rs` states the same law.
--   4. GDPR erasure must find EVERY binding. A fan-out over N reality DBs is
--      the shape that leaves rows behind.
--
-- ── TENANCY ─────────────────────────────────────────────────────────────────
-- Tier: per-user. Scope key: user_ref_id. There is no shared row: a binding
-- names one human, and a cross-user READ is the identity-manipulation surface
-- registered as `actor_binding_cross_user` in
-- contracts/meta/meta-sensitive-read-paths.yml — every such read writes a
-- meta_read_audit row.

CREATE TABLE IF NOT EXISTS actor_control_binding (
    -- WHO drives. Opaque; the only user reference in the table and not PII on
    -- its own, which is what lets `@erasure_method` be a plain hard_delete.
    user_ref_id  UUID            NOT NULL,

    -- WHERE. Names a reality in reality_registry.
    reality_id   UUID            NOT NULL,

    -- WHAT. The per-reality actor identity; its FK lives in the PER-REALITY
    -- database, so it is deliberately unconstrained here (reason 3 above).
    actor_id     UUID            NOT NULL,

    created_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- The BINDING is revoked; the actor lives on. A timestamp and not a status
    -- enum, because every other member of `012`'s enum turned out to belong to
    -- the transport, to GoneState, or to user preferences — and re-introducing
    -- one here would rebuild the second SSOT that audit found.
    revoked_at   TIMESTAMPTZ     NULL,

    -- One driver per actor per reality. This is the constraint that makes the
    -- table an answer to "who may act as this subject" rather than a log: two
    -- live rows for one actor is the confused-deputy state the whole table
    -- exists to make unrepresentable.
    PRIMARY KEY (reality_id, actor_id),

    CONSTRAINT actor_control_binding_revoked_after_created CHECK (
        revoked_at IS NULL OR revoked_at >= created_at
    )
);

-- The character-select query: "which actors do I drive, and where" — the reason
-- reason 1 above rules out a per-reality home.
CREATE INDEX IF NOT EXISTS idx_actor_control_binding_user
    ON actor_control_binding (user_ref_id, reality_id);

-- The GDPR erasure lookup: the DISTINCT realities a user appears in. Partial on
-- nothing — a REVOKED binding still means the user was there, and erasure must
-- reach it (over-inclusion is the safe direction).
CREATE INDEX IF NOT EXISTS idx_actor_control_binding_reality
    ON actor_control_binding (reality_id);

COMMENT ON TABLE actor_control_binding IS
    'SEALED-BINDING — which human drives which actor, in which reality. A player '
    'is not a kind of actor; it is a control interface, and this row is the whole '
    'of what makes one. Replaces player_character_index (012), whose name carried '
    'the deleted vocabulary and whose other six columns were PII, presence, or a '
    'second SSOT. Cross-user reads = sensitive (actor_binding_cross_user).';
COMMENT ON COLUMN actor_control_binding.actor_id IS
    'Per-reality actor identity. The FK lives in the PER-REALITY database: this '
    'is a control-plane pointer into a data-plane identity, the same split '
    '033_reality_ruleset_binding makes against the content-addressed store.';
COMMENT ON COLUMN actor_control_binding.revoked_at IS
    'The BINDING is revoked; the actor lives on. Not a status enum — see the '
    'column audit in the header.';
