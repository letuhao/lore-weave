-- 035_drop_player_character_index.up.sql
-- `SEALED-BINDING`, second half — the table 034 replaces, and its audit path id.
-- Source: docs/plans/2026-08-06-game-tier-build-RUN-STATE.md §6g
--
-- @pii_sensitivity: none (this migration REMOVES the last PII in the table it
--   drops — `pc_name` — and adds no column of its own)
-- @retention_class: system_config
-- @retention_hot: n/a (a DDL step, not a data store)
-- @erasure_method: hard_delete (the DROP is itself the erasure of every row the
--   table could have held; it held none — no production writer ever existed)
-- @legal_basis: legitimate_interest
--
-- Its own migration rather than the tail of 034, so that "the binding exists"
-- and "the old table is gone" are two facts with two `down`s. The precedent is
-- this project's own: contracts/migrations/per_reality/0017 dropped the sibling
-- pc/npc projections as one deliberate step.
--
-- ── SAFETY: WHY THIS DROPS NO DATA ──────────────────────────────────────────
--
-- `player_character_index` has **no PRODUCTION writer**. Measured, and stated
-- precisely because the first draft of this comment said "no INSERT anywhere in
-- the tree" and that is false:
--
--   INSERT INTO player_character_index
--     services/meta-worker/pkg/user_erased_writer/pglive/pglive_pg_test.go:63
--     services/meta-worker/pkg/user_erased_writer/pglive/integration_pg_test.go:75
--
-- Both are TEST FIXTURES that seed the table in order to exercise the erasure
-- READER. Nothing in any service writes a row, so in every deployment the table
-- is empty by construction and always was. Those two fixtures move to
-- `actor_control_binding` in this same commit.
--
-- The three readers move too (services/meta-worker/.../pglive.go), which is what
-- keeps the erasure path whole rather than merely still compiling. Leaving a
-- statement pointing at a dropped table is not a safe failure: this exact file's
-- sibling records what happened last time — the statement errors, the handler
-- NACKs, and the erasure retries forever without completing.

DROP TRIGGER IF EXISTS player_character_index_touch_updated_at_trg ON player_character_index;
DROP TABLE IF EXISTS player_character_index CASCADE;
DROP FUNCTION IF EXISTS player_character_index_touch_updated_at() CASCADE;

-- ── The read-audit CHECK enum follows the table ─────────────────────────────
--
-- `contracts/meta/meta-sensitive-read-paths.yml` is the SSOT and
-- `scripts/read-audit-query-type-drift-lint.sh` asserts this CHECK lists
-- EXACTLY its ids, reading the LATEST migration that (re)defines the
-- constraint. So the rename lands here, in the same migration as the drop:
-- leaving `player_index_cross_user` behind would be an audit path pointing at a
-- table Postgres no longer has — a registration that can never fire, which is
-- the stale-claim shape this repository has recorded four times.
--
-- Safety: no existing row can violate the tighter CHECK. `player_index_cross_user`
-- is written only by a cross-user SELECT on a table that is empty by
-- construction and has no such caller; the GDPR cascade's two reads are
-- OWNER-scoped and therefore not sensitive reads at all.

ALTER TABLE meta_read_audit DROP CONSTRAINT IF EXISTS meta_read_audit_query_type_enum;

ALTER TABLE meta_read_audit ADD CONSTRAINT meta_read_audit_query_type_enum CHECK (
    query_type IN (
        'actor_binding_cross_user',
        'audit_query',
        'admin_bulk_export',
        'bulk_meta_query',
        'bulk_pii_read',
        'pii_user_get',
        'pii_user_erase'
    )
);
