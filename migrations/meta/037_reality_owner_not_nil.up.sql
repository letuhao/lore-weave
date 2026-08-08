-- 037 — the nil UUID is not an owner (W6 hardening).
--
-- WHY
-- ---
-- 036 made the (owner_kind, owner_user_id) PAIR consistent, but said nothing
-- about the VALUE. `('user', '00000000-0000-0000-0000-000000000000')` satisfies
-- every constraint on the table: a reality owned by a user that cannot exist,
-- sitting in the partial owner index, invisible to any join against `users`.
--
-- Three application layers now reject it (the admin handler, the Rust worker,
-- and the bridge's deriveOwner). That is defence in depth, and it is not the
-- same thing as a guarantee: the bridge is an HTTP endpoint, `provision_drill`
-- already demonstrates a raw INSERT path around it, and a cold-start review
-- confirmed live that `UPDATE reality_registry SET owner_kind='user',
-- owner_user_id='00000000-…'` succeeded with all CHECKs satisfied.
--
-- A rule enforced only by the callers is a rule that holds until someone writes
-- a new caller. This is the mechanism.
--
-- @pii_sensitivity: low (constrains the VALUE of an existing opaque user id;
--   introduces no new column and no new data)
-- @retention_class: tenancy_binding
-- @retention_hot: lifetime_of_reality
-- @erasure_method: reassign_to_system_on_user_erasure — unchanged from 036 and
--   COMPATIBLE with it: erasure sets (system, NULL), and NULL is exempt from
--   this CHECK, so the constraint cannot block an erasure. Discharged by
--   PgMetaScrubber.reassignOwnedRealities.
-- @legal_basis: contract

ALTER TABLE reality_registry
    ADD CONSTRAINT reality_registry_owner_not_nil_uuid
        CHECK (owner_user_id IS NULL
               OR owner_user_id <> '00000000-0000-0000-0000-000000000000'::uuid);
