// Package pgsource is the pgx-backed drain.Source/drain.Batch over meta_outbox.
//
// Begin opens ONE tx against the meta DB, runs the FOR UPDATE SKIP LOCKED batch
// SELECT, and returns a Batch whose Mark* methods UPDATE within that same tx.
// Commit closes it (releasing the locks). The pending scan re-derives the
// exponential backoff deadline inline from attempts + last_attempt_at (no
// next_attempt_at column needed) — identical to the publisher's pgsource.
package pgsource

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/drain"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

// Source binds the meta DB pool + the backoff policy the pending scan uses.
type Source struct {
	pool     *pgxpool.Pool
	baseSecs float64
	capSecs  float64
}

// New constructs a Source. The policy supplies the base/cap the pending scan
// uses to skip rows still inside their retry backoff.
func New(pool *pgxpool.Pool, policy retry.Policy) (*Source, error) {
	if pool == nil {
		return nil, errors.New("pgsource: nil pool")
	}
	if err := policy.Validate(); err != nil {
		return nil, fmt.Errorf("pgsource: %w", err)
	}
	return &Source{pool: pool, baseSecs: policy.BaseBackoff.Seconds(), capSecs: policy.MaxBackoff.Seconds()}, nil
}

const selectPendingSQL = `
SELECT event_id::text, event_name, aggregate_id, payload, xreality_topic, attempts, recorded_at_nanos
FROM meta_outbox
WHERE published = FALSE
  AND dead_lettered_at IS NULL
  AND (last_attempt_at IS NULL
       OR last_attempt_at + LEAST(
            make_interval(secs => $2 * power(2, GREATEST(attempts - 1, 0))),
            make_interval(secs => $3)) <= NOW())
ORDER BY enqueued_at ASC
LIMIT $1
FOR UPDATE SKIP LOCKED
`

// Begin opens the drain tx and SELECTs the locked batch.
func (s *Source) Begin(ctx context.Context, batchSize int) (drain.Batch, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("pgsource: begin tx: %w", err)
	}
	rows, err := tx.Query(ctx, selectPendingSQL, batchSize, s.baseSecs, s.capSecs)
	if err != nil {
		_ = tx.Rollback(ctx)
		return nil, fmt.Errorf("pgsource: select pending: %w", err)
	}
	out, scanErr := scanRows(rows)
	rows.Close()
	if scanErr != nil {
		_ = tx.Rollback(ctx)
		return nil, fmt.Errorf("pgsource: scan: %w", scanErr)
	}
	return &Batch{tx: tx, rows: out}, nil
}

func scanRows(rows pgx.Rows) ([]drain.Row, error) {
	var out []drain.Row
	for rows.Next() {
		var (
			r          drain.Row
			topic      *string
			payloadRaw []byte
		)
		if err := rows.Scan(&r.EventID, &r.EventName, &r.AggregateID, &payloadRaw, &topic, &r.Attempts, &r.RecordedAtNanos); err != nil {
			return nil, err
		}
		if topic != nil {
			r.XRealityTopic = *topic
		}
		// Carry the jsonb bytes through verbatim (no unmarshal→map→remarshal,
		// which would lose int64 precision). meta_outbox.payload is NOT NULL +
		// a jsonb object, so payloadRaw is always a valid non-empty object.
		r.Payload = append([]byte(nil), payloadRaw...)
		out = append(out, r)
	}
	return out, rows.Err()
}

// Batch holds the locked rows + the live tx.
type Batch struct {
	tx   pgx.Tx
	rows []drain.Row
}

func (b *Batch) Rows() []drain.Row { return b.rows }

// MarkPublished sets published=TRUE; attempts++ satisfies the
// published⇒attempts≥1 CHECK.
func (b *Batch) MarkPublished(ctx context.Context, eventID string) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE meta_outbox
		SET published = TRUE, attempts = attempts + 1, last_attempt_at = NOW()
		WHERE event_id = $1`, eventID)
	if err != nil {
		return fmt.Errorf("pgsource: MarkPublished %s: %w", eventID, err)
	}
	return nil
}

// MarkRetry records a transient failure (attempts already incremented by the
// caller) + last_error + last_attempt_at; the pending scan re-derives backoff.
func (b *Batch) MarkRetry(ctx context.Context, eventID string, attempts int, lastErr string) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE meta_outbox
		SET attempts = $2, last_error = $3, last_attempt_at = NOW()
		WHERE event_id = $1`, eventID, attempts, lastErr)
	if err != nil {
		return fmt.Errorf("pgsource: MarkRetry %s: %w", eventID, err)
	}
	return nil
}

// MarkDeadLetter sets dead_lettered_at so the row leaves the pending scan.
func (b *Batch) MarkDeadLetter(ctx context.Context, eventID string, attempts int, lastErr string) error {
	_, err := b.tx.Exec(ctx, `
		UPDATE meta_outbox
		SET attempts = $2, last_error = $3, last_attempt_at = NOW(), dead_lettered_at = NOW()
		WHERE event_id = $1`, eventID, attempts, lastErr)
	if err != nil {
		return fmt.Errorf("pgsource: MarkDeadLetter %s: %w", eventID, err)
	}
	return nil
}

func (b *Batch) Commit(ctx context.Context) error { return b.tx.Commit(ctx) }

// Rollback aborts the tx; tolerant of an already-committed tx (pgx.ErrTxClosed).
func (b *Batch) Rollback(ctx context.Context) error {
	err := b.tx.Rollback(ctx)
	if err != nil && !errors.Is(err, pgx.ErrTxClosed) {
		return err
	}
	return nil
}

var _ drain.Source = (*Source)(nil)
var _ drain.Batch = (*Batch)(nil)
