package api

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// insertOutboxEvent writes a transactional outbox event within the given tx.
// The outbox row lives in the same database as the mutation, ensuring atomicity.
// The worker-infra service polls/listens for new rows and relays them to Redis Streams.
func insertOutboxEvent(ctx context.Context, tx pgx.Tx, eventType string, aggregateID uuid.UUID, payload map[string]any) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("outbox marshal: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('chapter', $1, $2, $3)
	`, aggregateID, eventType, payloadJSON)
	if err != nil {
		return fmt.Errorf("outbox insert: %w", err)
	}
	return nil
}
