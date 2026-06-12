// Package cohort_router routes realities into a canary stage by their
// reality_registry.deploy_cohort (L1.A.6.4 / SR05 §12AH.4).
//
// deploy_cohort is hash(reality_id) % 100, assigned at reality creation and
// stable for its lifetime; canary rolls cohorts in order 0→99. The router
// answers two questions the controller needs each tick:
//
//   - which realities are LIVE on the new code at a given stage (RealitiesInStage)
//   - what cohort-scoped SLI label set to query for the auto-abort check
//
// The reality_registry read is behind RealitySource so the controller can run
// against the live meta DB in prod and a fake in tests (no live Postgres in CI).
package cohort_router

import (
	"context"
	"fmt"
	"sort"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

// Reality is the projection of a reality_registry row the router needs.
type Reality struct {
	RealityID    string
	DeployCohort int    // 0..99
	Tier         string // free|paid|premium — stage 1 weights non-premium
	Status       string // only 'active' realities take traffic
}

// RealitySource reads reality rows. The prod impl queries reality_registry via
// contracts/meta (read-only); the test impl is an in-memory slice.
type RealitySource interface {
	// ListActive returns all realities currently eligible for routing
	// (status='active'). Implementations MUST NOT return non-active realities.
	ListActive(ctx context.Context) ([]Reality, error)
}

// Router selects realities per canary stage.
type Router struct {
	src RealitySource
}

// New builds a Router. Fails closed on a nil source.
func New(src RealitySource) (*Router, error) {
	if src == nil {
		return nil, fmt.Errorf("cohort_router: nil reality source")
	}
	return &Router{src: src}, nil
}

// RealitiesInStage returns the active realities live on the new code at the
// given stage, sorted by deploy_cohort then reality_id (deterministic).
func (r *Router) RealitiesInStage(ctx context.Context, stage canary.Stage) ([]Reality, error) {
	all, err := r.src.ListActive(ctx)
	if err != nil {
		return nil, fmt.Errorf("cohort_router: list active: %w", err)
	}
	out := make([]Reality, 0, len(all))
	for _, rr := range all {
		if rr.Status != "active" {
			// Defensive: the contract says ListActive returns only active, but
			// fail safe by skipping anything that slips through.
			continue
		}
		if rr.DeployCohort < 0 || rr.DeployCohort > 99 {
			continue
		}
		if canary.CohortInStage(rr.DeployCohort, stage) {
			out = append(out, rr)
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].DeployCohort != out[j].DeployCohort {
			return out[i].DeployCohort < out[j].DeployCohort
		}
		return out[i].RealityID < out[j].RealityID
	})
	return out, nil
}

// CohortsInStage returns the distinct deploy_cohort values that are live at the
// given stage (the label set for the cohort-scoped SLI query).
func (r *Router) CohortsInStage(ctx context.Context, stage canary.Stage) ([]int, error) {
	rs, err := r.RealitiesInStage(ctx, stage)
	if err != nil {
		return nil, err
	}
	seen := map[int]struct{}{}
	out := make([]int, 0, len(rs))
	for _, rr := range rs {
		if _, ok := seen[rr.DeployCohort]; ok {
			continue
		}
		seen[rr.DeployCohort] = struct{}{}
		out = append(out, rr.DeployCohort)
	}
	sort.Ints(out)
	return out, nil
}

// StaticSource is a trivial in-memory RealitySource for tests + dry-run.
type StaticSource struct {
	Realities []Reality
}

// ListActive returns the active subset of the static realities.
func (s *StaticSource) ListActive(_ context.Context) ([]Reality, error) {
	out := make([]Reality, 0, len(s.Realities))
	for _, r := range s.Realities {
		if r.Status == "active" {
			out = append(out, r)
		}
	}
	return out, nil
}
