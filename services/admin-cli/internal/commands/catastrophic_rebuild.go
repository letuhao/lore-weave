package commands

// Live `reality catastrophic-rebuild` (073, L3.H) — Tier-1 destructive rolling
// rebuild of EVERY projection table across N realities (Q-L3-3). Wraps the
// internal/rolling_rebuild orchestrator (bounded concurrency so no more than
// rolling_concurrency realities are frozen at once — R02 §12B.5) over a
// per-reality flow that reuses the rebuild-projection primitives:
//
//	freeze reality ONCE → for each projection table: TRUNCATE + rebuilder →
//	thaw ONCE (only if every projection rebuilt cleanly; else LEAVE FROZEN).
//
// First-class as of 147+142 (same as rebuild-projection): the projection-apply
// path is validated, so the former ADMIN_CLI_ENABLE_UNPROVEN_REBUILD gate is
// removed; wired whenever META_DATABASE_URL is set.

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/admin-cli/internal/rolling_rebuild"
)

// ErrInvalidCatastrophic is returned on bad catastrophic-rebuild input.
var ErrInvalidCatastrophic = errors.New("catastrophic-rebuild: invalid request")

// AllProjectionTables returns the allowlisted projection table names, sorted —
// the full set a catastrophic rebuild replays per reality.
func AllProjectionTables() []string {
	out := make([]string, 0, len(projectionTables))
	for t := range projectionTables {
		out = append(out, t)
	}
	sort.Strings(out)
	return out
}

// CatastrophicRebuildRequest is the input to RunCatastrophicRebuild. RealityIDs
// are pre-resolved by the handler from --scope (reality | all-realities |
// aggregate-list).
type CatastrophicRebuildRequest struct {
	Scope              string
	RealityIDs         []string
	Actor              string
	Reason             string
	Confirm            bool
	DryRun             bool
	RollingConcurrency int
	PerRealityTimeout  time.Duration
}

// Validate enforces the tier-1 rolling preconditions.
func (r CatastrophicRebuildRequest) Validate() error {
	switch r.Scope {
	case "reality", "all-realities", "aggregate-list":
	default:
		return fmt.Errorf("%w: scope must be reality|all-realities|aggregate-list, got %q", ErrInvalidCatastrophic, r.Scope)
	}
	if len(r.RealityIDs) == 0 {
		return fmt.Errorf("%w: no realities resolved for scope %q", ErrInvalidCatastrophic, r.Scope)
	}
	for _, id := range r.RealityIDs {
		if _, err := uuid.Parse(id); err != nil {
			return fmt.Errorf("%w: reality_id %q is not a UUID", ErrInvalidCatastrophic, id)
		}
	}
	if strings.TrimSpace(r.Actor) == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidCatastrophic)
	}
	if strings.TrimSpace(r.Reason) == "" {
		return fmt.Errorf("%w: reason empty", ErrInvalidCatastrophic)
	}
	if !r.Confirm && !r.DryRun {
		return fmt.Errorf("%w: --confirm required (or --dry-run to preview)", ErrInvalidCatastrophic)
	}
	if r.RollingConcurrency <= 0 || r.RollingConcurrency > 50 {
		return fmt.Errorf("%w: rolling_concurrency=%d must be in [1,50]", ErrInvalidCatastrophic, r.RollingConcurrency)
	}
	if r.PerRealityTimeout <= 0 || r.PerRealityTimeout > 30*time.Minute {
		return fmt.Errorf("%w: per_reality_timeout=%s must be in (0,30m]", ErrInvalidCatastrophic, r.PerRealityTimeout)
	}
	return nil
}

// PerRealityResolver opens the per-reality collaborators (truncator + rebuilder
// invoker) for one reality and returns a closer. The handler supplies the
// production impl (per-reality DB pool + shard DSN); tests stub.
type PerRealityResolver func(ctx context.Context, realityID uuid.UUID) (ProjectionTruncator, RebuildInvoker, func(), error)

// MultiProjectionRebuilder implements rolling_rebuild.RealityRebuilder: it
// freezes a reality once, rebuilds every projection table, then thaws once. Any
// failure leaves the reality FROZEN (fail-loud).
type MultiProjectionRebuilder struct {
	Lifecycle   LifecycleGate
	Resolve     PerRealityResolver
	Projections []string
}

var _ rolling_rebuild.RealityRebuilder = (*MultiProjectionRebuilder)(nil)

// RebuildReality runs the per-reality freeze→(truncate+rebuild)*→thaw flow.
func (m *MultiProjectionRebuilder) RebuildReality(ctx context.Context, realityIDStr, actor, reason string) (rolling_rebuild.PerRealityStats, error) {
	start := time.Now()
	stats := rolling_rebuild.PerRealityStats{RealityID: realityIDStr}
	rid, err := uuid.Parse(realityIDStr)
	if err != nil {
		return stats, fmt.Errorf("invalid reality_id %q: %w", realityIDStr, err)
	}
	trunc, invoker, closeFn, err := m.Resolve(ctx, rid)
	if err != nil {
		return stats, fmt.Errorf("resolve reality %s: %w", realityIDStr, err)
	}
	defer closeFn()

	if err := m.Lifecycle.FreezeForRebuild(ctx, rid, actor, reason); err != nil {
		return stats, fmt.Errorf("freeze (no changes made): %w", err)
	}

	for _, proj := range m.Projections {
		stats.ProjectionsTried++
		if err := trunc.Truncate(ctx, rid, proj); err != nil {
			return stats, fmt.Errorf("truncate %s — reality %s LEFT FROZEN: %w", proj, realityIDStr, err)
		}
		rs, err := invoker.Rebuild(ctx, rid, proj)
		if err != nil {
			return stats, fmt.Errorf("rebuild %s — reality %s LEFT FROZEN: %w", proj, realityIDStr, err)
		}
		stats.AggregatesRebuilt += rs.AggregatesRebuilt
		stats.EventsReplayed += rs.EventsReplayed
		if rs.AggregatesFailed > 0 {
			stats.AggregatesFailed += rs.AggregatesFailed
			return stats, fmt.Errorf("%d aggregate(s) failed on %s — reality %s LEFT FROZEN", rs.AggregatesFailed, proj, realityIDStr)
		}
		stats.ProjectionsOK++
	}

	if err := m.Lifecycle.ThawAfterRebuild(ctx, rid, actor, reason); err != nil {
		return stats, fmt.Errorf("thaw FAILED — reality %s LEFT FROZEN: %w", realityIDStr, err)
	}
	stats.Duration = time.Since(start)
	return stats, nil
}

// RunCatastrophicRebuild drives the rolling orchestrator and formats the summary.
// Returns an error (non-zero exit) if any reality failed, so the operator notices.
func RunCatastrophicRebuild(ctx context.Context, req CatastrophicRebuildRequest, rebuilder rolling_rebuild.RealityRebuilder) (string, error) {
	if err := req.Validate(); err != nil {
		return "", err
	}
	if req.DryRun {
		return fmt.Sprintf(
			"catastrophic-rebuild DRY-RUN — scope=%s would freeze-rebuild %d realities × %d projection tables (rolling_concurrency=%d). No changes made.",
			req.Scope, len(req.RealityIDs), len(AllProjectionTables()), req.RollingConcurrency), nil
	}

	orch, err := rolling_rebuild.New(rolling_rebuild.Config{
		RollingConcurrency: req.RollingConcurrency,
		PerRealityTimeout:  req.PerRealityTimeout,
	}, rebuilder)
	if err != nil {
		return "", fmt.Errorf("catastrophic-rebuild: orchestrator: %w", err)
	}

	roll := orch.Run(ctx, req.RealityIDs, req.Actor, req.Reason)

	var b strings.Builder
	fmt.Fprintf(&b, "catastrophic-rebuild (scope=%s) — %d realities: %d OK, %d FAILED (max concurrent %d, %s)\n",
		req.Scope, roll.TotalRealities, roll.RealitiesOK, roll.RealitiesFailed, roll.MaxConcurrentSeen, roll.Duration.Round(time.Millisecond))
	if roll.RealitiesFailed > 0 {
		// Deterministic ordering for a stable message.
		ids := make([]string, 0, len(roll.PerRealityErrors))
		for id := range roll.PerRealityErrors {
			ids = append(ids, id)
		}
		sort.Strings(ids)
		for _, id := range ids {
			fmt.Fprintf(&b, "  FROZEN %s: %s\n", id, roll.PerRealityErrors[id])
		}
		return "", fmt.Errorf("catastrophic-rebuild: %d/%d realities LEFT FROZEN — inspect + re-queue:\n%s",
			roll.RealitiesFailed, roll.TotalRealities, b.String())
	}
	return b.String(), nil
}
