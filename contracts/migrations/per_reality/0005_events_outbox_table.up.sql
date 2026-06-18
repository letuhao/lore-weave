-- contracts/migrations/per_reality/0005_events_outbox_table.up.sql
--
-- L2.C.1 — `events_outbox` table (production shape).
--
-- Per R06 §12F.1 the outbox is the durable hand-off between domain writes
-- (cycle 9 L2.A `events` table) and the L2.D publisher service that drains
-- outbox rows into Redis Streams. Cycle 5 shipped a placeholder `outbox`
-- table; cycle 9's 0002 migration dropped that placeholder along with the
-- skeleton `events` (the cycle-5 FK was the cleanup hook). This migration
-- creates the production-shape `events_outbox` table.
--
-- LOCKED decisions consumed:
--   * Q-L1B-3 (OPEN_QUESTIONS_LOCKED §3): `MetaWriteBatch` multi-table TX
--     support — the outbox row MUST be written in the SAME transaction as
--     the `events` append. Atomicity contract enforced by the
--     `tests/integration/outbox_atomicity_test.rs` integration test.
--   * Q-L2-3 (§4): events ↔ event_audit linkage is UUID pointer (not FK)
--     because archive cuts FKs. THIS table has the SAME constraint:
--     `event_id` is a UUID pointer to `events.event_id` (NOT a FK) — once
--     an event's monthly partition is detached + archived by the L2.J
--     archive-worker (cycle 11), the row is gone from `events` but its
--     outbox row may legitimately still be `published = FALSE` mid-flight.
--   * Q-L2D-1 (§4): publisher V1 deploys a SINGLE replica per shard host;
--     `FOR UPDATE SKIP LOCKED` works correctly with N=1 (trivially no
--     contention) AND with V2+ multi-replica (no duplicate XADD).
--   * Q-L2-5 (§4): publisher V1 ships a no-op leader-election skeleton;
--     this migration is publisher-replica-count agnostic.
--
-- Cross-cycle contracts:
--   * Cycle 9 (L2.A): `events.event_id` is the pointer target. Cycle 9
--     adds an index on `events (event_id)` (events_event_id_idx) that we
--     rely on for the publisher's batch-fetch join when populating the
--     wire envelope.
--   * Cycle 9 (L2.A): the cycle-9 0002 migration drops the cycle-5
--     placeholder `outbox` table; we DO NOT need to repeat that here.
--   * Cycle 8 (L2.F/I): every outbox row's wire envelope (event_type,
--     event_version) is registered in `contracts/events/_registry.yaml`;
--     the L2.I validators_go check fires BEFORE the same-TX outbox write,
--     so by the time a row reaches the publisher it is guaranteed
--     schema-valid.
--   * Cycle 11 (L2.J/K): retention + archive workers do NOT touch this
--     table — events_outbox is ephemeral by design (published rows are
--     pruned by the publisher itself once attempts ≥ 1 + published = TRUE +
--     a configurable grace window passes).
--
-- ⚠️ DO NOT add per-reality DOMAIN tables here. This file is L2 infra ONLY.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────
-- events_outbox — durable hand-off between event append and publisher
-- ─────────────────────────────────────────────────────────────────────────
--
-- Row lifecycle:
--   1. domain write opens TX → INSERT INTO events (...) → outbox::write()
--      inserts (event_id, reality_id, published=FALSE, attempts=0)
--   2. publisher poll loop scans `WHERE published=FALSE AND
--      dead_lettered_at IS NULL` with FOR UPDATE SKIP LOCKED
--   3. publisher XADD-s envelope to Redis Streams, then UPDATE
--      `published=TRUE, attempts=attempts+1, last_attempt_at=NOW()`
--   4. on XADD failure → UPDATE `attempts=attempts+1, last_error=$err,
--      last_attempt_at=NOW()` with backoff before retry
--   5. when attempts >= max_attempts (config; default 10) → UPDATE
--      `dead_lettered_at=NOW()` (row excluded from pending scan; SRE
--      reviews via dead-letter triage runbook)

CREATE TABLE IF NOT EXISTS events_outbox (
    -- Identity (UUID pointer to events.event_id; NOT FK per Q-L2-3 +
    -- archive-cut rationale). One outbox row per event.
    event_id           UUID NOT NULL PRIMARY KEY,
    -- Tenant — denormalized to keep the FOR UPDATE SKIP LOCKED scan
    -- shard-local without joining the (potentially partitioned) events
    -- table. Matches `events.reality_id` exactly.
    reality_id         UUID NOT NULL,
    -- Publish state
    published          BOOLEAN NOT NULL DEFAULT FALSE,
    attempts           INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT,
    last_attempt_at    TIMESTAMPTZ,
    dead_lettered_at   TIMESTAMPTZ,
    -- Bookkeeping
    enqueued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Constraints
    CONSTRAINT events_outbox_attempts_nonneg CHECK (attempts >= 0),
    CONSTRAINT events_outbox_published_consistency CHECK (
        -- A row marked published=TRUE MUST have attempts >= 1 and a
        -- last_attempt_at timestamp.
        (published = FALSE)
        OR (published = TRUE AND attempts >= 1 AND last_attempt_at IS NOT NULL)
    ),
    CONSTRAINT events_outbox_dead_letter_consistency CHECK (
        -- A dead-lettered row MUST also have attempts >= 1.
        dead_lettered_at IS NULL
        OR (dead_lettered_at IS NOT NULL AND attempts >= 1)
    )
);

COMMENT ON TABLE  events_outbox IS
    'L2.C outbox: durable hand-off between event append (cycle 9 events table) and L2.D publisher. event_id is UUID pointer to events.event_id (NOT FK; Q-L2-3 archive-cut rationale).';
COMMENT ON COLUMN events_outbox.published IS
    'TRUE once the publisher has XADDed the envelope to Redis Streams. Pruning is a future concern (D-OUTBOX-PRUNE deferred).';
COMMENT ON COLUMN events_outbox.dead_lettered_at IS
    'Set once attempts >= max_attempts (config). Row excluded from pending scan; SRE triages via runbooks/publisher/lag.md.';

-- ─────────────────────────────────────────────────────────────────────────
-- Indexes — 2 partial per L2.C.1 acceptance criteria
-- ─────────────────────────────────────────────────────────────────────────
--
-- Index strategy:
--   1. PENDING — publisher hot path: pull next batch of rows that are
--      neither published nor dead-lettered.
--      Predicate: published = FALSE AND dead_lettered_at IS NULL.
--      Sort by enqueued_at ASC so the publisher drains oldest first
--      (preserves cross-aggregate causal order at the publisher tier;
--      strict per-aggregate order is upheld at insertion time by L2.A
--      optimistic CC).
--   2. DEAD-LETTER TRIAGE — SRE / admin-cli scans by reality + dead-letter
--      time when investigating an alert.
--      Predicate: dead_lettered_at IS NOT NULL.

CREATE INDEX IF NOT EXISTS events_outbox_pending_idx
    ON events_outbox (reality_id, enqueued_at)
    WHERE published = FALSE AND dead_lettered_at IS NULL;

CREATE INDEX IF NOT EXISTS events_outbox_dead_letter_idx
    ON events_outbox (reality_id, dead_lettered_at)
    WHERE dead_lettered_at IS NOT NULL;

COMMIT;
