package ledger

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

// LoadLog fetches the event store + outbox into an in-memory Log.
//
// It reads only the columns C3 reasons about, ordered by (recorded_at, event_id)
// — the spine's canonical event order. This is a thin adapter; the check logic
// (ledger.go, against.go) is what carries the coverage. LoadLog itself is
// exercised by the live pipeline smoke.
//
// SCOPE: LoadLog reads ALL realities and loads the whole log into memory, so
// `-verify` expects a DB containing exactly the seeded data (the smoke uses a
// fresh DB). A reality filter + streaming for production-scale logs is a future
// concern (the C3 ledger is a test tool, not a standing production sweep).
func LoadLog(ctx context.Context, db *sql.DB) (Log, error) {
	var log Log

	rows, err := db.QueryContext(ctx, `
		SELECT event_id, reality_id, aggregate_type, aggregate_id,
		       aggregate_version, event_type, recorded_at, payload
		FROM events
		ORDER BY recorded_at, event_id`)
	if err != nil {
		return Log{}, fmt.Errorf("ledger: query events: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var (
			e       EventRow
			version int64
			payload []byte
		)
		if err := rows.Scan(&e.EventID, &e.RealityID, &e.AggType, &e.AggID, &version, &e.EventType, &e.RecordedAt, &payload); err != nil {
			return Log{}, fmt.Errorf("ledger: scan event: %w", err)
		}
		e.Version = uint64(version)
		if err := json.Unmarshal(payload, &e.Payload); err != nil {
			return Log{}, fmt.Errorf("ledger: unmarshal payload %s: %w", e.EventID, err)
		}
		log.Events = append(log.Events, e)
	}
	if err := rows.Err(); err != nil {
		return Log{}, fmt.Errorf("ledger: events rows: %w", err)
	}

	orows, err := db.QueryContext(ctx, `SELECT event_id FROM events_outbox`)
	if err != nil {
		return Log{}, fmt.Errorf("ledger: query outbox: %w", err)
	}
	defer orows.Close()
	for orows.Next() {
		var id uuid.UUID
		if err := orows.Scan(&id); err != nil {
			return Log{}, fmt.Errorf("ledger: scan outbox: %w", err)
		}
		log.OutboxIDs = append(log.OutboxIDs, id)
	}
	if err := orows.Err(); err != nil {
		return Log{}, fmt.Errorf("ledger: outbox rows: %w", err)
	}
	return log, nil
}
