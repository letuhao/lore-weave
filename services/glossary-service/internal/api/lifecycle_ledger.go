package api

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// appendLifecycleLedgerTx writes ONE row to the physical lifecycle ledger (plan T31 / D5).
//
// WHY IT TAKES A tx AND NOT A POOL
// --------------------------------
// The whole point is that the ledger row cannot exist without the mutation and the mutation
// cannot exist without the ledger row. Handing this a pool would let it commit independently,
// which recreates exactly the divergence the ledger is meant to make impossible — the same
// argument `outbox_lifecycle.go` makes for the event, one table over.
//
// `prior`/`next`/`reason` are empty for the delete/restore/purge axis, where the op IS the
// transition and there is no meaningful "from" value; they carry real values on the curation
// axis (`status_changed`), where the interesting fact is precisely what it changed FROM. They
// are written as SQL NULL rather than ” so "not applicable" and "empty string" stay
// distinguishable — a distinction the recycle-bin/status split has already cost this repo once.
func appendLifecycleLedgerTx(
	ctx context.Context,
	tx pgx.Tx,
	bookID, entityID uuid.UUID,
	op, prior, next, actorType, actorID, reason string,
) error {
	nullable := func(s string) any {
		if s == "" {
			return nil
		}
		return s
	}
	var actor any
	if actorID != "" {
		actor = actorID
	}
	_, err := tx.Exec(ctx, `
		INSERT INTO entity_lifecycle_ledger
		    (entity_id, book_id, op, prior_status, new_status, actor_type, actor_id, reason)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
		entityID, bookID, op, nullable(prior), nullable(next), actorType, actor, nullable(reason))
	return err
}
