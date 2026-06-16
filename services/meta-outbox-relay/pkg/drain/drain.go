// Package drain is the meta-outbox-relay's batch-drain core (P2/101 slice B).
//
// It drains the meta_outbox table (migration 030, written by MetaWrite's
// sdks/go/metaoutbox appender) to Redis Streams: every row goes to the home
// stream lw.meta.events, and a row carrying an xreality_topic ALSO goes to that
// cross-reality topic (feeding per-reality consumers like
// meta-worker/user_erased_writer, 071).
//
// One iteration:
//  1. Source.Begin opens a tx + SELECTs a batch of pending rows
//     FOR UPDATE SKIP LOCKED (V2-multi-replica safe; trivially safe at V1).
//  2. For each row: XADD to the home stream; if xreality_topic is set, XADD to
//     it too. Classify the outcome via the SHARED publisher retry.Policy →
//     MarkPublished / MarkRetry / MarkDeadLetter on the batch (same tx).
//  3. Batch.Commit closes the tx. Any error before commit → Rollback (rows
//     re-drain next tick — at-least-once; consumers are idempotent on event_id).
//
// ## Why the xreality bridge is required-when-set (NOT best-effort)
//
// The publisher's per-reality fanout treats the xreality XADD as non-fatal
// (the per-reality stream is authoritative). Here the cross-reality events are
// COMPLIANCE-critical (xreality.user.erased drives the GDPR Art.17 per-reality
// scrub). So when xreality_topic is set we mark published ONLY if BOTH the home
// and the xreality XADD succeed (both-or-neither). A transient failure retries
// the whole row, re-emitting to both streams — consumers dedupe on event_id.
package drain

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

// Row is one meta_outbox row's wire envelope + drain bookkeeping.
type Row struct {
	EventID     string
	EventName   string
	AggregateID string
	// Payload is the raw jsonb bytes from meta_outbox, carried through verbatim
	// to Redis. Kept as json.RawMessage (NOT map[string]any) on purpose: an
	// unmarshal→map→remarshal round-trip turns JSON numbers into float64, which
	// would silently lose precision for any int64 > 2^53 in a future event's
	// payload (/review-impl finding). Raw passthrough preserves it exactly.
	Payload         json.RawMessage
	XRealityTopic   string // "" ⇒ meta-only (home stream only)
	Attempts        int
	RecordedAtNanos int64
}

// Source begins a drain transaction over meta_outbox. The pgx impl
// (pkg/pgsource) runs the FOR UPDATE SKIP LOCKED batch SELECT; tests inject a fake.
type Source interface {
	Begin(ctx context.Context, batchSize int) (Batch, error)
}

// Batch is the locked pending rows + the state-write methods, all bound to one
// tx. Commit/Rollback release the SKIP-LOCKED locks.
type Batch interface {
	Rows() []Row
	MarkPublished(ctx context.Context, eventID string) error
	MarkRetry(ctx context.Context, eventID string, attempts int, lastErr string) error
	MarkDeadLetter(ctx context.Context, eventID string, attempts int, lastErr string) error
	Commit(ctx context.Context) error
	Rollback(ctx context.Context) error
}

// Emitter XADDs a row's envelope to a Redis Stream. Emit targets the home
// stream (lw.meta.events); EmitXReality targets the row's xreality_topic.
type Emitter interface {
	Emit(ctx context.Context, row Row) error
	EmitXReality(ctx context.Context, row Row) error
}

// Loop ties Source + Emitter + retry policy together. One iteration per Run().
type Loop struct {
	source    Source
	emitter   Emitter
	policy    retry.Policy
	batchSize int
}

// Config is the constructor input. All deps required; Policy validated;
// BatchSize defaults to 100 when <= 0.
type Config struct {
	Source    Source
	Emitter   Emitter
	Policy    retry.Policy
	BatchSize int
}

// New constructs a Loop.
func New(c Config) (*Loop, error) {
	if c.Source == nil {
		return nil, errors.New("drain: Source nil")
	}
	if c.Emitter == nil {
		return nil, errors.New("drain: Emitter nil")
	}
	if err := c.Policy.Validate(); err != nil {
		return nil, fmt.Errorf("drain: %w", err)
	}
	bs := c.BatchSize
	if bs <= 0 {
		bs = 100
	}
	return &Loop{source: c.Source, emitter: c.Emitter, policy: c.Policy, batchSize: bs}, nil
}

// IterationStats is the per-Run summary (metrics + tests).
type IterationStats struct {
	Fetched      int
	Published    int
	Retried      int
	DeadLettered int
	XRealityOK   int // rows that ALSO emitted to an xreality topic
}

// Run executes ONE drain iteration. Returns stats + the first error (after
// attempting the whole batch's commit/rollback).
func (l *Loop) Run(ctx context.Context) (IterationStats, error) {
	stats := IterationStats{}
	batch, err := l.source.Begin(ctx, l.batchSize)
	if err != nil {
		return stats, fmt.Errorf("drain: begin: %w", err)
	}
	rows := batch.Rows()
	stats.Fetched = len(rows)

	for _, row := range rows {
		if err := l.drainRow(ctx, batch, row, &stats); err != nil {
			_ = batch.Rollback(ctx)
			return stats, fmt.Errorf("drain: row %s: %w", row.EventID, err)
		}
	}
	if err := batch.Commit(ctx); err != nil {
		_ = batch.Rollback(ctx)
		return stats, fmt.Errorf("drain: commit: %w", err)
	}
	return stats, nil
}

// drainRow emits one row (home + required xreality bridge) and records the
// outcome on the batch. A Mark error is fatal for the batch (caller rolls back).
func (l *Loop) drainRow(ctx context.Context, batch Batch, row Row, stats *IterationStats) error {
	emitErr := l.emitter.Emit(ctx, row)
	// Both-or-neither: if the home XADD succeeded AND this row has an xreality
	// topic, the xreality XADD must ALSO succeed before we mark published.
	xrealityEmitted := false
	if emitErr == nil && row.XRealityTopic != "" {
		if xerr := l.emitter.EmitXReality(ctx, row); xerr != nil {
			emitErr = fmt.Errorf("xreality emit to %s: %w", row.XRealityTopic, xerr)
		} else {
			xrealityEmitted = true
		}
	}

	switch retry.Classify(l.policy, row.Attempts, emitErr) {
	case retry.MarkPublished:
		if err := batch.MarkPublished(ctx, row.EventID); err != nil {
			return fmt.Errorf("MarkPublished: %w", err)
		}
		stats.Published++
		if xrealityEmitted {
			stats.XRealityOK++
		}
	case retry.Retry:
		attempts := row.Attempts + 1
		if err := batch.MarkRetry(ctx, row.EventID, attempts, errString(emitErr)); err != nil {
			return fmt.Errorf("MarkRetry: %w", err)
		}
		stats.Retried++
	case retry.DeadLetter:
		attempts := row.Attempts + 1
		if err := batch.MarkDeadLetter(ctx, row.EventID, attempts, errString(emitErr)); err != nil {
			return fmt.Errorf("MarkDeadLetter: %w", err)
		}
		stats.DeadLettered++
	}
	return nil
}

// BackoffFor exposes the policy backoff for the caller's metrics/logging.
func (l *Loop) BackoffFor(attempts int) time.Duration { return retry.BackoffFor(l.policy, attempts) }

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
