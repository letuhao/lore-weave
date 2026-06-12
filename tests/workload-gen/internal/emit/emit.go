// Package emit writes a generated stream through the REAL Go outbox path so the
// whole base→derived pipeline runs (publisher drains outbox → Redis → Rust
// projections → 11 tables → integrity-checker).
//
// Each event is written in stream order, one transaction per event:
//
//	BEGIN → INSERT INTO events(…) → events.OutboxWrite(tx, …) → COMMIT
//
// matching the I13/Q-L1B-3 atomicity contract (tests/integration/outbox_atomicity_test.go)
// and reusing events.OutboxWrite verbatim (no SQL drift). Stream order is
// preserved — NOT reordered into per-aggregate batches — so cross-aggregate
// causality holds in the outbox (e.g. session.started is enqueued before the
// npc.said that updates its session-memory row).
package emit

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	events "github.com/loreweave/foundation/contracts/events"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

// insertEventsSQL mirrors the production event INSERT (the column set written by
// dp-kernel's append + the Go services). metadata is included so npc.said's
// session_id (read by the npc_session_memory projection) is durable.
const insertEventsSQL = `
INSERT INTO events (
	event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
	event_type, event_version, payload, metadata, occurred_at, recorded_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`

// writeEvent inserts one event + its outbox row using exec (the caller's open
// transaction). It does NOT begin/commit — atomicity is the caller's, matching
// events.OutboxWrite's contract.
func writeEvent(ctx context.Context, exec events.OutboxExecutor, e events.Envelope) error {
	payload, err := json.Marshal(e.Payload)
	if err != nil {
		return fmt.Errorf("emit: marshal payload for %s: %w", e.EventID, err)
	}
	var metadata any // NULL when the event has no metadata
	if e.Metadata != nil {
		mb, err := json.Marshal(e.Metadata)
		if err != nil {
			return fmt.Errorf("emit: marshal metadata for %s: %w", e.EventID, err)
		}
		metadata = mb
	}

	if _, err := exec.ExecContext(ctx, insertEventsSQL,
		e.EventID, e.RealityID, e.AggregateType, e.AggregateID, int64(e.AggregateVersion),
		e.EventType, int32(e.EventVersion), payload, metadata, e.OccurredAt, e.RecordedAt,
	); err != nil {
		return fmt.Errorf("emit: insert event %s: %w", e.EventID, err)
	}
	// Same transaction as the event INSERT (the atomicity contract).
	if err := events.OutboxWrite(ctx, exec, events.OutboxRow{EventID: e.EventID, RealityID: e.RealityID}); err != nil {
		return fmt.Errorf("emit: outbox %s: %w", e.EventID, err)
	}
	return nil
}

// Stream writes every event in s through the real outbox path, one transaction
// per event, in order. On any error the current event's transaction is rolled
// back and the error is returned (no partial event survives).
//
// The per-event write LOGIC is unit-tested via writeEvent (fake executor); this
// orchestration's begin/commit/rollback is exercised by the live-smoke
// (scripts/workload-gen-pipeline-smoke.sh), and the underlying event+outbox
// atomicity contract (rollback-on-partial-fail) is owned + tested by
// contracts/events (tests/integration/outbox_atomicity_test.go). We do not
// re-fake *sql.DB here.
func Stream(ctx context.Context, db *sql.DB, s gen.Stream) error {
	for i, e := range s {
		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			return fmt.Errorf("emit: begin tx for event %d: %w", i, err)
		}
		if err := writeEvent(ctx, tx, e); err != nil {
			_ = tx.Rollback()
			return err
		}
		if err := tx.Commit(); err != nil {
			return fmt.Errorf("emit: commit event %d (%s): %w", i, e.EventID, err)
		}
	}
	return nil
}
