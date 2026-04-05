package tasks

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
)

// uuidStr converts a [16]byte UUID to standard string format.
func uuidStr(b [16]byte) string {
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

type OutboxRelay struct {
	Sources    []config.OutboxSource
	SourcePools map[string]*pgxpool.Pool
	EventsPool *pgxpool.Pool
	Redis      *redis.Client
}

func (t *OutboxRelay) Name() string { return "outbox-relay" }

func (t *OutboxRelay) Run(ctx context.Context) error {
	slog.Info("outbox-relay starting", "sources", len(t.Sources))

	// Poll fallback loop — LISTEN/NOTIFY will be added in D1-10
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.Info("outbox-relay shutting down")
			return nil
		case <-ticker.C:
			for _, src := range t.Sources {
				pool, ok := t.SourcePools[src.Name]
				if !ok {
					continue
				}
				n, err := t.processSource(ctx, src.Name, pool)
				if err != nil {
					slog.Error("outbox-relay error", "source", src.Name, "error", err)
					continue
				}
				if n > 0 {
					slog.Info("outbox-relay relayed events", "source", src.Name, "count", n)
				}
			}
		}
	}
}

func (t *OutboxRelay) processSource(ctx context.Context, sourceName string, pool *pgxpool.Pool) (int, error) {
	rows, err := pool.Query(ctx, `
SELECT id, event_type, aggregate_type, aggregate_id, payload, created_at
FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at
LIMIT 100
`)
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		var id, aggregateID [16]byte
		var eventType, aggregateType string
		var payload []byte
		var createdAt time.Time

		if err := rows.Scan(&id, &eventType, &aggregateType, &aggregateID, &payload, &createdAt); err != nil {
			return count, err
		}

		// Convert UUIDs from [16]byte to string for Redis and logging
		idStr := uuidStr(id)
		aggIDStr := uuidStr(aggregateID)

		// Publish to Redis Stream
		streamKey := "loreweave:events:" + aggregateType
		err := t.Redis.XAdd(ctx, &redis.XAddArgs{
			Stream: streamKey,
			MaxLen: 10000,
			Approx: true,
			Values: map[string]any{
				"event_type":    eventType,
				"aggregate_id":  aggIDStr,
				"payload":       string(payload),
				"source":        sourceName,
			},
		}).Err()
		if err != nil {
			slog.Error("outbox-relay redis XADD failed", "source", sourceName, "id", idStr, "error", err)
			pool.Exec(ctx, `UPDATE outbox_events SET retry_count=retry_count+1, last_error=$2 WHERE id=$1`, id, err.Error())
			continue
		}

		// Record in event_log (idempotent via UNIQUE constraint)
		t.EventsPool.Exec(ctx, `
INSERT INTO event_log (source_service, source_outbox_id, event_type, aggregate_type, aggregate_id, payload, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (source_service, source_outbox_id) DO NOTHING
`, sourceName+"-service", idStr, eventType, aggregateType, aggIDStr, payload, createdAt)

		// Mark as published
		pool.Exec(ctx, `UPDATE outbox_events SET published_at=now() WHERE id=$1`, id)
		count++
	}

	return count, nil
}
