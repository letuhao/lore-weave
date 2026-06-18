package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	rr "github.com/loreweave/foundation/services/admin-cli/internal/rolling_rebuild"
)

type rrStats = rr.PerRealityStats

func twoProjections() []string { return []string{"pc_projection", "npc_projection"} }

func resolverFor(tr ProjectionTruncator, iv RebuildInvoker) PerRealityResolver {
	return func(_ context.Context, _ uuid.UUID) (ProjectionTruncator, RebuildInvoker, func(), error) {
		return tr, iv, func() {}, nil
	}
}

func TestMultiProjectionRebuilder_HappyPath(t *testing.T) {
	l := &fakeLifecycle{}
	tr := &fakeTruncator{}
	iv := &fakeInvoker{stats: RebuildStats{AggregatesRebuilt: 2, EventsReplayed: 5}}
	m := &MultiProjectionRebuilder{Lifecycle: l, Resolve: resolverFor(tr, iv), Projections: twoProjections()}

	stats, err := m.RebuildReality(context.Background(), uuid.NewString(), uuid.NewString(), "rebuild reason here")
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if stats.ProjectionsTried != 2 || stats.ProjectionsOK != 2 {
		t.Errorf("projections tried/ok = %d/%d, want 2/2", stats.ProjectionsTried, stats.ProjectionsOK)
	}
	if got := strings.Join(l.calls, ","); got != "freeze,thaw" {
		t.Errorf("lifecycle = %q, want freeze,thaw (frozen once, thawed once)", got)
	}
	if len(tr.calls) != 2 || len(iv.calls) != 2 {
		t.Errorf("expected 2 truncates + 2 rebuilds, got %d/%d", len(tr.calls), len(iv.calls))
	}
	if stats.AggregatesRebuilt != 4 {
		t.Errorf("aggregates rebuilt = %d, want 4 (2 per projection)", stats.AggregatesRebuilt)
	}
}

func TestMultiProjectionRebuilder_FailedProjectionLeavesFrozen(t *testing.T) {
	l := &fakeLifecycle{}
	tr := &fakeTruncator{}
	iv := &fakeInvoker{stats: RebuildStats{AggregatesFailed: 1}}
	m := &MultiProjectionRebuilder{Lifecycle: l, Resolve: resolverFor(tr, iv), Projections: twoProjections()}

	_, err := m.RebuildReality(context.Background(), uuid.NewString(), uuid.NewString(), "reason here ok")
	if err == nil || !strings.Contains(err.Error(), "LEFT FROZEN") {
		t.Fatalf("failed projection must leave frozen, got %v", err)
	}
	if got := strings.Join(l.calls, ","); got != "freeze" {
		t.Errorf("must NOT thaw after failure, calls = %q", got)
	}
}

// fakeRebuilder lets RunCatastrophicRebuild be tested without per-reality wiring.
type fakeRebuilder struct {
	failIDs map[string]bool
}

func (f *fakeRebuilder) RebuildReality(_ context.Context, realityID, _, _ string) (rrStats, error) {
	if f.failIDs[realityID] {
		return rrStats{RealityID: realityID}, errors.New("boom")
	}
	return rrStats{RealityID: realityID, ProjectionsOK: 1}, nil
}

func validCatReq(ids []string) CatastrophicRebuildRequest {
	return CatastrophicRebuildRequest{
		Scope: "aggregate-list", RealityIDs: ids, Actor: uuid.NewString(),
		Reason: "mass rebuild after schema fix", Confirm: true,
		RollingConcurrency: 4, PerRealityTimeout: time.Minute,
	}
}

func TestRunCatastrophicRebuild_AllOK(t *testing.T) {
	ids := []string{uuid.NewString(), uuid.NewString()}
	out, err := RunCatastrophicRebuild(context.Background(), validCatReq(ids), &fakeRebuilder{})
	if err != nil {
		t.Fatalf("all-ok: %v", err)
	}
	if !strings.Contains(out, "2 OK, 0 FAILED") {
		t.Errorf("summary: %s", out)
	}
}

func TestRunCatastrophicRebuild_FailedRealitySurfaced(t *testing.T) {
	bad := uuid.NewString()
	ids := []string{uuid.NewString(), bad}
	_, err := RunCatastrophicRebuild(context.Background(), validCatReq(ids), &fakeRebuilder{failIDs: map[string]bool{bad: true}})
	if err == nil || !strings.Contains(err.Error(), "LEFT FROZEN") || !strings.Contains(err.Error(), bad) {
		t.Fatalf("failed reality must surface, got %v", err)
	}
}

func TestRunCatastrophicRebuild_DryRun(t *testing.T) {
	req := validCatReq([]string{uuid.NewString()})
	req.Confirm = false
	req.DryRun = true
	out, err := RunCatastrophicRebuild(context.Background(), req, &fakeRebuilder{failIDs: map[string]bool{}})
	if err != nil {
		t.Fatalf("dry-run: %v", err)
	}
	if !strings.Contains(out, "DRY-RUN") {
		t.Errorf("dry-run marker missing: %s", out)
	}
}

func TestCatastrophicRequest_Validate(t *testing.T) {
	good := validCatReq([]string{uuid.NewString()})
	if err := good.Validate(); err != nil {
		t.Fatalf("valid request rejected: %v", err)
	}
	bad := good
	bad.Scope = "nonsense"
	if err := bad.Validate(); !errors.Is(err, ErrInvalidCatastrophic) {
		t.Errorf("bad scope must reject")
	}
	bad = good
	bad.RollingConcurrency = 51
	if err := bad.Validate(); !errors.Is(err, ErrInvalidCatastrophic) {
		t.Errorf("concurrency > 50 must reject")
	}
}
