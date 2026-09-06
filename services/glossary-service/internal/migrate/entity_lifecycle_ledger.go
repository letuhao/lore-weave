package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityLifecycleLedgerSQL — the PHYSICAL lifecycle ledger (plan T31 / design D5).
//
// ── WHY A LEDGER AND NOT JUST THE COLUMNS ────────────────────────────────────────────────
// `glossary_entities.deleted_at` and `.status` answer *"is it gone NOW"* and nothing else.
// They cannot answer *when*, *by whom*, *from what*, or *how many times* — a soft-delete
// followed by a restore leaves `deleted_at = NULL`, which is byte-identical to an entity that
// was never touched. D-ENTITY-LIFECYCLE's finding was that four services keep four private
// notions of "gone" and none is connected to any other; a column that forgets its own history
// is why reconciling them after the fact is impossible.
//
// The design (D5) demotes those columns to **derived caches** of this ledger. This step
// creates the ledger and starts writing it; the demotion of the readers is deliberately NOT
// here — see the note at the bottom.
//
// ── THE INVARIANT THIS EXISTS TO SUPPORT ─────────────────────────────────────────────────
// The architecture diagram is explicit that the ledger row and the outbox row are written in
// ONE transaction with the mutation:
//
//	rect: ONE transaction — the invariant
//	  G->>DB: write lifecycle ledger
//	  G->>DB: write outbox row
//
// So a state change with no ledger row is impossible by construction rather than by
// convention — the same reasoning T27 applied to the outbox, and for the same reason: the
// failure was never a wrong UPDATE, it was an UPDATE that arrived alone.
//
// ── APPEND-ONLY, ENFORCED BY THE SCHEMA ──────────────────────────────────────────────────
// A ledger you can UPDATE is a cache with extra steps. There is no `updated_at`, no mutable
// column, and the trigger below refuses UPDATE and DELETE outright. That is stronger than a
// convention and it costs nothing: nothing in the service has any reason to rewrite history,
// and the day something tries, it fails loudly instead of silently rewriting the audit trail.
//
// ── SHIPPED AS A NEW CHAIN STEP ──────────────────────────────────────────────────────────
// `migrate.go:231` — *"shipped as a NEW ledger step (0052) — NOT edited"*. Editing an applied
// step breaks every already-migrated database, because `ApplyOnce` records the name and never
// revisits it. This is 0063.
const entityLifecycleLedgerSQL = `
CREATE TABLE IF NOT EXISTS entity_lifecycle_ledger (
    ledger_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id     uuid        NOT NULL,
    book_id       uuid        NOT NULL,
    -- The transition, not the resulting state: "deleted" / "restored" / "purged" /
    -- "status_changed" / "kind_reassigned". Deliberately the same vocabulary as the outbox
    -- event's 'op', so a ledger row and its event can be read side by side without a mapping
    -- table that would itself drift.
    op            text        NOT NULL,
    -- Physical axis only (D5): wall-clock and authored. The STORY axis (what the narrative
    -- says is true at position N) is a different table and a different question; one column
    -- could never have held both, which is the root of the five private notions of "gone".
    prior_status  text,
    new_status    text,
    actor_type    text        NOT NULL,
    actor_id      uuid,
    reason        text,
    occurred_at   timestamptz NOT NULL DEFAULT now()
);

-- The read this table exists for: one entity's history, newest first.
CREATE INDEX IF NOT EXISTS idx_ell_entity
    ON entity_lifecycle_ledger (entity_id, occurred_at DESC);
-- And the book-wide sweep (reconciliation, audit export).
CREATE INDEX IF NOT EXISTS idx_ell_book
    ON entity_lifecycle_ledger (book_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION entity_lifecycle_ledger_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'entity_lifecycle_ledger is append-only (attempted %); a ledger that can be rewritten is a cache, and this one is the audit trail for entity deletion',
        TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_ell_append_only ON entity_lifecycle_ledger;
CREATE TRIGGER trg_ell_append_only
    BEFORE UPDATE OR DELETE ON entity_lifecycle_ledger
    FOR EACH ROW EXECUTE FUNCTION entity_lifecycle_ledger_append_only();
`

// UpEntityLifecycleLedger creates the physical lifecycle ledger (T31).
//
// ⚠️ **NOT done here, and recorded rather than implied:** D5 also demotes
// `glossary_entities.deleted_at` and `.status` to *derived caches* of this table. That is a
// reader migration across the whole service — the same shape as T32's `alive` work — and
// doing it in the same step as creating the table would mean changing every consumer's read
// before a single ledger row exists to read. The columns stay authoritative for now; the
// ledger is written alongside them, so the history starts accumulating immediately and the
// demotion has something to be derived FROM when it happens.
func UpEntityLifecycleLedger(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-lifecycle-ledger", entityLifecycleLedgerSQL)
}
