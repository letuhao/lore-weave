// Package rolling_rebuild — RAID cycle 14 L3.H.2.
//
// Internal lib backing the `admin catastrophic-rebuild` sub-command (Q-L3-3:
// "Catastrophic rebuild orchestrator = admin-cli sub-command + `rolling_rebuild`
// internal lib"). Drives rolling per-reality rebuild with bounded concurrency
// (`contracts/rebuild/catastrophic_config.yaml::rolling_concurrency = 50`).
//
// Why ROLLING (not big-bang):
//   - All-at-once rebuild of N realities = N simultaneous freezes = global
//     write outage. R02 §12B.5 mandates rolling so no more than
//     `rolling_concurrency` realities are frozen simultaneously.
//   - A failure on reality K does not abort the run; it is recorded and the
//     orchestrator continues with reality K+1 (with K's failure surfacing in
//     the final summary so the operator can re-queue manually).
package rolling_rebuild

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// RealityRebuilder rebuilds ONE reality. Production wires to
// `commands.ApplyRebuildProjection` (cycle 14 DPS 2) per-projection looped over
// every projection name; tests stub.
type RealityRebuilder interface {
	RebuildReality(ctx context.Context, realityID, actor, reason string) (PerRealityStats, error)
}

// PerRealityStats summarises a single reality's rebuild outcome.
type PerRealityStats struct {
	RealityID         string
	ProjectionsTried  int
	ProjectionsOK     int
	AggregatesRebuilt int64
	AggregatesFailed  int64
	EventsReplayed    int64
	Duration          time.Duration
}

// Config — `contracts/rebuild/catastrophic_config.yaml`.
type Config struct {
	// Max concurrent realities frozen at once. Layer-plan L3.H.3:
	// `rolling_concurrency = 50`.
	RollingConcurrency int
	// Per-reality timeout. Layer-plan: `freeze_timeout_minutes = 30`.
	PerRealityTimeout time.Duration
}

// ErrInvalidConfig — bad orchestration config.
var ErrInvalidConfig = errors.New("rolling_rebuild: invalid config")

// Validate enforces config bounds.
func (c Config) Validate() error {
	if c.RollingConcurrency <= 0 {
		return fmt.Errorf("%w: rolling_concurrency must be > 0", ErrInvalidConfig)
	}
	if c.RollingConcurrency > 50 {
		return fmt.Errorf("%w: rolling_concurrency=%d exceeds 50 cap (R02 §12B.5)", ErrInvalidConfig, c.RollingConcurrency)
	}
	if c.PerRealityTimeout <= 0 {
		return fmt.Errorf("%w: per_reality_timeout must be > 0", ErrInvalidConfig)
	}
	return nil
}

// Orchestrator drives rolling rebuild across a list of realities.
type Orchestrator struct {
	cfg      Config
	rebuilder RealityRebuilder
}

// New constructs an Orchestrator. Returns ErrInvalidConfig on bad cfg.
func New(cfg Config, rebuilder RealityRebuilder) (*Orchestrator, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if rebuilder == nil {
		return nil, fmt.Errorf("%w: rebuilder nil", ErrInvalidConfig)
	}
	return &Orchestrator{cfg: cfg, rebuilder: rebuilder}, nil
}

// RollResult is the summary of one Run call.
type RollResult struct {
	TotalRealities    int
	RealitiesOK       int
	RealitiesFailed   int
	PerReality        []PerRealityStats
	PerRealityErrors  map[string]string // realityID → error
	MaxConcurrentSeen int               // observed peak concurrency (for tests)
	Duration          time.Duration
}

// Run rolls through realities with bounded concurrency. Failure on reality K
// does NOT abort — it goes into PerRealityErrors and the run continues.
//
// Concurrency invariant: at any instant, len(in_flight) <= RollingConcurrency.
// We enforce this with a semaphore + an observability counter that we surface
// in MaxConcurrentSeen so the unit test can assert.
func (o *Orchestrator) Run(ctx context.Context, realities []string, actor, reason string) RollResult {
	start := time.Now()
	res := RollResult{
		TotalRealities:   len(realities),
		PerRealityErrors: make(map[string]string),
	}
	if len(realities) == 0 {
		res.Duration = time.Since(start)
		return res
	}

	sem := make(chan struct{}, o.cfg.RollingConcurrency)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var currentInFlight int

	for _, realityID := range realities {
		realityID := realityID
		wg.Add(1)
		sem <- struct{}{} // BLOCKS until a slot is free (rolling — not all-at-once)
		mu.Lock()
		currentInFlight++
		if currentInFlight > res.MaxConcurrentSeen {
			res.MaxConcurrentSeen = currentInFlight
		}
		mu.Unlock()
		go func() {
			defer wg.Done()
			defer func() {
				mu.Lock()
				currentInFlight--
				mu.Unlock()
				<-sem
			}()

			perCtx, cancel := context.WithTimeout(ctx, o.cfg.PerRealityTimeout)
			defer cancel()

			stats, err := o.rebuilder.RebuildReality(perCtx, realityID, actor, reason)
			mu.Lock()
			defer mu.Unlock()
			res.PerReality = append(res.PerReality, stats)
			if err != nil {
				res.RealitiesFailed++
				res.PerRealityErrors[realityID] = err.Error()
				return
			}
			res.RealitiesOK++
		}()
	}
	wg.Wait()
	res.Duration = time.Since(start)
	return res
}
