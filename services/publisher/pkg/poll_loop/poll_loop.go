// Package poll_loop is the publisher's batch-drain core.
//
// One iteration (per reality):
//  1. Leader check (Q-L2-5 V1 no-op).
//  2. Source.Begin opens a TX and SELECTs a batch of pending outbox rows
//     with FOR UPDATE SKIP LOCKED (R06 §12F.4 — multi-replica safe at V2+,
//     trivially safe at V1). The TX is held open for the whole batch.
//  3. For each row, attempt XADD to the per-reality Redis Stream.
//  4. Classify outcome via retry.Classify → MarkPublished / Retry / DeadLetter
//     on the BATCH (same TX as the locking SELECT — Q-L1B-3 atomicity).
//  5. If a row carries `cross_reality: true` AND XADD succeeded — invoke the
//     L2.L xreality fanout (also XADDs to `xreality.<type>`).
//  6. Batch.Commit closes the TX (releasing the SKIP-LOCKED locks). Any
//     error before commit → Batch.Rollback (rows re-drain next tick;
//     at-least-once is the accepted outbox semantic — consumers are
//     idempotent on event_id).
//
// Every IO sink is abstracted as an interface. Production wiring binds pgx
// (Source/Batch) + redis (Emitter/Fanout); tests use in-memory fakes.
//
// ## Transaction model (D-PUBLISHER-LIVE-WIRING / DEFERRED 054)
//
// The Source→Batch split (replacing the old Fetcher+StateWriter pair) makes
// the SELECT … FOR UPDATE SKIP LOCKED and the row UPDATEs share ONE tx per
// reality. This is what makes the SKIP-LOCKED lock load-bearing: at V2+
// multi-replica, a second publisher cannot re-fetch+re-XADD a row another
// replica is mid-draining. The XADD happens BEFORE commit, so a crash
// between XADD and commit re-publishes the row next tick (at-least-once).
package poll_loop

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// Source begins a per-reality drain transaction. The concrete impl
// (pkg/pgsource) opens a pgx tx against the reality's DB and runs the
// FOR UPDATE SKIP LOCKED batch SELECT; tests inject an in-memory fake.
type Source interface {
	// Begin opens a tx for realityID, SELECTs up to batchSize pending outbox
	// rows FOR UPDATE SKIP LOCKED, and returns a Batch bound to that tx. The
	// caller MUST eventually call Batch.Commit or Batch.Rollback exactly once.
	Begin(ctx context.Context, realityID string, batchSize int) (Batch, error)
}

// Batch is a per-reality drain unit: the locked rows plus the state-write
// methods, ALL bound to one transaction. The locks held by the SELECT are
// released by Commit/Rollback.
type Batch interface {
	// Rows returns the locked pending rows for this reality (oldest first).
	Rows() []types.OutboxRow
	// MarkPublished sets published=TRUE (attempts++) for the row.
	MarkPublished(ctx context.Context, eventID string) error
	// MarkRetry records a transient failure (attempts, last_error). nextAttemptAt
	// is informational for the caller's metrics; the pg scan re-derives the
	// backoff deadline from attempts+last_attempt_at.
	MarkRetry(ctx context.Context, eventID string, attempts int, lastErr string, nextAttemptAt time.Time) error
	// MarkDeadLetter sets dead_lettered_at (row excluded from future scans).
	MarkDeadLetter(ctx context.Context, eventID string, attempts int, lastErr string) error
	// Commit closes the tx, durably persisting every Mark in this batch and
	// releasing the SKIP-LOCKED locks.
	Commit(ctx context.Context) error
	// Rollback aborts the tx (no Mark persists). Safe to call after Commit
	// (no-op / ErrTxDone-tolerant in the pg impl).
	Rollback(ctx context.Context) error
}

// Emitter XADDs an envelope to the per-reality Redis Stream
// `lw.events.<reality_id>`. Returns nil on success, error on Redis
// failure / circuit-break.
type Emitter interface {
	Emit(ctx context.Context, row types.OutboxRow) error
}

// XRealityFanout is the L2.L hand-off: when the row's metadata carries
// `cross_reality: true`, the publisher ALSO XADDs to
// `xreality.<event_type>` so meta-worker (sole consumer per I7) can
// dispatch. Returning an error here is NON-fatal for the main stream
// (the per-reality XADD already succeeded); we log + count a metric.
type XRealityFanout interface {
	Fanout(ctx context.Context, row types.OutboxRow) error
}

// ModeReader exposes the publisher's current ServiceMode (set by the
// heartbeat loop). The poll loop uses this for L1.J degraded-mode gating:
// at ModeEssentials+ we PAUSE the drain (background workers off).
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// Loop ties everything together. The caller (cmd/publisher) builds one
// Loop per shard host and invokes Run() on a ticker (default 1s).
type Loop struct {
	leader    leader_election.Leader
	source    Source
	emitter   Emitter
	fanout    XRealityFanout
	mode      ModeReader
	policy    retry.Policy
	batchSize int
	realities []string
}

// Config is the constructor input.
type Config struct {
	Leader    leader_election.Leader
	Source    Source
	Emitter   Emitter
	Fanout    XRealityFanout
	Mode      ModeReader
	Policy    retry.Policy
	BatchSize int
	// Realities is the per-shard list of reality_ids this publisher
	// drains. In V1 this is loaded from reality_registry at startup.
	Realities []string
}

// New constructs a Loop. All deps MUST be non-nil; Policy validated;
// BatchSize defaults to 100 when <= 0.
func New(c Config) (*Loop, error) {
	if c.Leader == nil {
		return nil, errors.New("poll_loop: Leader nil")
	}
	if c.Source == nil {
		return nil, errors.New("poll_loop: Source nil")
	}
	if c.Emitter == nil {
		return nil, errors.New("poll_loop: Emitter nil")
	}
	if c.Fanout == nil {
		return nil, errors.New("poll_loop: Fanout nil")
	}
	if c.Mode == nil {
		return nil, errors.New("poll_loop: Mode nil")
	}
	if err := c.Policy.Validate(); err != nil {
		return nil, fmt.Errorf("poll_loop: %w", err)
	}
	bs := c.BatchSize
	if bs <= 0 {
		bs = 100
	}
	return &Loop{
		leader:    c.Leader,
		source:    c.Source,
		emitter:   c.Emitter,
		fanout:    c.Fanout,
		mode:      c.Mode,
		policy:    c.Policy,
		batchSize: bs,
		realities: c.Realities,
	}, nil
}

// IterationStats is the per-Run summary. Used by tests + metrics.
type IterationStats struct {
	Fetched       int
	Published     int
	Retried       int
	DeadLettered  int
	FanoutOK      int
	FanoutErr     int
	RealityErrors int  // realities whose drain tx failed (infra error)
	Skipped       bool // true when leader=false OR mode degraded
	SkipReason    string
}

// Run executes ONE drain iteration across all known realities. Returns
// per-iteration stats so the caller can emit metrics + the tests can
// assert.
//
// Skips entirely when:
//   - Leader.IsLeader() == false  (V2+ failover; V1 no-op always true)
//   - mode.Mode() >= ModeEssentials (L1.J degraded gating)
func (l *Loop) Run(ctx context.Context) (IterationStats, error) {
	stats := IterationStats{}

	if !l.leader.IsLeader() {
		stats.Skipped = true
		stats.SkipReason = "not_leader"
		return stats, nil
	}
	if l.mode.Mode() >= lifecycle.ModeEssentials {
		stats.Skipped = true
		stats.SkipReason = fmt.Sprintf("degraded_mode=%s", l.mode.Mode())
		return stats, nil
	}

	// Per-reality isolation: one reality's DB being unreachable must NOT
	// starve the others. We attempt every reality, count the failures, and
	// return the FIRST error so the caller can log/alert — but only after
	// trying them all.
	var firstErr error
	for _, reality := range l.realities {
		if err := l.drainReality(ctx, reality, &stats); err != nil {
			stats.RealityErrors++
			if firstErr == nil {
				firstErr = err
			}
		}
	}

	return stats, firstErr
}

// drainReality opens one tx for the reality, drains its locked batch, and
// commits. Any error before commit rolls the tx back (rows re-drain next
// tick — at-least-once).
func (l *Loop) drainReality(ctx context.Context, reality string, stats *IterationStats) error {
	batch, err := l.source.Begin(ctx, reality, l.batchSize)
	if err != nil {
		return fmt.Errorf("begin reality=%s: %w", reality, err)
	}
	rows := batch.Rows()
	stats.Fetched += len(rows)

	for _, row := range rows {
		if err := l.drainRow(ctx, batch, row, stats); err != nil {
			_ = batch.Rollback(ctx)
			return fmt.Errorf("drain reality=%s event=%s: %w", reality, row.EventID, err)
		}
	}

	if err := batch.Commit(ctx); err != nil {
		_ = batch.Rollback(ctx)
		return fmt.Errorf("commit reality=%s: %w", reality, err)
	}
	return nil
}

// drainRow emits one row, classifies the outcome, and records the resulting
// state on the batch. A Mark error is fatal for the reality batch (the caller
// rolls back); a fanout error is non-fatal (counted only).
func (l *Loop) drainRow(ctx context.Context, batch Batch, row types.OutboxRow, stats *IterationStats) error {
	xerr := l.emitter.Emit(ctx, row)
	switch retry.Classify(l.policy, row.Attempts, xerr) {
	case retry.MarkPublished:
		if err := batch.MarkPublished(ctx, row.EventID.String()); err != nil {
			return fmt.Errorf("MarkPublished: %w", err)
		}
		stats.Published++
		// L2.L: fanout xreality AFTER the per-reality XADD succeeds.
		if row.CrossReality() {
			if ferr := l.fanout.Fanout(ctx, row); ferr != nil {
				stats.FanoutErr++ // non-fatal
			} else {
				stats.FanoutOK++
			}
		}
	case retry.Retry:
		attempts := row.Attempts + 1
		next := time.Now().Add(retry.BackoffFor(l.policy, attempts))
		if err := batch.MarkRetry(ctx, row.EventID.String(), attempts, errString(xerr), next); err != nil {
			return fmt.Errorf("MarkRetry: %w", err)
		}
		stats.Retried++
	case retry.DeadLetter:
		attempts := row.Attempts + 1
		if err := batch.MarkDeadLetter(ctx, row.EventID.String(), attempts, errString(xerr)); err != nil {
			return fmt.Errorf("MarkDeadLetter: %w", err)
		}
		stats.DeadLettered++
	}
	return nil
}

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
