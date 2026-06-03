package commands

// Live `reality rebuild-projection` (073, L3.G) — Tier-1 destructive freeze-
// rebuild of ONE projection table for ONE reality (Q-L3-3 / Q-L3-5):
//
//	1. Freeze     — reality active → frozen (AttemptStateTransition; writers 503).
//	2. Truncate   — TRUNCATE the target projection table (per-reality DB).
//	3. Rebuild    — exec the world-service `rebuilder` worker (replays events).
//	4. Thaw       — frozen → active, ONLY on a fully-successful rebuild.
//
// Order is load-bearing: freeze BEFORE truncate (no truncate if freeze fails);
// on ANY rebuild failure/partial the reality is LEFT FROZEN so an operator
// inspects the dead letter before a manual `reality thaw` (R02 §12B.2 fail-loud).
//
// ⚠️ UNPROVEN: the rebuilder is the first live projection-apply path and is not
// yet validated against real events by the L3.E/F integrity checker. The command
// is registered only when ADMIN_CLI_ENABLE_UNPROVEN_REBUILD=1; otherwise it stays
// fail-closed NotWired. See docs/plans/2026-06-03-073-destructive-admin-commands.md.

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// ErrInvalidRebuild is returned by Validate / RunRebuildProjection on bad input.
var ErrInvalidRebuild = errors.New("rebuild-projection: invalid request")

// projectionTables is the allowlist of L3.A projection table names a rebuild may
// target. The name is interpolated into `TRUNCATE <table>` and passed to the
// rebuilder, so an un-allowlisted value MUST be rejected (DDL-injection guard).
// Mirrors world_service::rebuild::PROJECTION_TABLES.
var projectionTables = map[string]struct{}{
	"pc_projection":                  {},
	"pc_inventory_projection":        {},
	"pc_relationship_projection":     {},
	"npc_projection":                 {},
	"npc_session_memory_projection":  {},
	"npc_pc_relationship_projection": {},
	"npc_session_memory_embedding":   {},
	"region_projection":              {},
	"world_kv_projection":            {},
	"session_participants":           {},
	"canon_projection":               {},
}

// IsKnownProjectionTable reports whether name is an allowlisted projection table.
func IsKnownProjectionTable(name string) bool {
	_, ok := projectionTables[name]
	return ok
}

// RebuildProjectionRequest is the input to RunRebuildProjection.
type RebuildProjectionRequest struct {
	RealityID      uuid.UUID
	ProjectionName string
	Actor          string // admin subject (JWT sub)
	Reason         string
	Confirm        bool
	DryRun         bool
}

// Validate enforces the destructive-command preconditions the dispatcher does
// not (the projection-table allowlist + a parsed reality_id).
func (r RebuildProjectionRequest) Validate() error {
	if r.RealityID == uuid.Nil {
		return fmt.Errorf("%w: reality_id empty", ErrInvalidRebuild)
	}
	if !IsKnownProjectionTable(r.ProjectionName) {
		return fmt.Errorf("%w: projection_name %q is not an L3.A projection table", ErrInvalidRebuild, r.ProjectionName)
	}
	if strings.TrimSpace(r.Actor) == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidRebuild)
	}
	if strings.TrimSpace(r.Reason) == "" {
		return fmt.Errorf("%w: reason empty (audit requires explanation)", ErrInvalidRebuild)
	}
	if !r.Confirm && !r.DryRun {
		return fmt.Errorf("%w: --confirm required (or --dry-run to preview)", ErrInvalidRebuild)
	}
	return nil
}

// RebuildStats is the rebuilder worker's JSON summary (mirrors
// world_service::rebuild::RebuildStats). aggregates_failed > 0 means the reality
// is LEFT FROZEN.
type RebuildStats struct {
	AggregatesRebuilt int64 `json:"aggregates_rebuilt"`
	AggregatesSkipped int64 `json:"aggregates_skipped"`
	AggregatesFailed  int64 `json:"aggregates_failed"`
	EventsReplayed    int64 `json:"events_replayed"`
	UpdatesApplied    int64 `json:"updates_applied"`
}

// LifecycleGate flips a reality between `active` and `frozen` via the meta state
// machine (AttemptStateTransition — writes lifecycle_transition_audit). Prod impl
// is PgLifecycleGate; tests stub.
type LifecycleGate interface {
	// FreezeForRebuild transitions active → frozen (writers get 503).
	FreezeForRebuild(ctx context.Context, realityID uuid.UUID, actor, reason string) error
	// ThawAfterRebuild transitions frozen → active.
	ThawAfterRebuild(ctx context.Context, realityID uuid.UUID, actor, reason string) error
}

// ProjectionTruncator wipes ONE projection table in the reality's shard DB.
type ProjectionTruncator interface {
	Truncate(ctx context.Context, realityID uuid.UUID, projection string) error
}

// RebuildInvoker runs the rebuilder worker over the reality and returns its
// stats. Prod impl execs the world-service `rebuilder` binary.
type RebuildInvoker interface {
	Rebuild(ctx context.Context, realityID uuid.UUID, projection string) (RebuildStats, error)
}

// RebuildProjectionDeps bundles the collaborators.
type RebuildProjectionDeps struct {
	Lifecycle LifecycleGate
	Truncator ProjectionTruncator
	Invoker   RebuildInvoker
}

// RunRebuildProjection orchestrates the freeze-truncate-rebuild-thaw flow.
func RunRebuildProjection(ctx context.Context, req RebuildProjectionRequest, deps RebuildProjectionDeps) (string, error) {
	if err := req.Validate(); err != nil {
		return "", err
	}
	if req.DryRun {
		return fmt.Sprintf(
			"rebuild-projection DRY-RUN — would freeze reality %s, TRUNCATE %s, replay events, then thaw. No changes made.",
			req.RealityID, req.ProjectionName), nil
	}
	if deps.Lifecycle == nil || deps.Truncator == nil || deps.Invoker == nil {
		return "", fmt.Errorf("%w: deps incomplete", ErrInvalidRebuild)
	}

	// ── 1. Freeze (before any destructive step) ──────────────────────────────
	if err := deps.Lifecycle.FreezeForRebuild(ctx, req.RealityID, req.Actor, req.Reason); err != nil {
		return "", fmt.Errorf("rebuild-projection: freeze (no changes made): %w", err)
	}

	// ── 2. Truncate ──────────────────────────────────────────────────────────
	if err := deps.Truncator.Truncate(ctx, req.RealityID, req.ProjectionName); err != nil {
		// Best-effort thaw — the table was not touched if truncate failed.
		_ = deps.Lifecycle.ThawAfterRebuild(ctx, req.RealityID, req.Actor, "rollback: truncate failed")
		return "", fmt.Errorf("rebuild-projection: truncate (thaw attempted): %w", err)
	}

	// ── 3. Rebuild ───────────────────────────────────────────────────────────
	stats, err := deps.Invoker.Rebuild(ctx, req.RealityID, req.ProjectionName)
	if err != nil {
		// LEAVE FROZEN — the projection is now empty/partial; operator inspects.
		return "", fmt.Errorf("rebuild-projection: rebuild FAILED — reality %s LEFT FROZEN, inspect dead letter then `admin reality thaw`: %w", req.RealityID, err)
	}
	if stats.AggregatesFailed > 0 {
		return "", fmt.Errorf("rebuild-projection: %d aggregate(s) dead-lettered — reality %s LEFT FROZEN, inspect then `admin reality thaw`", stats.AggregatesFailed, req.RealityID)
	}

	// ── 4. Thaw (only on full success) ───────────────────────────────────────
	if err := deps.Lifecycle.ThawAfterRebuild(ctx, req.RealityID, req.Actor, "rebuild-projection complete"); err != nil {
		return "", fmt.Errorf("rebuild-projection: rebuild OK but thaw FAILED — reality %s LEFT FROZEN, manual `admin reality thaw` required: %w", req.RealityID, err)
	}

	return fmt.Sprintf(
		"rebuild-projection complete — reality %s projection %s rebuilt (%d aggregates, %d events, %d updates) and thawed.",
		req.RealityID, req.ProjectionName, stats.AggregatesRebuilt, stats.EventsReplayed, stats.UpdatesApplied), nil
}
