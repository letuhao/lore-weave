// Package outbox_pruner addresses D-OUTBOX-PRUNE (deferred row 055).
//
// `events_outbox` rows accumulate as the publisher drains. Without pruning
// the table grows unboundedly. This package prunes published rows past the
// configured grace window.
//
// SAFETY INVARIANTS (enforced by tests):
//
//  1. NEVER delete rows where `dead_lettered_at IS NOT NULL` — those are
//     SRE-triage queue (runbooks/publisher/lag.md). Auto-pruning them would
//     silently drop incident-investigation evidence.
//  2. NEVER delete rows where `published = FALSE` — those are pending
//     publisher work. Deleting them would silently drop unpublished events.
//  3. Bounded by BatchSize (default 10000) — keeps TX small + lock window
//     short. Caller drives the loop until 0 rows returned.
//  4. NEVER touch the `events` table — that's archive-worker's surface
//     (Q-L2K-1 separation).
//
// The IO boundary is `Deleter`. Production binds to pgx via:
//
//	WITH d AS (
//	    DELETE FROM events_outbox
//	     WHERE published = TRUE
//	       AND dead_lettered_at IS NULL
//	       AND last_attempt_at < NOW() - INTERVAL '<grace>'
//	       AND ctid IN (SELECT ctid FROM events_outbox
//	                     WHERE published = TRUE AND dead_lettered_at IS NULL
//	                       AND last_attempt_at < NOW() - INTERVAL '<grace>'
//	                     LIMIT <batch_size>)
//	     RETURNING 1
//	) SELECT count(*) FROM d;
//
// Tests inject an in-mem fake.
package outbox_pruner

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

// OutboxCandidate models a single row's prune-relevant state. Tests use it;
// production never materializes the full set (the SQL DELETE-with-LIMIT
// loop counts rows server-side).
type OutboxCandidate struct {
	EventID        uuid.UUID
	Published      bool
	LastAttemptAt  time.Time
	DeadLetteredAt *time.Time // nil ⇒ not dead-lettered
}

// Eligible reports whether this candidate satisfies all 3 prune predicates:
//   published = TRUE AND dead_lettered_at IS NULL AND last_attempt_at < cutoff.
func (c OutboxCandidate) Eligible(cutoff time.Time) bool {
	if !c.Published {
		return false
	}
	if c.DeadLetteredAt != nil {
		return false
	}
	return c.LastAttemptAt.Before(cutoff)
}

// Deleter is the IO boundary. PruneOnce returns counts; the caller decides
// whether to loop until DeletedThisBatch == 0.
type Deleter interface {
	// PruneOnce runs ONE bounded DELETE. cutoff = NOW()-grace. Returns
	// (deleted, scanned, error). Scanned ≥ deleted (rows examined but
	// failed eligibility).
	PruneOnce(ctx context.Context, realityID uuid.UUID, cutoff time.Time, batchSize int) (deleted int64, scanned int64, err error)
}

// Clock allows tests to freeze NOW().
type Clock interface{ Now() time.Time }

// RealClock binds system time.
type RealClock struct{}

// Now returns current system time.
func (RealClock) Now() time.Time { return time.Now() }

// Config is the constructor input.
type Config struct {
	Deleter Deleter
	Clock   Clock
	Cfg     types.RetentionConfig
}

// Pruner is the per-reality runner.
type Pruner struct {
	deleter Deleter
	clock   Clock
	cfg     types.RetentionConfig
}

// New constructs a Pruner.
func New(c Config) (*Pruner, error) {
	if c.Deleter == nil {
		return nil, errors.New("outbox_pruner: Deleter nil")
	}
	if c.Clock == nil {
		return nil, errors.New("outbox_pruner: Clock nil")
	}
	if c.Cfg.OutboxBatchSize <= 0 {
		c.Cfg.OutboxBatchSize = 10000
	}
	if c.Cfg.OutboxPublishedGrace <= 0 {
		c.Cfg.OutboxPublishedGrace = 24 * time.Hour
	}
	return &Pruner{deleter: c.Deleter, clock: c.Clock, cfg: c.Cfg}, nil
}

// PruneReality runs the bounded-batch loop until 0 rows deleted in a batch
// or maxBatches hit (safety cap — default 100 means at most 1M rows deleted
// per call which is well above realistic per-hour publish volume).
func (p *Pruner) PruneReality(ctx context.Context, realityID uuid.UUID) (types.OutboxPruneStats, error) {
	stats := types.OutboxPruneStats{RealityID: realityID}
	cutoff := p.clock.Now().Add(-p.cfg.OutboxPublishedGrace)
	const maxBatches = 100
	for i := 0; i < maxBatches; i++ {
		del, scan, err := p.deleter.PruneOnce(ctx, realityID, cutoff, p.cfg.OutboxBatchSize)
		if err != nil {
			return stats, err
		}
		stats.Deleted += del
		stats.Scanned += scan
		if del < int64(p.cfg.OutboxBatchSize) {
			break
		}
	}
	return stats, nil
}

// InMemoryDeleter is the test-fake impl. Stores candidates per reality;
// PruneOnce filters by Eligible(cutoff) and removes matching rows up to
// batchSize.
type InMemoryDeleter struct {
	Rows map[uuid.UUID][]OutboxCandidate
}

// NewInMemoryDeleter constructs an empty fake.
func NewInMemoryDeleter() *InMemoryDeleter {
	return &InMemoryDeleter{Rows: map[uuid.UUID][]OutboxCandidate{}}
}

// PruneOnce removes up to batchSize eligible rows; returns (deleted, scanned).
// scanned = number of rows whose eligibility was evaluated.
func (d *InMemoryDeleter) PruneOnce(_ context.Context, realityID uuid.UUID, cutoff time.Time, batchSize int) (int64, int64, error) {
	rows := d.Rows[realityID]
	if len(rows) == 0 {
		return 0, 0, nil
	}
	var deleted int64
	var scanned int64
	kept := make([]OutboxCandidate, 0, len(rows))
	for _, r := range rows {
		scanned++
		if int(deleted) < batchSize && r.Eligible(cutoff) {
			deleted++
			continue
		}
		kept = append(kept, r)
	}
	d.Rows[realityID] = kept
	return deleted, scanned, nil
}

// Add appends candidates to the fake (test helper).
func (d *InMemoryDeleter) Add(realityID uuid.UUID, cands ...OutboxCandidate) {
	d.Rows[realityID] = append(d.Rows[realityID], cands...)
}

// FailingDeleter always errors — used to test error propagation.
type FailingDeleter struct{ Err error }

// PruneOnce always returns the configured error.
func (f *FailingDeleter) PruneOnce(_ context.Context, _ uuid.UUID, _ time.Time, _ int) (int64, int64, error) {
	if f.Err != nil {
		return 0, 0, f.Err
	}
	return 0, 0, errors.New("forced failure")
}
