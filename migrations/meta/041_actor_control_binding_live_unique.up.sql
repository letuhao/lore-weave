-- 041_actor_control_binding_live_unique.up.sql
-- `SEALED-BINDING`, corrected — the constraint now enforces what 034's header
-- SAYS, which is not what it did.
-- Source: docs/plans/2026-08-14-player-control-RUN-STATE.md §1 (the measurement)
-- Written by: nobody at runtime — this is DDL. The table's writer is the
--   meta-worker bridge via contracts/meta MetaWrite() (I8).
-- Read by: unchanged — the GDPR erasure cascade, and (new, this round) the
--   commit-service subject resolver.
--
-- @pii_sensitivity: none (adds one opaque surrogate uuid; no name, no presence)
-- @retention_class: operational
-- @retention_hot: indefinite
-- @erasure_method: hard_delete
-- @legal_basis: contract
--
-- ── THE DEFECT, MEASURED ────────────────────────────────────────────────────
--
-- 034's header states the invariant in these words:
--
--     "One driver per actor per reality. … two LIVE rows for one actor is the
--      confused-deputy state the whole table exists to make unrepresentable."
--
-- It then implemented `PRIMARY KEY (reality_id, actor_id)`, which permits one
-- row **TOTAL**. Those are different statements, and they diverge at exactly
-- the operation the design calls normal — handoff. Run against a throwaway
-- database carrying only 034:
--
--     grant to user A            -> granted
--     revoke                     -> revoked
--     grant same actor to user B -> ERROR: duplicate key value violates unique
--                                   constraint "actor_control_binding_pkey"
--
-- So **revoke was terminal**: an actor whose driver left could never be driven
-- again, by anyone. The intent was never that; the constraint simply said
-- something narrower than the sentence above it.
--
-- The available workaround made it worse. Re-granting by UPDATEing
-- `user_ref_id` in place emits the event `contracts/meta/events_allowlist.yaml`
-- binds to `op: UPDATE` — `actor.control.revoked` — for what is a GRANT. A name
-- that lies is the precise defect that got `player_character_index` dropped
-- (035: *"`pc_id` renamed to `actor_id` inside a table still called
-- `player_character_index` is `quantity[0] = "hp"` one tier over"*), so
-- reproducing it here to dodge a migration was not an option.
--
-- ── THE REPAIR ──────────────────────────────────────────────────────────────
--
-- A partial unique index over the LIVE rows. One live driver per actor is now
-- enforced as written, revoked rows remain as history, and every state change
-- keeps the operation the allowlist already maps:
--
--     grant   = INSERT  -> actor.control.granted
--     revoke  = UPDATE  -> actor.control.revoked
--     handoff = revoke, then a NEW grant row
--
-- ── ON THE SURROGATE KEY, WHICH LOOKS LIKE A REGRESSION AND IS NOT ──────────
--
-- 035's column audit condemned `pc_index_id` as *"a surrogate PK where
-- (reality_id, pc_id) was already UNIQUE"* — redundant, and therefore noise.
-- `binding_id` is the opposite case: once history is retained,
-- `(reality_id, actor_id)` is **no longer unique**, so a row needs an identity
-- of its own and the surrogate is load-bearing. The test is whether removing it
-- leaves the row addressable; there it did, here it does not.
--
-- SAFE BY MEASUREMENT, not by assumption: `SELECT count(*)` on the real
-- `loreweave_meta` returns **0**. The table has had no production writer since
-- it was created — which is the same emptiness 035 recorded about the table it
-- replaced, and the reason this rewrite costs nothing.

ALTER TABLE actor_control_binding
    DROP CONSTRAINT IF EXISTS actor_control_binding_pkey;

ALTER TABLE actor_control_binding
    ADD COLUMN IF NOT EXISTS binding_id UUID NOT NULL DEFAULT gen_random_uuid();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'actor_control_binding_pkey'
           AND conrelid = 'actor_control_binding'::regclass
    ) THEN
        ALTER TABLE actor_control_binding
            ADD CONSTRAINT actor_control_binding_pkey PRIMARY KEY (binding_id);
    END IF;
END $$;

-- THE INVARIANT, as 034's header words it: one LIVE driver per actor.
-- A partial index and not a plain UNIQUE, because a revoked row must not
-- occupy the slot — that occupancy was the whole defect.
CREATE UNIQUE INDEX IF NOT EXISTS actor_control_binding_one_live_driver
    ON actor_control_binding (reality_id, actor_id)
    WHERE revoked_at IS NULL;

-- Answers "which actors does this human drive?" — the first question a
-- character-select screen asks, and the query the GDPR erasure cascade already
-- runs (meta-worker/pkg/user_erased_writer). It was served by the old PK's
-- prefix only for `reality_id`, never for `user_ref_id`.
CREATE INDEX IF NOT EXISTS actor_control_binding_by_user
    ON actor_control_binding (user_ref_id)
    WHERE revoked_at IS NULL;
