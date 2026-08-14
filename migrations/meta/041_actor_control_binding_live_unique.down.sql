-- 041_actor_control_binding_live_unique.down.sql
--
-- @pii_sensitivity: none
-- @retention_class: operational
-- @retention_hot: n/a (a DDL step)
-- @erasure_method: hard_delete
-- @legal_basis: contract
--
-- ── THIS DOWN DESTROYS DATA, AND SAYS SO RATHER THAN DISCOVERING IT ─────────
--
-- The up-migration's whole purpose is that `(reality_id, actor_id)` may repeat
-- once a binding has been revoked. Restoring a PRIMARY KEY over that pair is
-- therefore impossible while any handoff history exists, and there are only two
-- honest ways to write this file: fail, or delete the history.
--
-- It deletes, deliberately and loudly. A `down` that cannot run is a `down`
-- nobody can use in the incident it exists for, and the rows removed are
-- REVOKED bindings — history, not authority. No live binding is touched, so
-- nobody loses control of an actor by reverting. **The audit trail survives
-- independently**: every one of these rows was written through MetaWrite, so
-- `meta_write_audit` holds the same facts and this DELETE does not erase the
-- record that a handoff happened.
--
-- If that trade is wrong for your incident, do not run this file — read the
-- rows out first.

DELETE FROM actor_control_binding WHERE revoked_at IS NOT NULL;

DROP INDEX IF EXISTS actor_control_binding_by_user;
DROP INDEX IF EXISTS actor_control_binding_one_live_driver;

ALTER TABLE actor_control_binding
    DROP CONSTRAINT IF EXISTS actor_control_binding_pkey;

ALTER TABLE actor_control_binding
    DROP COLUMN IF EXISTS binding_id;

ALTER TABLE actor_control_binding
    ADD CONSTRAINT actor_control_binding_pkey PRIMARY KEY (reality_id, actor_id);
