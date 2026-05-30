-- 006_book_reality_subscription.up.sql
-- L5.B (P1 task #18) — book → reality canon subscription map.
--
-- The canon fan-out flow (publisher xreality.book.canon.updated → meta-worker
-- canon_writer) must know WHICH realities subscribe to a given book's canon so
-- it can UPSERT canon_projection on exactly those per-reality DBs. The
-- canon_writer's RealitySubscriptionLookup.SubscribersForBook reads this table
-- (joined to reality_registry for live status), replacing the V1 "all active
-- realities" placeholder.
--
-- Written by: world-service / book-onboarding when a reality opts into a book's
--   canon (out of scope here — the foundation ships the schema + meta-worker
--   reader; the producer is a later domain cycle).
-- Read by: meta-worker canon_writer (SubscribersForBook).
-- Retention: lifecycle-bound to the reality (cascade-cleaned when a reality is
--   dropped — handled by the reality close pipeline, not an FK since reality_id
--   rows are audit-retained).

CREATE TABLE IF NOT EXISTS book_reality_subscription (
    book_id     UUID        NOT NULL,
    reality_id  UUID        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (book_id, reality_id)
);

-- Hot path: SubscribersForBook(book_id) → list of reality_ids.
CREATE INDEX IF NOT EXISTS idx_book_reality_subscription_book
    ON book_reality_subscription (book_id);

-- Reverse lookup: every book a reality subscribes to (reality close cleanup).
CREATE INDEX IF NOT EXISTS idx_book_reality_subscription_reality
    ON book_reality_subscription (reality_id);

COMMENT ON TABLE book_reality_subscription IS
    'L5.B — book→reality canon subscription map. Read by meta-worker canon_writer SubscribersForBook to scope per-reality canon_projection fan-out.';
