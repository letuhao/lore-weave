package tasks

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
)

// streamMaxLen keys the Redis Stream MAXLEN per aggregate_type.
// Matches 101_DATA_RE_ENGINEERING_PLAN.md §"Stream MAXLEN budgets":
// chapter/glossary/generic run cool, chat spikes under active use.
var streamMaxLen = map[string]int64{
	"chapter":  10000,
	"chat":     50000,
	"glossary": 10000,
}

const defaultStreamMaxLen int64 = 10000

// maxLenFor returns the retention cap for an aggregate_type's Redis Stream,
// falling back to defaultStreamMaxLen for unknown types (e.g. "voice", "generic").
func maxLenFor(aggregateType string) int64 {
	if n, ok := streamMaxLen[aggregateType]; ok {
		return n
	}
	return defaultStreamMaxLen
}

// isUndefinedTable reports whether err is a Postgres "relation does not exist"
// (SQLSTATE 42P01). This fires during cold starts when the source service
// hasn't run its migrations yet — the relay should stay quiet and retry on
// the next tick rather than log an error every 30s.
func isUndefinedTable(err error) bool {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		return pgErr.Code == "42P01"
	}
	return false
}

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

	// tableMissing tracks which sources last reported 42P01 (undefined_table).
	// Used to log exactly once per cold-start transition instead of per poll.
	// The Run loop is single-goroutine so no mutex is needed.
	tableMissing map[string]bool
}

func (t *OutboxRelay) Name() string { return "outbox-relay" }

// noteTableState logs on transitions so cold-start and recovery are observable
// without spamming. Returns silently otherwise.
func (t *OutboxRelay) noteTableState(sourceName string, missing bool) {
	if t.tableMissing == nil {
		t.tableMissing = make(map[string]bool)
	}
	was := t.tableMissing[sourceName]
	switch {
	case missing && !was:
		slog.Info("outbox_events table not yet created — will retry quietly",
			"source", sourceName)
	case !missing && was:
		slog.Info("outbox_events table now available", "source", sourceName)
	}
	t.tableMissing[sourceName] = missing
}

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
					if isUndefinedTable(err) {
						// Source service hasn't migrated yet (or table was dropped).
						// Log once on transition; stay quiet on subsequent ticks.
						t.noteTableState(src.Name, true)
						continue
					}
					slog.Error("outbox-relay error", "source", src.Name, "error", err)
					continue
				}
				t.noteTableState(src.Name, false)
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

		// Publish to Redis Stream — MAXLEN sized per aggregate_type to
		// reflect expected throughput (chat spikes, others cool).
		streamKey := "loreweave:events:" + aggregateType
		err := t.Redis.XAdd(ctx, &redis.XAddArgs{
			Stream: streamKey,
			MaxLen: maxLenFor(aggregateType),
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
