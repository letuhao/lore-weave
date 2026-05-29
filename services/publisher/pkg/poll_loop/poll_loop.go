// Package poll_loop is the publisher's batch-drain core.
//
// One iteration:
//  1. Leader check (Q-L2-5 V1 no-op).
//  2. SELECT batch of pending outbox rows per reality with FOR UPDATE
//     SKIP LOCKED (R06 §12F.4 — multi-replica safe at V2+, trivially safe
//     at V1).
//  3. For each row, attempt XADD to the per-reality Redis Stream.
//  4. Classify outcome via retry.Classify → MarkPublished / Retry / DeadLetter.
//  5. UPDATE the outbox row state (publisher.UpdateOutboxState).
//  6. If row carries `cross_reality: true` AND XADD succeeded — invoke
//     the L2.L xreality fanout (also XADDs to `xreality.<type>`).
//
// Every IO sink is abstracted as an interface. Production wiring (cycle 11+)
// binds pgx + redis; tests use in-memory fakes.
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

// Fetcher pulls a batch of pending outbox rows from one per-reality DB.
// FOR UPDATE SKIP LOCKED is the responsibility of the impl — the publisher
// loop trusts that any returned row is exclusively held until UpdateOutbox
// is called.
type Fetcher interface {
	FetchPending(ctx context.Context, realityID string, batchSize int) ([]types.OutboxRow, error)
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

// StateWriter updates the outbox row post-attempt. Called for each row
// EXACTLY ONCE per loop iteration. Atomicity is at the row level — the
// SELECT … FOR UPDATE SKIP LOCKED + the UPDATE happen in the same TX.
type StateWriter interface {
	MarkPublished(ctx context.Context, eventID string) error
	MarkRetry(ctx context.Context, eventID string, attempts int, lastErr string, nextAttemptAt time.Time) error
	MarkDeadLetter(ctx context.Context, eventID string, attempts int, lastErr string) error
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
	leader     leader_election.Leader
	fetcher    Fetcher
	emitter    Emitter
	fanout     XRealityFanout
	stateW     StateWriter
	mode       ModeReader
	policy     retry.Policy
	batchSize  int
	realities  []string
}

// Config is the constructor input.
type Config struct {
	Leader    leader_election.Leader
	Fetcher   Fetcher
	Emitter   Emitter
	Fanout    XRealityFanout
	StateW    StateWriter
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
	if c.Fetcher == nil {
		return nil, errors.New("poll_loop: Fetcher nil")
	}
	if c.Emitter == nil {
		return nil, errors.New("poll_loop: Emitter nil")
	}
	if c.Fanout == nil {
		return nil, errors.New("poll_loop: Fanout nil")
	}
	if c.StateW == nil {
		return nil, errors.New("poll_loop: StateW nil")
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
		fetcher:   c.Fetcher,
		emitter:   c.Emitter,
		fanout:    c.Fanout,
		stateW:    c.StateW,
		mode:      c.Mode,
		policy:    c.Policy,
		batchSize: bs,
		realities: c.Realities,
	}, nil
}

// IterationStats is the per-Run summary. Used by tests + metrics.
type IterationStats struct {
	Fetched      int
	Published    int
	Retried      int
	DeadLettered int
	FanoutOK     int
	FanoutErr    int
	Skipped      bool // true when leader=false OR mode degraded
	SkipReason   string
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

	for _, reality := range l.realities {
		rows, err := l.fetcher.FetchPending(ctx, reality, l.batchSize)
		if err != nil {
			return stats, fmt.Errorf("fetch reality=%s: %w", reality, err)
		}
		stats.Fetched += len(rows)
		for _, row := range rows {
			xerr := l.emitter.Emit(ctx, row)
			decision := retry.Classify(l.policy, row.Attempts, xerr)
			switch decision {
			case retry.MarkPublished:
				if err := l.stateW.MarkPublished(ctx, row.EventID.String()); err != nil {
					return stats, fmt.Errorf("MarkPublished %s: %w", row.EventID, err)
				}
				stats.Published++
				// L2.L: fanout xreality AFTER the per-reality XADD succeeds.
				if row.CrossReality() {
					if ferr := l.fanout.Fanout(ctx, row); ferr != nil {
						// Non-fatal: log + count.
						stats.FanoutErr++
					} else {
						stats.FanoutOK++
					}
				}
			case retry.Retry:
				attempts := row.Attempts + 1
				next := time.Now().Add(retry.BackoffFor(l.policy, attempts))
				errStr := ""
				if xerr != nil {
					errStr = xerr.Error()
				}
				if err := l.stateW.MarkRetry(ctx, row.EventID.String(), attempts, errStr, next); err != nil {
					return stats, fmt.Errorf("MarkRetry %s: %w", row.EventID, err)
				}
				stats.Retried++
			case retry.DeadLetter:
				attempts := row.Attempts + 1
				errStr := ""
				if xerr != nil {
					errStr = xerr.Error()
				}
				if err := l.stateW.MarkDeadLetter(ctx, row.EventID.String(), attempts, errStr); err != nil {
					return stats, fmt.Errorf("MarkDeadLetter %s: %w", row.EventID, err)
				}
				stats.DeadLettered++
			}
		}
	}

	return stats, nil
}
