package api

import (
	"context"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Entity CURATION transitions — status change and kind reassignment (plan T28).
//
// WHAT T28 EXPECTED TO FIND, AND WHAT IS ACTUALLY HERE
// ----------------------------------------------------
// The plan names four `curation*Core` funcs and asks for them to converge. They already do:
// `curationStatusChangeCore` and friends are the MINT side, shared by the unified
// `glossary_propose_curation` and the legacy per-op tools. They write nothing — they mint a
// confirm card.
//
// The drift the plan predicted is one layer down, on the WRITE side, and it is real. Each
// curation transition has two entry points — a REST handler and a confirm effect — and both
// already route through one `*Core`. Of those four cores:
//
//	mergeEntitiesCore          emits entity_merged + entity_updated   ✅
//	restoreEntityRevisionCore  emits entity_updated                   ✅
//	bulkSetEntityStatusCore    emitted NOTHING                        ❌
//	reassignEntityKindCore     emitted NOTHING                        ❌
//
// WHY THE TWO SILENT ONES MATTER
// -------------------------------
// `status` is a LIVENESS predicate in this service, not a label. Every consumer-facing read
// filters `status = 'active'` alongside `deleted_at IS NULL` — the KG-facing canon reads in
// `knowledge_client.go`, the context reads in `server.go`, the wiki read. Setting an entity to
// `inactive` or `rejected` therefore removes it from every downstream read, and emitted
// nothing: the KG mirror keeps the node and keeps answering RAG queries about an entity the
// author retired. That is the same split brain T27 removed for delete/restore, reached by a
// different verb.
//
// A kind reassignment is milder but no less silent: `kind` is a field of the
// `glossary.entity_updated` payload the KG mirror stores, so an entity that moves from
// `species` to `character` keeps the old kind in the graph forever.
//
// WHY status_changed IS ITS OWN EVENT AND NOT A FIELD ON entity_updated
// ---------------------------------------------------------------------
// `entity_updated` is emitted from roughly a dozen write paths and means "the content
// changed, re-sync it". Hanging an archive/restore side effect off an optional `status` field
// would make every one of those paths a latent archive trigger the day somebody populates the
// field. T27 settled the general form of this question already: a consumer that has to infer
// WHICH transition happened from a payload field is exactly what an event type exists to make
// unnecessary.
//
// The kind reassignment goes the other way for the same reason — it IS a content change, the
// payload already carries `kind`, and the consumer already knows what to do with it. A new
// event there would be a second way to say something already said.
const entityStatusChangedEvent = "glossary.entity_status_changed"

// entityStatusChangedPayload carries BOTH statuses. The consumer's decision is
// "is the new status active", which needs only one of them — but `prior_status` is what makes
// the event auditable after the fact, and what lets a consumer added later distinguish
// draft→active (a first publication) from rejected→active (a reinstatement) without
// re-querying a service that may have moved on since.
type entityStatusChangedPayload struct {
	BookID           string `json:"book_id"`
	GlossaryEntityID string `json:"glossary_entity_id"`
	Status           string `json:"status"`
	PriorStatus      string `json:"prior_status"`
	ActorType        string `json:"actor_type"`
	ActorID          string `json:"actor_id,omitempty"`
	EmittedAt        string `json:"emitted_at"`
}

// emitEntityStatusChangedTx writes ONE status-change event inside the caller's transaction.
//
// Same contract as `emitEntityLifecycleTx`: enlisted in the transaction that made the change,
// so the write is never "mostly done". The caller has already established that the status
// actually moved — this function does not re-read, for the reason T27 records: a re-read would
// see the caller's own uncommitted write and prove nothing.
func emitEntityStatusChangedTx(
	ctx context.Context,
	tx pgx.Tx,
	bookID, entityID uuid.UUID,
	status, priorStatus string,
	actorType, actorID string,
) error {
	if actorType != "user" {
		actorType = "pipeline"
	}
	payload := entityStatusChangedPayload{
		BookID:           bookID.String(),
		GlossaryEntityID: entityID.String(),
		Status:           status,
		PriorStatus:      priorStatus,
		ActorType:        actorType,
		ActorID:          actorID,
		EmittedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	// The ledger row goes first, in this same transaction (plan T31 / D5). On THIS axis the
	// prior value is the whole point: `status` is a liveness predicate, so "went from active
	// to rejected" and "was created rejected" are different facts that the column alone cannot
	// tell apart afterwards.
	if err := appendLifecycleLedgerTx(ctx, tx, bookID, entityID,
		"status_changed", priorStatus, status, actorType, actorID, ""); err != nil {
		return err
	}
	return insertOutboxEventTx(ctx, func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}, entityID, entityStatusChangedEvent, payload,
		"book_id", bookID.String(), "status", status,
		"prior_status", priorStatus, "actor_type", actorType)
}

// setEntityStatusCore is the ONE place a curated status change is written.
//
// It reads the prior statuses `FOR UPDATE` before writing, rather than deriving them from the
// UPDATE's own `RETURNING`. Two reasons, and the second is the load-bearing one:
//
//  1. `RETURNING` on a self-joined UPDATE can be read as returning either the pre- or
//     post-update value depending on which alias you reach for. Correct, and one refactor away
//     from silently inverting.
//  2. Without the row lock, a concurrent writer can change the status between the read and the
//     write, and `prior_status` in the event becomes a confident lie. An audit field that is
//     wrong under concurrency is worse than an absent one.
//
// The returned count and the events emitted come from the SAME locked list, so — as in
// `bulkDeleteEntitiesCore` — the number reported to the caller and the events that reached the
// bus cannot disagree.
//
// Only entities whose status ACTUALLY moves are announced. Re-setting an entity to the status
// it already has is a no-op transition, and an event announcing a transition that did not
// happen is worse than none, because a consumer acts on it.
func (s *Server) setEntityStatusCore(
	ctx context.Context, bookID uuid.UUID, status string, ids []uuid.UUID, actorID uuid.UUID,
) (int, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after a successful Commit

	rows, err := tx.Query(ctx, `
		SELECT entity_id, status FROM glossary_entities
		 WHERE book_id = $1 AND entity_id = ANY($2::uuid[]) AND deleted_at IS NULL
		 ORDER BY entity_id
		 FOR UPDATE`,
		bookID, ids)
	if err != nil {
		return 0, err
	}
	type priorRow struct {
		id     uuid.UUID
		status string
	}
	var matched []priorRow
	for rows.Next() {
		var r priorRow
		if err := rows.Scan(&r.id, &r.status); err != nil {
			rows.Close()
			return 0, err
		}
		matched = append(matched, r)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}
	if len(matched) == 0 {
		return 0, nil
	}

	if _, err := tx.Exec(ctx, `
		UPDATE glossary_entities SET status = $1, updated_at = now()
		 WHERE book_id = $2 AND entity_id = ANY($3::uuid[]) AND deleted_at IS NULL`,
		status, bookID, ids,
	); err != nil {
		return 0, err
	}

	actorType, actor := actorFor(actorID)
	for _, r := range matched {
		if r.status == status {
			continue
		}
		if err := emitEntityStatusChangedTx(
			ctx, tx, bookID, r.id, status, r.status, actorType, actor,
		); err != nil {
			// The whole batch rolls back. A partial status change that committed only the
			// rows it managed to announce would leave the caller's count wrong and half the
			// entities retired with no record of which half — the same reasoning
			// `bulkDeleteEntitiesCore` uses.
			slog.Warn("status change rolled back — outbox emit failed",
				"book_id", bookID.String(), "entity_id", r.id.String(), "error", err)
			return 0, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return len(matched), nil
}
