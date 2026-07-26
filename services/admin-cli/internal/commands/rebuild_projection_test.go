package commands

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// db-safety-gate: file-ok — a pure unit test over fakeLifecycle / fakeTruncator mocks and
// assertion messages ("truncate" is a mock call-log label, not SQL); it never connects to
// or executes anything against a real database.

type fakeLifecycle struct {
	freezeErr, thawErr error
	calls              []string
}

func (f *fakeLifecycle) FreezeForRebuild(_ context.Context, _ uuid.UUID, _, _ string) error {
	f.calls = append(f.calls, "freeze")
	return f.freezeErr
}

func (f *fakeLifecycle) ThawAfterRebuild(_ context.Context, _ uuid.UUID, _, _ string) error {
	f.calls = append(f.calls, "thaw")
	return f.thawErr
}

type fakeTruncator struct {
	err   error
	calls []string
}

func (f *fakeTruncator) Truncate(_ context.Context, _ uuid.UUID, _ string) error {
	f.calls = append(f.calls, "truncate")
	return f.err
}

type fakeInvoker struct {
	stats RebuildStats
	err   error
	calls []string
}

func (f *fakeInvoker) Rebuild(_ context.Context, _ uuid.UUID, _ string) (RebuildStats, error) {
	f.calls = append(f.calls, "rebuild")
	return f.stats, f.err
}

func validRebuildReq() RebuildProjectionRequest {
	return RebuildProjectionRequest{
		RealityID:      uuid.New(),
		ProjectionName: "pc_projection",
		Actor:          uuid.NewString(),
		Reason:         "post-corruption rebuild after INC-77",
		Confirm:        true,
	}
}

func newFakeDeps() (*fakeLifecycle, *fakeTruncator, *fakeInvoker, RebuildProjectionDeps) {
	l, t, i := &fakeLifecycle{}, &fakeTruncator{}, &fakeInvoker{stats: RebuildStats{AggregatesRebuilt: 3, EventsReplayed: 12}}
	return l, t, i, RebuildProjectionDeps{Lifecycle: l, Truncator: t, Invoker: i}
}

func TestRunRebuildProjection_HappyPath(t *testing.T) {
	l, tr, iv, deps := newFakeDeps()
	out, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err != nil {
		t.Fatalf("happy path: %v", err)
	}
	if got := strings.Join(l.calls, ","); got != "freeze,thaw" {
		t.Errorf("lifecycle calls = %q, want freeze,thaw", got)
	}
	if len(tr.calls) != 1 || len(iv.calls) != 1 {
		t.Errorf("expected one truncate + one rebuild, got %v / %v", tr.calls, iv.calls)
	}
	if !strings.Contains(out, "rebuilt") || !strings.Contains(out, "thawed") {
		t.Errorf("summary missing success markers:\n%s", out)
	}
}

func TestRunRebuildProjection_DryRunDoesNothing(t *testing.T) {
	l, tr, iv, deps := newFakeDeps()
	req := validRebuildReq()
	req.Confirm = false
	req.DryRun = true
	out, err := RunRebuildProjection(context.Background(), req, deps)
	if err != nil {
		t.Fatalf("dry-run: %v", err)
	}
	if len(l.calls)+len(tr.calls)+len(iv.calls) != 0 {
		t.Errorf("dry-run must touch nothing, got %v %v %v", l.calls, tr.calls, iv.calls)
	}
	if !strings.Contains(out, "DRY-RUN") {
		t.Errorf("dry-run output missing marker:\n%s", out)
	}
}

func TestRunRebuildProjection_FreezeFailsNoTruncate(t *testing.T) {
	l, tr, _, deps := newFakeDeps()
	l.freezeErr = errors.New("CAS conflict")
	_, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err == nil || !strings.Contains(err.Error(), "no changes made") {
		t.Fatalf("freeze failure must abort before truncate, got %v", err)
	}
	if len(tr.calls) != 0 {
		t.Errorf("truncate must NOT run when freeze fails")
	}
}

func TestRunRebuildProjection_TruncateFailsAttemptsThaw(t *testing.T) {
	l, tr, iv, deps := newFakeDeps()
	tr.err = errors.New("lock timeout")
	_, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err == nil || !strings.Contains(err.Error(), "thaw attempted") {
		t.Fatalf("truncate failure must attempt thaw, got %v", err)
	}
	if got := strings.Join(l.calls, ","); got != "freeze,thaw" {
		t.Errorf("expected freeze then rollback thaw, got %q", got)
	}
	if len(iv.calls) != 0 {
		t.Errorf("rebuild must NOT run when truncate fails")
	}
}

func TestRunRebuildProjection_RebuildErrorLeavesFrozen(t *testing.T) {
	l, _, iv, deps := newFakeDeps()
	iv.err = errors.New("rebuilder exited 2")
	_, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err == nil || !strings.Contains(err.Error(), "LEFT FROZEN") {
		t.Fatalf("rebuild error must leave frozen, got %v", err)
	}
	if got := strings.Join(l.calls, ","); got != "freeze" {
		t.Errorf("must NOT thaw on rebuild error, calls = %q", got)
	}
}

func TestRunRebuildProjection_FailedAggregatesLeavesFrozen(t *testing.T) {
	l, _, iv, deps := newFakeDeps()
	iv.stats = RebuildStats{AggregatesRebuilt: 2, AggregatesFailed: 1}
	_, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err == nil || !strings.Contains(err.Error(), "LEFT FROZEN") {
		t.Fatalf("dead-lettered aggregate must leave frozen, got %v", err)
	}
	if got := strings.Join(l.calls, ","); got != "freeze" {
		t.Errorf("must NOT thaw with failed aggregates, calls = %q", got)
	}
}

func TestRunRebuildProjection_ThawFailureSurfaced(t *testing.T) {
	l, _, _, deps := newFakeDeps()
	l.thawErr = errors.New("CAS conflict on thaw")
	_, err := RunRebuildProjection(context.Background(), validRebuildReq(), deps)
	if err == nil || !strings.Contains(err.Error(), "thaw FAILED") {
		t.Fatalf("thaw failure must surface (left frozen), got %v", err)
	}
}

func TestRunRebuildProjection_RejectsUnknownProjection(t *testing.T) {
	_, _, _, deps := newFakeDeps()
	req := validRebuildReq()
	req.ProjectionName = "reality_registry"
	if _, err := RunRebuildProjection(context.Background(), req, deps); !errors.Is(err, ErrInvalidRebuild) {
		t.Fatalf("unknown projection must reject, got %v", err)
	}
}
