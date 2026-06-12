-- 030 (P2/101): meta_outbox — the meta-DB transactional outbox.
--
-- PII/retention classification (S08 §12X.3/§12X.4; pii-classify-lint).
-- @pii_sensitivity: low (payload carries opaque user_ref_id + table/op metadata, never PII *values*; the after-image is the same data MetaWrite already persisted under its own table's classification)
-- @retention_class: ephemeral
-- @retention_hot: 7d
-- @erasure_method: crypto_shred_actor
-- @legal_basis: legitimate_interest
--
-- WHY: contracts/meta MetaWrite is wired to emit allowlisted outbox events in
-- the SAME TX as the data + meta_write_audit rows (metawrite.go: the
-- `if cfg.Outbox != nil` block). No production OutboxAppender / outbox table
-- existed, so cfg.Outbox was nil platform-wide and every allowlisted event
-- (user.consent.revoked from erasure step 7, etc.) was silently dropped
-- (D-METAWRITE-OUTBOX-UNWIRED / DEFERRED 101). This is the durable hand-off:
-- MetaWrite's appender (sdks/go/metaoutbox) INSERTs one row here per emitted
-- event inside the write TX; the dedicated meta-outbox-relay drains it to Redis
-- (lw.meta.events + the xreality.* bridge for cross-reality events).
--
-- This table is an OUTBOX TRANSPORT table, NOT an audited domain table: it is
-- written by MetaWrite's appender and its publish-state is updated by the
-- relay (exactly as the per-reality events_outbox is updated by the publisher).
-- It is therefore exempt from the I8 meta-write-discipline lint (the relay's
-- UPDATE publish-state is the drain, not a domain write that must route through
-- MetaWrite).
--
-- The publish-state machine + index strategy mirror the proven per-reality
-- events_outbox (contracts/migrations/per_reality/0005) so the relay's drain
-- logic matches the publisher's hardened shape. Unlike events_outbox, this
-- table SELF-CONTAINS the wire envelope (event_name + payload) — Option B has
-- no events/events_outbox split.

CREATE TABLE IF NOT EXISTS meta_outbox (
    -- Identity — = OutboxEvent.EventID (cfg.UUIDGen); one row per emitted event.
    event_id          UUID        NOT NULL PRIMARY KEY,
    -- Wire envelope (self-contained — no events-table join).
    event_name        TEXT        NOT NULL,       -- allowlist event_name, e.g. user.consent.revoked
    aggregate_id      TEXT        NOT NULL,        -- pkAsString(intent.PK)
    payload           JSONB       NOT NULL,        -- {table, operation, pk, after}
    -- Cross-reality routing: set by the appender from events_allowlist.yaml's
    -- xreality_topic. When non-NULL the relay ALSO XADDs to this topic so
    -- existing xreality consumers (meta-worker/user_erased_writer, 071) are fed.
    xreality_topic    TEXT        NULL,
    -- Publish-state machine (identical to events_outbox).
    published         BOOLEAN     NOT NULL DEFAULT FALSE,
    attempts          INTEGER     NOT NULL DEFAULT 0,
    last_error        TEXT        NULL,
    last_attempt_at   TIMESTAMPTZ NULL,
    dead_lettered_at  TIMESTAMPTZ NULL,
    -- Bookkeeping. enqueued_at orders the pending scan (DB wall-clock, like
    -- events_outbox); recorded_at_nanos preserves OutboxEvent.RecordedAt
    -- (cfg.Clock unix nanos) verbatim for the wire envelope (mirrors the
    -- meta_write_audit.created_at_nanos BIGINT pattern).
    enqueued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recorded_at_nanos BIGINT      NOT NULL,
    CONSTRAINT meta_outbox_attempts_nonneg CHECK (attempts >= 0),
    CONSTRAINT meta_outbox_event_name_nonempty CHECK (length(event_name) > 0),
    CONSTRAINT meta_outbox_payload_is_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT meta_outbox_published_consistency CHECK (
        published = FALSE
        OR (published = TRUE AND attempts >= 1 AND last_attempt_at IS NOT NULL)
    ),
    CONSTRAINT meta_outbox_dead_letter_consistency CHECK (
        dead_lettered_at IS NULL
        OR (dead_lettered_at IS NOT NULL AND attempts >= 1)
    )
);

-- PENDING — relay hot path: oldest-first scan of unpublished, non-dead rows.
CREATE INDEX IF NOT EXISTS meta_outbox_pending_idx
    ON meta_outbox (enqueued_at)
    WHERE published = FALSE AND dead_lettered_at IS NULL;

-- DEAD-LETTER TRIAGE — SRE scans dead-lettered rows when investigating lag.
CREATE INDEX IF NOT EXISTS meta_outbox_dead_letter_idx
    ON meta_outbox (dead_lettered_at)
    WHERE dead_lettered_at IS NOT NULL;

COMMENT ON TABLE meta_outbox IS
    'P2/101 meta-DB transactional outbox. Written by MetaWrite''s appender (sdks/go/metaoutbox) in the write TX; drained by meta-outbox-relay to lw.meta.events (+ xreality.* bridge). Ephemeral: published rows pruned after a grace window (D-META-OUTBOX-PRUNE). Outbox transport table — exempt from I8 meta-write-discipline.';
COMMENT ON COLUMN meta_outbox.xreality_topic IS
    'When non-NULL, the relay ALSO XADDs to this xreality.<entity>.<verb> topic so per-reality consumers (071) are fed. Resolved at write-time from events_allowlist.yaml.';
COMMENT ON COLUMN meta_outbox.recorded_at_nanos IS
    'OutboxEvent.RecordedAt (cfg.Clock unix nanos) — the logical event time for the wire envelope. enqueued_at is the DB-side row insert time used for scan ordering.';
