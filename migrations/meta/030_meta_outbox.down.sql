-- 030 (P2/101) rollback: drop meta_outbox.
--
-- Clean + non-destructive to existing data: the table is additive + ephemeral
-- (no FKs reference it; no other table FKs into it; no backfill). Dropping it
-- reverts MetaWrite to Outbox=nil behaviour (events silently dropped, as before
-- 101). Any in-flight unpublished rows are lost — acceptable for a rollback
-- (at-least-once was the semantic; consumers are idempotent and the source DB
-- state, e.g. revoked_at, remains the SSOT).

DROP TABLE IF EXISTS meta_outbox;
