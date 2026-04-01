package tasks

import (
	"context"
	"log"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
)

type OutboxRelay struct {
	Sources    []config.OutboxSource
	SourcePools map[string]*pgxpool.Pool
	EventsPool *pgxpool.Pool
	Redis      *redis.Client
}

func (t *OutboxRelay) Name() string { return "outbox-relay" }

func (t *OutboxRelay) Run(ctx context.Context) error {
	log.Printf("[outbox-relay] starting with %d source(s)", len(t.Sources))

	// Poll fallback loop — LISTEN/NOTIFY will be added in D1-10
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("[outbox-relay] shutting down")
			return nil
		case <-ticker.C:
			for _, src := range t.Sources {
				pool, ok := t.SourcePools[src.Name]
				if !ok {
					continue
				}
				n, err := t.processSource(ctx, src.Name, pool)
				if err != nil {
					log.Printf("[outbox-relay] %s: error: %v", src.Name, err)
					continue
				}
				if n > 0 {
					log.Printf("[outbox-relay] %s: relayed %d events", src.Name, n)
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

		// Publish to Redis Stream
		streamKey := "loreweave:events:" + aggregateType
		err := t.Redis.XAdd(ctx, &redis.XAddArgs{
			Stream: streamKey,
			MaxLen: 10000,
			Approx: true,
			Values: map[string]any{
				"event_type":    eventType,
				"aggregate_id":  aggregateID,
				"payload":       string(payload),
				"source":        sourceName,
			},
		}).Err()
		if err != nil {
			log.Printf("[outbox-relay] %s: redis XADD failed for %x: %v", sourceName, id, err)
			pool.Exec(ctx, `UPDATE outbox_events SET retry_count=retry_count+1, last_error=$2 WHERE id=$1`, id, err.Error())
			continue
		}

		// Record in event_log (idempotent via UNIQUE constraint)
		t.EventsPool.Exec(ctx, `
INSERT INTO event_log (source_service, source_outbox_id, event_type, aggregate_type, aggregate_id, payload, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (source_service, source_outbox_id) DO NOTHING
`, sourceName+"-service", id, eventType, aggregateType, aggregateID, payload, createdAt)

		// Mark as published
		pool.Exec(ctx, `UPDATE outbox_events SET published_at=now() WHERE id=$1`, id)
		count++
	}

	return count, nil
}
