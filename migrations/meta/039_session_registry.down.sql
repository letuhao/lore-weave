-- Down for 039 — session_registry.
--
-- Safe with one consequence worth stating: the table is OPERATIONAL state, not
-- history. Every live row can be re-created by re-binding, so dropping it costs
-- no durable fact — but it does REVOKE every outstanding capability at once,
-- because validation is a digest lookup and a lookup against a missing table
-- finds nothing. That is the correct direction to fail (a dropped store denies,
-- it does not admit), and it is why this down is safe to run rather than safe
-- to run unnoticed: every bound session must re-bind afterwards.
--
-- Contrast the 036 down, which destroys tenancy data nothing else records and
-- therefore carries a guard. Nothing here is unrecoverable, so no guard.

DROP INDEX IF EXISTS idx_session_registry_service;
DROP INDEX IF EXISTS idx_session_registry_reality;
DROP TABLE IF EXISTS session_registry;
