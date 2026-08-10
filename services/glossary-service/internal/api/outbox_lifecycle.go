package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Entity LIFECYCLE events — delete, restore, purge (plan T27).
//
// WHY THREE EVENTS AND NOT ONE
// -----------------------------
// Before this, all three lifecycle transitions were SILENT: `softDeleteEntityCore`,
// `bulkDeleteEntities`, `restoreEntityCore` and `purgeEntity` each mutated
// `glossary_entities` and emitted nothing. The downstream KG mirror therefore never
// learned about any of them — and the machinery to act on them already existed
// (`archive_entity` / `restore_entity` in knowledge-service's Neo4j repo), unused, because
// nothing ever told it.
//
// Emitting only `entity_deleted` would fix one third of that and leave the worse half in
// place: an entity restored from the recycle bin would stay ARCHIVED downstream forever,
// with the glossary showing it live. A user who deletes and undoes ends up with a split
// brain that no retry converges, because the corrective event does not exist. So the
// transitions are modelled as what they are — three distinct facts.
//
// `purged` is separate from `deleted` for the same reason: soft-delete is reversible and
// maps to "archive"; purge is not, and maps to a cascading delete. A consumer that received
// one event type for both would have to guess which, and would guess from a payload field —
// exactly the kind of inference an event type exists to make unnecessary.
//
// TRANSACTIONAL, ALWAYS
// ---------------------
// Every emit here is enlisted in the SAME transaction as the row mutation. The repo's own
// lore is blunt about the alternative: an emit outside the transaction produces a state
// change with no event when the process dies between them, which is precisely the silent
// divergence this task exists to remove. If the emit fails, the mutation rolls back with
// it — the write is not "mostly done".
const (
	entityDeletedEvent  = "glossary.entity_deleted"
	entityRestoredEvent = "glossary.entity_restored"
	entityPurgedEvent   = "glossary.entity_purged"
)

// entityLifecyclePayload is deliberately THIN. A delete carries no useful "after"
// snapshot — the interesting content is exactly what is going away — and a restore's
// content arrives via the `entity_updated` the consumer already handles. Shipping a fat
// snapshot here would invite consumers to treat a lifecycle event as a content event and
// then disagree with `entity_updated` about which is authoritative.
type entityLifecyclePayload struct {
	BookID           string `json:"book_id"`
	GlossaryEntityID string `json:"glossary_entity_id"`
	Op               string `json:"op"` // "deleted" | "restored" | "purged"
	ActorType        string `json:"actor_type"`
	ActorID          string `json:"actor_id,omitempty"`
	EmittedAt        string `json:"emitted_at"`
}

// lifecycleOpFor maps an event type to its payload `op`. Kept as a function rather than a
// map literal so an unknown event type is a compile-time-visible default rather than an
// empty string silently reaching a consumer.
func lifecycleOpFor(eventType string) string {
	switch eventType {
	case entityDeletedEvent:
		return "deleted"
	case entityRestoredEvent:
		return "restored"
	case entityPurgedEvent:
		return "purged"
	default:
		return "unknown"
	}
}

// actorFor renders an actor id as the (actor_type, actor_id) pair every entity event carries.
//
// `uuid.Nil` means "no user was on the call" — a pipeline, sweeper or system-seeded write —
// and must render as an EMPTY actor_id rather than the nil UUID, so a downstream owner-guard
// cannot mistake a fake all-zero user for a real one.
//
// The actor is a parameter everywhere it is used rather than read from ctx: the only ctx
// identity this service has (`userIDFromCtx`) is set by MCP middleware alone, so a REST write
// would silently record itself as a pipeline write. An audit trail that mislabels who did
// something is worse than one that says nothing.
func actorFor(actorID uuid.UUID) (actorType, actor string) {
	if actorID == uuid.Nil {
		return "pipeline", ""
	}
	return "user", actorID.String()
}

// emitEntityLifecycleTx writes ONE lifecycle event inside the caller's transaction.
//
// It does not check that the entity exists or is in the expected state: the caller has just
// mutated the row and holds the transaction, so its `RowsAffected() > 0` is a stronger
// statement than any re-read this function could make. Re-reading would also invite the
// bug it looks like it prevents — a check that passes because the caller's own uncommitted
// write is visible to it.
func emitEntityLifecycleTx(
	ctx context.Context,
	tx pgx.Tx,
	bookID, entityID uuid.UUID,
	eventType string,
	actorType, actorID string,
) error {
	if actorType != "user" {
		actorType = "pipeline"
	}
	payload := entityLifecyclePayload{
		BookID:           bookID.String(),
		GlossaryEntityID: entityID.String(),
		Op:               lifecycleOpFor(eventType),
		ActorType:        actorType,
		ActorID:          actorID,
		EmittedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("lifecycle outbox marshal: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('glossary', $1, $2, $3)`,
		entityID, eventType, payloadJSON,
	); err != nil {
		return fmt.Errorf("lifecycle outbox insert: %w", err)
	}
	slog.Debug("entity lifecycle emitted",
		"event_type", eventType, "entity_id", entityID.String(),
		"book_id", bookID.String(), "actor_type", actorType)
	return nil
}

// bulkDeleteEntitiesCore soft-deletes many entities in ONE transaction, emitting one
// `entity_deleted` per entity that actually changed (plan T27).
//
// The emission is driven by `RETURNING entity_id`, not by the caller's id list. The two
// differ precisely when an id was already deleted or belongs to another book — the cases
// where emitting would announce a deletion that never happened. The count returned to the
// caller comes from the same list, so the reported number and the events emitted cannot
// disagree with each other, which they could when the count came from `RowsAffected()` and
// the events from the input.
//
// Per-entity events rather than one bulk event: the consumers are per-entity (the KG
// archives one node at a time), so a bulk event would push the fan-out — and its
// partial-failure semantics — into every consumer.
func (s *Server) bulkDeleteEntitiesCore(
	ctx context.Context, bookID uuid.UUID, ids []uuid.UUID, actorID uuid.UUID,
) (int, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after a successful Commit

	rows, err := tx.Query(ctx,
		`UPDATE glossary_entities SET deleted_at = now(), updated_at = now()
		 WHERE book_id = $1 AND entity_id = ANY($2::uuid[]) AND deleted_at IS NULL
		 RETURNING entity_id`,
		bookID, ids)
	if err != nil {
		return 0, err
	}
	var changed []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return 0, err
		}
		changed = append(changed, id)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	actorType, actor := actorFor(actorID)
	for _, id := range changed {
		if err := emitEntityLifecycleTx(
			ctx, tx, bookID, id, entityDeletedEvent, actorType, actor,
		); err != nil {
			// The WHOLE batch rolls back, deliberately. A partial bulk delete that
			// committed the rows it managed to announce would leave the caller's count
			// wrong and the trash half-populated, with no record of which half.
			slog.Warn("bulk delete rolled back — outbox emit failed",
				"book_id", bookID.String(), "entity_id", id.String(), "error", err)
			return 0, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	slog.Debug("bulk entity delete emitted",
		"book_id", bookID.String(), "requested", len(ids), "deleted", len(changed))
	return len(changed), nil
}

// mutateEntityLifecycleTx is the whole T27 contract in one place: mutate the row and emit
// the matching event, atomically, or do neither.
//
// Every lifecycle caller goes through here rather than hand-rolling the pair, because the
// failure this task fixes is not "someone wrote the wrong SQL" — it is "someone wrote the
// SQL and forgot the event", four separate times, over months. A shape that makes the two
// separable is a shape that will be separated again.
//
// Returns found=false when the UPDATE matched nothing (already deleted, already live,
// nonexistent). No event is emitted in that case: an event announcing a transition that did
// not happen is worse than none, because a consumer would act on it.
func mutateEntityLifecycleTx(
	ctx context.Context,
	tx pgx.Tx,
	sql string,
	bookID, entityID uuid.UUID,
	eventType string,
	actorType, actorID string,
) (bool, error) {
	tag, err := tx.Exec(ctx, sql, entityID, bookID)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, nil
	}
	if err := emitEntityLifecycleTx(ctx, tx, bookID, entityID, eventType, actorType, actorID); err != nil {
		// WARN before returning: the caller rolls back, so the mutation is undone — but a
		// lifecycle write failing on its OUTBOX rather than its data is worth seeing
		// distinctly from a plain SQL error. This is the runtime twin of the static gate.
		slog.Warn("entity lifecycle mutation rolled back — outbox emit failed",
			"event_type", eventType, "entity_id", entityID.String(), "error", err)
		return false, err
	}
	return true, nil
}
