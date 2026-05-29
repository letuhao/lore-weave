// L3.H catastrophic-rebuild admin command — RAID cycle 14 DPS 3.
//
// LOCKED Q-IDs honored:
//   - Q-L3-3: catastrophic rebuild orchestrator = admin-cli sub-command +
//     `rolling_rebuild` internal lib (services/admin-cli/internal/rolling_rebuild).
//   - Q-L3-5: NO blue-green migration; rebuild uses freeze-rebuild per-reality
//     (delegates to rebuild_projection.go which itself honors Q-L3-5).
//
// Scope (--scope flag):
//   - `reality`        single --reality <id>
//   - `all-realities`  every reality in meta DB
//   - `aggregate-list` --aggregate-file <path> (one reality_id per line)
//
// Tier classification: S5-D5 Tier-1 destructive (TRUNCATEs across N realities).
// Requires --confirm flag; rolling via rolling_rebuild package so global outage
// is bounded.
package commands

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/loreweave/foundation/services/admin-cli/internal/rolling_rebuild"
)

// CatastrophicRebuildRequest captures the input to admin catastrophic-rebuild.
type CatastrophicRebuildRequest struct {
	Scope             string // "reality" | "all-realities" | "aggregate-list"
	RealityIDs        []string
	Actor             string
	Reason            string
	Confirm           bool
	DryRun            bool
	RollingConcurrency int
	PerRealityTimeout  time.Duration
}

// ErrInvalidCatastrophic — bad input.
var ErrInvalidCatastrophic = errors.New("admin-cli: invalid catastrophic rebuild request")

// Validate enforces tier-1 destructive policy.
func (r CatastrophicRebuildRequest) Validate() error {
	switch r.Scope {
	case "reality", "all-realities", "aggregate-list":
		// ok
	default:
		return fmt.Errorf("%w: scope must be reality|all-realities|aggregate-list, got %q", ErrInvalidCatastrophic, r.Scope)
	}
	if len(r.RealityIDs) == 0 {
		return fmt.Errorf("%w: reality_ids empty", ErrInvalidCatastrophic)
	}
	if r.Actor == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidCatastrophic)
	}
	if r.Reason == "" {
		return fmt.Errorf("%w: reason empty (catastrophic-rebuild audit requires explanation)", ErrInvalidCatastrophic)
	}
	if !r.Confirm && !r.DryRun {
		return fmt.Errorf("%w: --confirm required for destructive run (or --dry-run to preview)", ErrInvalidCatastrophic)
	}
	if r.RollingConcurrency <= 0 || r.RollingConcurrency > 50 {
		return fmt.Errorf("%w: rolling_concurrency=%d must be in [1,50] (R02 §12B.5)", ErrInvalidCatastrophic, r.RollingConcurrency)
	}
	if r.PerRealityTimeout <= 0 || r.PerRealityTimeout > 30*time.Minute {
		return fmt.Errorf("%w: per_reality_timeout=%s must be in (0, 30m]", ErrInvalidCatastrophic, r.PerRealityTimeout)
	}
	return nil
}

// CatastrophicRebuildResult is the summary returned by ApplyCatastrophicRebuild.
type CatastrophicRebuildResult struct {
	DryRun           bool
	TotalRealities   int
	RealitiesOK      int
	RealitiesFailed  int
	PerRealityErrors map[string]string
	MaxConcurrentSeen int
	Duration         time.Duration
}

// ApplyCatastrophicRebuild orchestrates the rolling catastrophic rebuild.
//
// Architecture (Q-L3-3):
//   admin catastrophic-rebuild (this fn)
//     └─→ rolling_rebuild.Orchestrator (bounded concurrency, partial-failure
//         tolerant)
//             └─→ RealityRebuilder.RebuildReality (one reality at a time —
//                 production wires to a closure that loops every projection
//                 and calls ApplyRebuildProjection per-projection)
//
// Why two layers: the rolling lib is reusable for future bulk operations
// (mass schema migrations, mass projection-schema upgrades). The admin-cli
// command is the destructive-policy / audit layer.
func ApplyCatastrophicRebuild(
	ctx context.Context,
	req CatastrophicRebuildRequest,
	rebuilder rolling_rebuild.RealityRebuilder,
) (CatastrophicRebuildResult, error) {
	if err := req.Validate(); err != nil {
		return CatastrophicRebuildResult{}, err
	}

	if req.DryRun {
		return CatastrophicRebuildResult{
			DryRun:         true,
			TotalRealities: len(req.RealityIDs),
		}, nil
	}

	orch, err := rolling_rebuild.New(rolling_rebuild.Config{
		RollingConcurrency: req.RollingConcurrency,
		PerRealityTimeout:  req.PerRealityTimeout,
	}, rebuilder)
	if err != nil {
		return CatastrophicRebuildResult{}, fmt.Errorf("admin-cli: orchestrator setup: %w", err)
	}

	roll := orch.Run(ctx, req.RealityIDs, req.Actor, req.Reason)
	return CatastrophicRebuildResult{
		DryRun:            false,
		TotalRealities:    roll.TotalRealities,
		RealitiesOK:       roll.RealitiesOK,
		RealitiesFailed:   roll.RealitiesFailed,
		PerRealityErrors:  roll.PerRealityErrors,
		MaxConcurrentSeen: roll.MaxConcurrentSeen,
		Duration:          roll.Duration,
	}, nil
}
