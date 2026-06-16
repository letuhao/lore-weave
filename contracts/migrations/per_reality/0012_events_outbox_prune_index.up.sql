-- contracts/migrations/per_reality/0012_events_outbox_prune_index.up.sql
--
-- D-OUTBOX-PRUNE-INDEX (088) — supporting partial index for the retention-worker
-- events_outbox prune scan.
--
-- The L2.C 0005 migration shipped 2 partial indexes:
--   * PENDING     — WHERE published = FALSE AND dead_lettered_at IS NULL
--   * DEAD-LETTER — WHERE dead_lettered_at IS NOT NULL
-- Neither covers the retention-worker prune predicate
-- (services/retention-worker/pkg/pgio/pgio.go):
--
--     WHERE published = TRUE
--       AND dead_lettered_at IS NULL
--       AND last_attempt_at < $cutoff
--     ... LIMIT $batch
--
-- so the inner `ctid IN (SELECT ctid …)` does a seq/partial scan of the whole
-- table. This partial index on last_attempt_at, scoped to exactly the
-- prune-eligible set (published + not dead-lettered), turns that into an index
-- range scan on `last_attempt_at < cutoff` at scale.
--
-- Non-breaking, index-only, idempotent. events_outbox is ephemeral (kept small
-- by this very prune), so a plain (non-CONCURRENT) CREATE INDEX is fine — the
-- brief lock is acceptable and matches the 0005 index pattern. (CONCURRENTLY
-- cannot run inside the migration's transaction anyway.)

BEGIN;

CREATE INDEX IF NOT EXISTS events_outbox_prune_idx
    ON events_outbox (last_attempt_at)
    WHERE published = TRUE AND dead_lettered_at IS NULL;

COMMENT ON INDEX events_outbox_prune_idx IS
    'D-OUTBOX-PRUNE-INDEX (088) — supports the retention-worker prune scan: published=TRUE AND dead_lettered_at IS NULL AND last_attempt_at < cutoff. Partial, scoped to the prune-eligible set.';

COMMIT;
