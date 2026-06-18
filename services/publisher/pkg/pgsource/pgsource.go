// Package pgsource is the pgx-backed implementation of poll_loop.Source /
// poll_loop.Batch.
//
// Each Begin opens ONE transaction against the reality's per-reality DB,
// runs the FOR UPDATE SKIP LOCKED batch SELECT (joining events_outbox →
// events for the wire envelope), and returns a Batch whose Mark* methods
// UPDATE within that same tx. Commit closes it (releasing the locks).
//
// The pending-scan WHERE honors the retry backoff WITHOUT a schema change:
// it re-derives the exponential deadline from `attempts` + `last_attempt_at`
// using the policy's base/cap, so a freshly-retried row stays invisible
// until its backoff elapses (events_outbox has no next_attempt_at column).
package pgsource

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// Source binds a set of per-reality pgx pools. Begin picks the pool for the
// requested reality and opens its drain transaction.
type Source struct {
	pools    map[string]*pgxpool.Pool
	baseSecs float64
	capSecs  float64
}

// New constructs a Source. pools maps reality_id → its connection pool (may
// be empty when no realities are active yet — Begin guards per-reality); the
// policy supplies the backoff base/cap the pending scan uses.
func New(pools map[string]*pgxpool.Pool, policy retry.Policy) (*Source, error) {
	if pools == nil {
		pools = map[string]*pgxpool.Pool{}
	}
	if err := policy.Validate(); err != nil {
		return nil, fmt.Errorf("pgsource: %w", err)
	}
	return &Source{
		pools:    pools,
		baseSecs: policy.BaseBackoff.Seconds(),
		capSecs:  policy.MaxBackoff.Seconds(),
	}, nil
}

const selectPendingSQL = `
SELECT o.event_id::text, o.reality_id::text, o.attempts,
       e.event_type, e.event_version, e.aggregate_type, e.aggregate_id,
       e.aggregate_version, e.occurred_at, e.recorded_at, e.payload, e.metadata
FROM events_outbox o
JOIN events e ON e.event_id = o.event_id
WHERE o.published = FALSE
  AND o.dead_lettered_at IS NULL
  AND (o.last_attempt_at IS NULL
       OR o.last_attempt_at + LEAST(
            make_interval(secs => $2 * power(2, GREATEST(o.attempts - 1, 0))),
            make_interval(secs => $3)) <= NOW())
ORDER BY o.enqueued_at ASC
LIMIT $1
FOR UPDATE OF o SKIP LOCKED
`

// Begin opens the per-reality drain tx and SELECTs the locked batch.
func (s *Source) Begin(ctx context.Context, realityID string, batchSize int) (poll_loop.Batch, error) {
	pool, ok := s.pools[realityID]
	if !ok {
		return nil, fmt.Errorf("pgsource: no pool for reality %s", realityID)
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("pgsource: begin tx reality=%s: %w", realityID, err)
	}

	rows, err := tx.Query(ctx, selectPendingSQL, batchSize, s.baseSecs, s.capSecs)
	if err != nil {
		_ = tx.Rollback(ctx)
		return nil, fmt.Errorf("pgsource: select pending reality=%s: %w", realityID, err)
	}

	out, scanErr := scanRows(rows)
	rows.Close()
	if scanErr != nil {
		_ = tx.Rollback(ctx)
		return nil, fmt.Errorf("pgsource: scan reality=%s: %w", realityID, scanErr)
	}

	return &Batch{tx: tx, rows: out}, nil
}

func scanRows(rows pgx.Rows) ([]types.OutboxRow, error) {
	var out []types.OutboxRow
	for rows.Next() {
		var (
			eventIDStr, realityIDStr  string
			attempts, eventVersion    int
			eventType, aggType, aggID string
			aggVersion                int64
			r                         types.OutboxRow
			payloadRaw, metadataRaw   []byte
		)
		if err := rows.Scan(
			&eventIDStr, &realityIDStr, &attempts,
			&eventType, &eventVersion, &aggType, &aggID,
			&aggVersion, &r.OccurredAt, &r.RecordedAt, &payloadRaw, &metadataRaw,
		); err != nil {
			return nil, err
		}
		eid, err := uuid.Parse(eventIDStr)
		if err != nil {
			return nil, fmt.Errorf("bad event_id %q: %w", eventIDStr, err)
		}
		rid, err := uuid.Parse(realityIDStr)
		if err != nil {
			return nil, fmt.Errorf("bad reality_id %q: %w", realityIDStr, err)
		}
		r.EventID = eid
		r.RealityID = rid
		r.Attempts = attempts
		r.EventType = eventType
		r.EventVersion = eventVersion
		r.AggregateType = aggType
		r.AggregateID = aggID
		r.AggregateVersion = uint64(aggVersion)
		if len(payloadRaw) > 0 {
			if err := json.Unmarshal(payloadRaw, &r.Payload); err != nil {
				return nil, fmt.Errorf("event %s: bad payload json: %w", eid, err)
			}
		}
		if len(metadataRaw) > 0 {
			if err := json.Unmarshal(metadataRaw, &r.Metadata); err != nil {
				return nil, fmt.Errorf("event %s: bad metadata json: %w", eid, err)
			}
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// Batch holds the locked rows + the live tx. Mark* UPDATE within the tx;
// Commit/Rollback close it.
type Batch struct {
	tx   pgx.Tx
	rows []types.OutboxRow
}

// Rows returns the locked pending rows.
func (b *Batch) Rows() []types.OutboxRow { return b.rows }

// MarkPublished sets published=TRUE; attempts++ satisfies the
// published⇒attempts≥1 CHECK on events_outbox.
func (b *Batch) MarkPublished(ctx context.Context, eventID string) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE events_outbox
		SET published = TRUE, attempts = attempts + 1, last_attempt_at = NOW()
		WHERE event_id = $1
	`, eventID)
	if err != nil {
		return fmt.Errorf("pgsource: MarkPublished %s: %w", eventID, err)
	}
	return nil
}

// MarkRetry records the transient failure (attempts already incremented by
// the caller) + last_error + last_attempt_at=NOW(). nextAttemptAt is unused
// here — the pending scan re-derives the backoff deadline from
// attempts+last_attempt_at.
func (b *Batch) MarkRetry(ctx context.Context, eventID string, attempts int, lastErr string, _ time.Time) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE events_outbox
		SET attempts = $2, last_error = $3, last_attempt_at = NOW()
		WHERE event_id = $1
	`, eventID, attempts, lastErr)
	if err != nil {
		return fmt.Errorf("pgsource: MarkRetry %s: %w", eventID, err)
	}
	return nil
}

// MarkDeadLetter sets dead_lettered_at=NOW() so the row leaves the scan.
func (b *Batch) MarkDeadLetter(ctx context.Context, eventID string, attempts int, lastErr string) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE events_outbox
		SET attempts = $2, last_error = $3, last_attempt_at = NOW(), dead_lettered_at = NOW()
		WHERE event_id = $1
	`, eventID, attempts, lastErr)
	if err != nil {
		return fmt.Errorf("pgsource: MarkDeadLetter %s: %w", eventID, err)
	}
	return nil
}

// Commit durably persists the batch + releases the SKIP-LOCKED locks.
func (b *Batch) Commit(ctx context.Context) error { return b.tx.Commit(ctx) }

// Rollback aborts the tx. Tolerant of an already-committed tx (pgx returns
// ErrTxClosed) so the poll loop's defensive double-call is a no-op.
func (b *Batch) Rollback(ctx context.Context) error {
	err := b.tx.Rollback(ctx)
	if err != nil && !errors.Is(err, pgx.ErrTxClosed) {
		return err
	}
	return nil
}
