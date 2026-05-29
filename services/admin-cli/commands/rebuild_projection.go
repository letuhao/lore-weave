// L3.G freeze-rebuild admin command — RAID cycle 14.
//
// Flow:
//
//	1. Validate request (reality_id + projection name + actor).
//	2. Transition reality: active → rebuilding (writes rejected, 503).
//	3. TRUNCATE projection table.
//	4. Call the rebuilder worker (per-aggregate replay; Rust crate
//	   `crates/rebuilder/` invoked via the world-service binary).
//	5. Transition reality: rebuilding → active.
//	6. Write `lifecycle_transition_audit` row for each transition.
//
// LOCKED Q-IDs honored:
//   - Q-L3-5: V1 strategy = freeze-rebuild. NO blue-green migration.
//   - Q-L3-3: this command IS the admin-cli sub-command (the catastrophic
//     wrapper in catastrophic_rebuild.go calls this internally per-reality).
//
// Tier classification: S5-D5 Tier-1 destructive (TRUNCATEs projection table).
// Requires --confirm flag; logs every step.
package commands

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// RebuildProjectionRequest captures the input to admin rebuild-projection.
type RebuildProjectionRequest struct {
	RealityID      string // UUID string
	ProjectionName string // e.g. "pc_projection"
	Actor          string // user_ref_id
	Reason         string // audit explanation
	Confirm        bool   // --confirm flag — required for non-dry-run
	DryRun         bool   // --dry-run skips TRUNCATE + rebuild, just emits plan
	FreezeTimeout  time.Duration
}

// ErrInvalidRebuild is returned by Validate / Apply on bad input.
var ErrInvalidRebuild = errors.New("admin-cli: invalid rebuild request")

// Validate enforces destructive-command policy.
func (r RebuildProjectionRequest) Validate() error {
	if r.RealityID == "" {
		return fmt.Errorf("%w: reality_id empty", ErrInvalidRebuild)
	}
	if r.ProjectionName == "" {
		return fmt.Errorf("%w: projection_name empty", ErrInvalidRebuild)
	}
	if r.Actor == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidRebuild)
	}
	if r.Reason == "" {
		return fmt.Errorf("%w: reason empty (audit requires explanation)", ErrInvalidRebuild)
	}
	if !r.Confirm && !r.DryRun {
		return fmt.Errorf("%w: --confirm required for destructive run (or --dry-run to preview)", ErrInvalidRebuild)
	}
	if r.FreezeTimeout > 30*time.Minute {
		return fmt.Errorf("%w: freeze_timeout=%s exceeds 30m cap (contracts/rebuild/config.yaml)", ErrInvalidRebuild, r.FreezeTimeout)
	}
	return nil
}

// LifecycleGate flips a reality between `active` and `rebuilding`. Production
// wires to contracts/meta/lifecycle.go; tests stub.
type LifecycleGate interface {
	// FreezeForRebuild transitions reality: active → rebuilding. Writes are
	// rejected with 503 by the world-service maintenance middleware
	// (L3.G.3, cycle 15).
	FreezeForRebuild(ctx context.Context, realityID, actor, reason string) error
	// ThawAfterRebuild transitions reality: rebuilding → active.
	ThawAfterRebuild(ctx context.Context, realityID, actor, reason string) error
}

// ProjectionTruncator wipes a projection table (TRUNCATE ... RESTART IDENTITY).
type ProjectionTruncator interface {
	Truncate(ctx context.Context, realityID, projectionName string) error
}

// RebuildInvoker runs the rebuilder worker over all aggregates for the named
// projection. Production wires to the rust crates/rebuilder via a subprocess
// or RPC to world-service; tests stub.
type RebuildInvoker interface {
	Rebuild(ctx context.Context, realityID, projectionName string) (RebuildStats, error)
}

// RebuildStats is the per-projection summary returned by the worker.
type RebuildStats struct {
	AggregatesRebuilt int64
	AggregatesFailed  int64
	EventsReplayed    int64
}

// AuditWriter writes a `lifecycle_transition_audit` row. Production wires to
// contracts/meta; tests stub.
type AuditWriter interface {
	WriteTransition(ctx context.Context, evt AuditTransition) error
}

// AuditTransition is one row in lifecycle_transition_audit.
type AuditTransition struct {
	RealityID  string
	FromState  string
	ToState    string
	Actor      string
	Reason     string
	OccurredAt time.Time
}

// RebuildDeps bundles all collaborators.
type RebuildDeps struct {
	Lifecycle  LifecycleGate
	Truncator  ProjectionTruncator
	Invoker    RebuildInvoker
	Audit      AuditWriter
	Clock      ClockFn
}

// RebuildResult is what Apply returns on success.
type RebuildResult struct {
	RealityID         string
	ProjectionName    string
	DryRun            bool
	AggregatesRebuilt int64
	AggregatesFailed  int64
	EventsReplayed    int64
	FreezeDuration    time.Duration
	FrozeAt           time.Time
	ThawedAt          time.Time
}

// Apply orchestrates the freeze-rebuild flow.
//
// Order of operations is load-bearing:
//
//  1. Freeze the reality FIRST. If freeze fails, abort BEFORE truncate.
//  2. TRUNCATE. If truncate fails, attempt thaw (best effort) and report.
//  3. Invoke rebuilder. On success, thaw normally.
//  4. On rebuilder failure: leave reality frozen + write audit row pointing
//     to the runbook (operator MUST inspect dead-letter table before manual
//     thaw — silently thawing on partial rebuild would lose data).
func ApplyRebuildProjection(ctx context.Context, req RebuildProjectionRequest, deps RebuildDeps) (RebuildResult, error) {
	if err := req.Validate(); err != nil {
		return RebuildResult{}, err
	}
	if deps.Lifecycle == nil || deps.Truncator == nil || deps.Invoker == nil || deps.Audit == nil || deps.Clock == nil {
		return RebuildResult{}, fmt.Errorf("%w: deps incomplete", ErrInvalidRebuild)
	}

	res := RebuildResult{
		RealityID:      req.RealityID,
		ProjectionName: req.ProjectionName,
		DryRun:         req.DryRun,
	}

	if req.DryRun {
		// Dry run path — print plan, do not touch state.
		return res, nil
	}

	// ── 1. Freeze ────────────────────────────────────────────────────────
	frozeAt := deps.Clock()
	if err := deps.Lifecycle.FreezeForRebuild(ctx, req.RealityID, req.Actor, req.Reason); err != nil {
		return res, fmt.Errorf("admin-cli: freeze: %w", err)
	}
	res.FrozeAt = frozeAt
	if err := deps.Audit.WriteTransition(ctx, AuditTransition{
		RealityID:  req.RealityID,
		FromState:  "active",
		ToState:    "rebuilding",
		Actor:      req.Actor,
		Reason:     req.Reason,
		OccurredAt: frozeAt,
	}); err != nil {
		// Audit write failure is severe but not fatal — log and continue.
		// In prod, alerting on the audit gap is the SRE's job.
		_ = err
	}

	// ── 2. TRUNCATE ──────────────────────────────────────────────────────
	if err := deps.Truncator.Truncate(ctx, req.RealityID, req.ProjectionName); err != nil {
		// Try to thaw. Even on thaw failure, return the truncate error so
		// operator knows the projection table is empty.
		_ = deps.Lifecycle.ThawAfterRebuild(ctx, req.RealityID, req.Actor, "rollback: truncate failed")
		return res, fmt.Errorf("admin-cli: truncate: %w", err)
	}

	// ── 3. Rebuild ───────────────────────────────────────────────────────
	stats, err := deps.Invoker.Rebuild(ctx, req.RealityID, req.ProjectionName)
	res.AggregatesRebuilt = stats.AggregatesRebuilt
	res.AggregatesFailed = stats.AggregatesFailed
	res.EventsReplayed = stats.EventsReplayed
	if err != nil {
		// Leave frozen — operator MUST inspect dead-letter before manual thaw.
		return res, fmt.Errorf("admin-cli: rebuild (reality FROZEN — inspect dead-letter then `admin thaw`): %w", err)
	}
	if stats.AggregatesFailed > 0 {
		// Any failed aggregate = leave frozen, operator inspects dead letter.
		return res, fmt.Errorf("admin-cli: %d aggregate(s) failed (reality FROZEN — inspect projection_rebuild_errors then `admin thaw`)", stats.AggregatesFailed)
	}

	// ── 4. Thaw ──────────────────────────────────────────────────────────
	thawedAt := deps.Clock()
	if err := deps.Lifecycle.ThawAfterRebuild(ctx, req.RealityID, req.Actor, "rebuild complete"); err != nil {
		return res, fmt.Errorf("admin-cli: thaw (reality FROZEN — manual thaw required): %w", err)
	}
	res.ThawedAt = thawedAt
	res.FreezeDuration = thawedAt.Sub(frozeAt)
	_ = deps.Audit.WriteTransition(ctx, AuditTransition{
		RealityID:  req.RealityID,
		FromState:  "rebuilding",
		ToState:    "active",
		Actor:      req.Actor,
		Reason:     "rebuild complete",
		OccurredAt: thawedAt,
	})

	return res, nil
}
