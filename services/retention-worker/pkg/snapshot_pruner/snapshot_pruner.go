// Package snapshot_pruner is a V1 PLACEHOLDER for L3 aggregate_snapshots
// retention. The L3 layer plan (cycle 12+) will define the per-aggregate
// retention policy (keep last-N snapshots OR keep snapshots newer than
// last-keyframe OR keep all snapshots for canon aggregates).
//
// Cycle 11 ships this file solely to:
//   1. Reserve the package name in the retention-worker tree so cycle 12
//      finds the natural home for the impl.
//   2. Document the IO boundary (Deleter interface) so the cycle-12
//      writer doesn't have to refactor.
//   3. Hold the V1 no-op runner that the cmd/retention-worker main loop
//      can wire today without crashing.
//
// V1 behavior: PruneReality returns zero-everything immediately.
package snapshot_pruner

import (
	"context"

	"github.com/google/uuid"
)

// Stats is the per-reality outcome shape.
type Stats struct {
	RealityID uuid.UUID
	Deleted   int64
	Scanned   int64
}

// Pruner is the V1 no-op runner.
type Pruner struct{}

// New constructs the V1 no-op.
func New() *Pruner { return &Pruner{} }

// PruneReality is a V1 no-op. Returns zero-everything; the retention-worker
// loop treats this as "nothing to prune yet" (correct — L3 hasn't shipped).
func (Pruner) PruneReality(_ context.Context, realityID uuid.UUID) (Stats, error) {
	return Stats{RealityID: realityID}, nil
}
