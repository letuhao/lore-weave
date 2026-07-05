package tasks

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
)

// notifyAggregateType marks an outbox row whose payload is a notification-service
// ingest body ({user_id, category, title, body, metadata, message_key,
// message_params, dedup_key}). D-C-PRODUCER-OUTBOX: instead of the Redis fan-out
// (nothing consumes loreweave:events:notification), the relay DELIVERS these rows to
// notification-service's /internal/notifications ingest — turning the 3 producers'
// former fire-and-forget-swallow POST into a durable outbox+retry drain, idempotent
// via the payload's dedup_key. The relay's existing published_at/retry_count give
// at-least-once for free; this is the "relay calls HTTP for notification-typed rows"
// path the P2·C spec lists (reuses the ingest unchanged, no new consumer/contract).
const notifyAggregateType = "notification"

// streamMaxLen keys the Redis Stream MAXLEN per aggregate_type.
// Matches 101_DATA_RE_ENGINEERING_PLAN.md §"Stream MAXLEN budgets":
// chapter/generic run cool, chat spikes under active use.
//
// glossary + knowledge feed learning-service's append-only correction log
// (Phase B, docs/specs/2026-05-31-phase-b-correction-capture.md §10.1).
// Corrections are eval-grade history, NOT re-derivable like glossary_sync, so
// MAXLEN trim must not drop unread events during a learning-service outage —
// hence a large budget here (trim-before-consume effectively impossible inside
// any realistic outage; the event_log + ReplayCorrections task is the backstop).
var streamMaxLen = map[string]int64{
	"chapter":   10000,
	"chat":      50000,
	"glossary":  200000,
	"knowledge": 200000,
	// Unified Job Control Plane — job-lifecycle events (loreweave:events:jobs) are
	// frequent (every status transition across all worker services) but small + the
	// jobs-service projection is a mirror (re-derivable via the reconcile sweep), so a
	// moderate cap is fine.
	"jobs": 50000,
}

const defaultStreamMaxLen int64 = 10000

// relayStreamValues builds the Redis Stream field map for one relayed event.
//
// `outbox_id` = the producer's outbox row PK. It is stable across relay
// re-emission of the same row (unlike the Redis message_id, which changes on
// re-emit), so it is the end-to-end idempotency key for consumers that must
// dedup an append-only log (e.g. learning-service's corrections). Phase B §4.0.
// Additive: existing consumers ignore the unknown field.
func relayStreamValues(eventType, aggregateID, payload, source, outboxID string) map[string]any {
	return map[string]any{
		"event_type":   eventType,
		"aggregate_id": aggregateID,
		"payload":      payload,
		"source":       source,
		"outbox_id":    outboxID,
	}
}

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

	// NotifyURL + InternalToken address notification-service's /internal/notifications
	// ingest for notification-typed outbox rows (D-C-PRODUCER-OUTBOX). Empty NotifyURL
	// disables delivery (rows stay unpublished until configured — never dropped).
	NotifyURL     string
	InternalToken string
	// NotifyDeliver is injectable for tests; nil ⇒ the built-in HTTP deliverer.
	// Returns (permanent, err): err==nil is success; a permanent error (4xx reject)
	// is a poison row that must NOT retry forever; a transient error (5xx/network)
	// leaves the row unpublished for the next tick.
	NotifyDeliver func(ctx context.Context, payload []byte) (permanent bool, err error)
	httpClient    *http.Client

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

		// Notification-typed rows are DELIVERED to notification-service, not fanned
		// out to Redis (nothing consumes loreweave:events:notification). Durable +
		// idempotent (dedup_key in the payload); transient failure retries next tick.
		if aggregateType == notifyAggregateType {
			if t.deliverNotification(ctx, sourceName, idStr, payload, pool) {
				count++
			}
			continue
		}

		// Publish to Redis Stream — MAXLEN sized per aggregate_type to
		// reflect expected throughput (chat spikes, others cool).
		streamKey := "loreweave:events:" + aggregateType
		err := t.Redis.XAdd(ctx, &redis.XAddArgs{
			Stream: streamKey,
			MaxLen: maxLenFor(aggregateType),
			Approx: true,
			Values: relayStreamValues(eventType, aggIDStr, string(payload), sourceName, idStr),
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

// deliverNotification drains one notification-typed outbox row to notification-service.
// Returns true iff the row is now terminal (published) — success OR a permanent 4xx
// reject (dropped so a poison row can't spin forever). A transient failure returns
// false: the row stays unpublished (retry_count bumped) for the next poll.
func (t *OutboxRelay) deliverNotification(ctx context.Context, sourceName, idStr string, payload []byte, pool *pgxpool.Pool) bool {
	deliver := t.NotifyDeliver
	if deliver == nil {
		deliver = t.httpNotifyDeliver
	}
	permanent, err := deliver(ctx, payload)
	if err == nil {
		pool.Exec(ctx, `UPDATE outbox_events SET published_at=now() WHERE id=$1`, idStr)
		return true
	}
	if permanent {
		// 4xx reject (malformed/unknown category) — mark published + record why, so
		// it stops re-polling. Losing a malformed notification beats an infinite loop.
		slog.Error("outbox-relay notification permanently rejected — dropping",
			"source", sourceName, "id", idStr, "error", err)
		pool.Exec(ctx, `UPDATE outbox_events SET published_at=now(), last_error=$2 WHERE id=$1`, idStr, err.Error())
		return true
	}
	// Transient (5xx / network / notification-service down) — keep for the next tick.
	pool.Exec(ctx, `UPDATE outbox_events SET retry_count=retry_count+1, last_error=$2 WHERE id=$1`, idStr, err.Error())
	return false
}

// classifyNotifyStatus maps an HTTP status from the notification ingest to the relay's
// three outcomes. 2xx (incl. the idempotent-dedup and opt-out-suppressed 200s) = success;
// 429 / 5xx = transient (retry); any other 4xx = permanent reject (drop, don't loop).
func classifyNotifyStatus(code int) (success bool, permanent bool) {
	switch {
	case code >= 200 && code < 300:
		return true, false
	case code == http.StatusTooManyRequests || code >= 500:
		return false, false
	default:
		return false, true
	}
}

// httpNotifyDeliver POSTs a notification outbox payload to notification-service's
// internal ingest. The payload is already the exact ingest body, so it is forwarded
// verbatim (the producer owns the shape + the dedup_key).
func (t *OutboxRelay) httpNotifyDeliver(ctx context.Context, payload []byte) (bool, error) {
	if t.NotifyURL == "" {
		// Delivery not configured — treat as transient so the row is preserved
		// (never dropped) until a NotifyURL is set.
		return false, errors.New("notification delivery not configured (NOTIFICATION_SERVICE_URL unset)")
	}
	if t.httpClient == nil {
		t.httpClient = &http.Client{Timeout: 10 * time.Second}
	}
	url := t.NotifyURL + "/internal/notifications"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return true, fmt.Errorf("build notify request: %w", err) // malformed URL is permanent
	}
	req.Header.Set("Content-Type", "application/json")
	if t.InternalToken != "" {
		req.Header.Set("X-Internal-Token", t.InternalToken)
	}
	resp, err := t.httpClient.Do(req)
	if err != nil {
		return false, fmt.Errorf("notify POST: %w", err) // network/timeout is transient
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(resp.Body, 1<<16))
	success, permanent := classifyNotifyStatus(resp.StatusCode)
	if success {
		return false, nil
	}
	return permanent, fmt.Errorf("notification ingest returned %d", resp.StatusCode)
}
