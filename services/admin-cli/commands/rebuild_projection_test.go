package commands

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

func rebuildFixedClock(t time.Time) ClockFn { return func() time.Time { return t } }

// ── Test fakes ──────────────────────────────────────────────────────────────

type fakeLifecycle struct {
	mu             sync.Mutex
	freezeCalls    []string // realityID per call
	thawCalls      []string
	failFreeze     bool
	failThaw       bool
	frozenReality  string // tracks current state — non-empty = frozen
	frozenAtNanos  int64
}

func (f *fakeLifecycle) FreezeForRebuild(_ context.Context, realityID, _, _ string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failFreeze {
		return errors.New("freeze failed")
	}
	f.freezeCalls = append(f.freezeCalls, realityID)
	f.frozenReality = realityID
	f.frozenAtNanos = time.Now().UnixNano()
	return nil
}
func (f *fakeLifecycle) ThawAfterRebuild(_ context.Context, realityID, _, _ string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failThaw {
		return errors.New("thaw failed")
	}
	f.thawCalls = append(f.thawCalls, realityID)
	f.frozenReality = ""
	return nil
}
func (f *fakeLifecycle) isFrozen() bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.frozenReality != ""
}

type fakeTruncator struct {
	calls    []string // realityID:projectionName per call
	fail     bool
}

func (f *fakeTruncator) Truncate(_ context.Context, realityID, projectionName string) error {
	if f.fail {
		return errors.New("truncate failed")
	}
	f.calls = append(f.calls, realityID+":"+projectionName)
	return nil
}

type fakeInvoker struct {
	stats RebuildStats
	err   error
	calls []string
	// Tracks whether reality was frozen when Rebuild() was invoked.
	wasFrozenAtInvoke bool
	lifecycle         *fakeLifecycle
}

func (f *fakeInvoker) Rebuild(_ context.Context, realityID, projectionName string) (RebuildStats, error) {
	f.calls = append(f.calls, realityID+":"+projectionName)
	if f.lifecycle != nil {
		f.wasFrozenAtInvoke = f.lifecycle.isFrozen()
	}
	return f.stats, f.err
}

type fakeAudit struct {
	transitions []AuditTransition
}

func (f *fakeAudit) WriteTransition(_ context.Context, t AuditTransition) error {
	f.transitions = append(f.transitions, t)
	return nil
}

// ── Validation tests ───────────────────────────────────────────────────────

func TestValidate_RejectsMissingReality(t *testing.T) {
	r := RebuildProjectionRequest{ProjectionName: "pc", Actor: "a", Reason: "r", Confirm: true}
	if err := r.Validate(); err == nil || !errors.Is(err, ErrInvalidRebuild) {
		t.Fatalf("want ErrInvalidRebuild, got %v", err)
	}
}

func TestValidate_RejectsMissingProjection(t *testing.T) {
	r := RebuildProjectionRequest{RealityID: "u", Actor: "a", Reason: "r", Confirm: true}
	if err := r.Validate(); err == nil || !errors.Is(err, ErrInvalidRebuild) {
		t.Fatalf("want ErrInvalidRebuild, got %v", err)
	}
}

func TestValidate_RejectsMissingConfirmWhenNotDryRun(t *testing.T) {
	r := RebuildProjectionRequest{RealityID: "u", ProjectionName: "pc", Actor: "a", Reason: "r"}
	err := r.Validate()
	if err == nil || !errors.Is(err, ErrInvalidRebuild) {
		t.Fatalf("want ErrInvalidRebuild, got %v", err)
	}
	if !strings.Contains(err.Error(), "--confirm") {
		t.Fatalf("error must mention --confirm, got: %v", err)
	}
}

func TestValidate_AllowsDryRunWithoutConfirm(t *testing.T) {
	r := RebuildProjectionRequest{RealityID: "u", ProjectionName: "pc", Actor: "a", Reason: "r", DryRun: true}
	if err := r.Validate(); err != nil {
		t.Fatalf("dry-run should be allowed without --confirm: %v", err)
	}
}

func TestValidate_RejectsFreezeTimeoutOverCap(t *testing.T) {
	r := RebuildProjectionRequest{
		RealityID: "u", ProjectionName: "pc", Actor: "a", Reason: "r", Confirm: true,
		FreezeTimeout: 60 * time.Minute,
	}
	if err := r.Validate(); err == nil || !errors.Is(err, ErrInvalidRebuild) {
		t.Fatalf("want ErrInvalidRebuild, got %v", err)
	}
}

// ── Apply happy path ───────────────────────────────────────────────────────

func TestApply_HappyPath_FreezeTruncateRebuildThaw(t *testing.T) {
	lc := &fakeLifecycle{}
	tr := &fakeTruncator{}
	in := &fakeInvoker{
		stats:     RebuildStats{AggregatesRebuilt: 10, EventsReplayed: 100},
		lifecycle: lc,
	}
	au := &fakeAudit{}
	deps := RebuildDeps{
		Lifecycle: lc,
		Truncator: tr,
		Invoker:   in,
		Audit:     au,
		Clock:     rebuildFixedClock(time.Unix(1000, 0)),
	}
	req := RebuildProjectionRequest{
		RealityID:      "reality-1",
		ProjectionName: "pc_projection",
		Actor:          "ops@loreweave",
		Reason:         "drift detected by L3.E sampler",
		Confirm:        true,
	}

	res, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err != nil {
		t.Fatalf("Apply failed: %v", err)
	}
	if res.AggregatesRebuilt != 10 || res.EventsReplayed != 100 {
		t.Fatalf("bad stats in result: %+v", res)
	}
	if len(lc.freezeCalls) != 1 || lc.freezeCalls[0] != "reality-1" {
		t.Fatalf("freeze not called once on reality-1: %v", lc.freezeCalls)
	}
	if len(lc.thawCalls) != 1 || lc.thawCalls[0] != "reality-1" {
		t.Fatalf("thaw not called once on reality-1: %v", lc.thawCalls)
	}
	if len(tr.calls) != 1 || tr.calls[0] != "reality-1:pc_projection" {
		t.Fatalf("truncate not called: %v", tr.calls)
	}
	if !in.wasFrozenAtInvoke {
		t.Fatal("rebuilder must run while reality is frozen")
	}
	// Audit: two transitions (active→rebuilding, rebuilding→active).
	if len(au.transitions) != 2 {
		t.Fatalf("want 2 audit transitions, got %d", len(au.transitions))
	}
	if au.transitions[0].FromState != "active" || au.transitions[0].ToState != "rebuilding" {
		t.Fatalf("first transition wrong: %+v", au.transitions[0])
	}
	if au.transitions[1].FromState != "rebuilding" || au.transitions[1].ToState != "active" {
		t.Fatalf("second transition wrong: %+v", au.transitions[1])
	}
}

// ── Dry-run path ───────────────────────────────────────────────────────────

func TestApply_DryRun_NoStateChanges(t *testing.T) {
	lc := &fakeLifecycle{}
	tr := &fakeTruncator{}
	in := &fakeInvoker{lifecycle: lc}
	au := &fakeAudit{}
	deps := RebuildDeps{Lifecycle: lc, Truncator: tr, Invoker: in, Audit: au, Clock: rebuildFixedClock(time.Unix(0, 0))}
	req := RebuildProjectionRequest{
		RealityID: "r", ProjectionName: "pc", Actor: "a", Reason: "preview", DryRun: true,
	}
	res, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err != nil {
		t.Fatalf("dry-run Apply: %v", err)
	}
	if !res.DryRun {
		t.Fatal("DryRun flag not propagated")
	}
	if len(lc.freezeCalls) != 0 || len(tr.calls) != 0 || len(in.calls) != 0 {
		t.Fatalf("dry-run mutated state: freeze=%d trunc=%d invoke=%d", len(lc.freezeCalls), len(tr.calls), len(in.calls))
	}
}

// ── Failure paths ──────────────────────────────────────────────────────────

func TestApply_FreezeFails_NoTruncateNoInvoke(t *testing.T) {
	lc := &fakeLifecycle{failFreeze: true}
	tr := &fakeTruncator{}
	in := &fakeInvoker{}
	au := &fakeAudit{}
	deps := RebuildDeps{Lifecycle: lc, Truncator: tr, Invoker: in, Audit: au, Clock: rebuildFixedClock(time.Unix(0, 0))}
	req := RebuildProjectionRequest{RealityID: "r", ProjectionName: "pc", Actor: "a", Reason: "x", Confirm: true}
	_, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err == nil || !strings.Contains(err.Error(), "freeze") {
		t.Fatalf("want freeze error, got %v", err)
	}
	if len(tr.calls) != 0 {
		t.Fatal("truncate must NOT be called if freeze fails")
	}
	if len(in.calls) != 0 {
		t.Fatal("rebuild must NOT be called if freeze fails")
	}
}

func TestApply_TruncateFails_AttemptsThaw(t *testing.T) {
	lc := &fakeLifecycle{}
	tr := &fakeTruncator{fail: true}
	in := &fakeInvoker{}
	au := &fakeAudit{}
	deps := RebuildDeps{Lifecycle: lc, Truncator: tr, Invoker: in, Audit: au, Clock: rebuildFixedClock(time.Unix(0, 0))}
	req := RebuildProjectionRequest{RealityID: "r", ProjectionName: "pc", Actor: "a", Reason: "x", Confirm: true}
	_, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err == nil || !strings.Contains(err.Error(), "truncate") {
		t.Fatalf("want truncate error, got %v", err)
	}
	if len(lc.thawCalls) != 1 {
		t.Fatalf("rollback thaw not attempted: %v", lc.thawCalls)
	}
	if len(in.calls) != 0 {
		t.Fatal("rebuild must NOT be called if truncate fails")
	}
}

func TestApply_RebuildFails_LeavesFrozen(t *testing.T) {
	lc := &fakeLifecycle{}
	tr := &fakeTruncator{}
	in := &fakeInvoker{err: errors.New("rebuilder crashed"), lifecycle: lc}
	au := &fakeAudit{}
	deps := RebuildDeps{Lifecycle: lc, Truncator: tr, Invoker: in, Audit: au, Clock: rebuildFixedClock(time.Unix(0, 0))}
	req := RebuildProjectionRequest{RealityID: "r", ProjectionName: "pc", Actor: "a", Reason: "x", Confirm: true}
	_, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err == nil || !strings.Contains(err.Error(), "FROZEN") {
		t.Fatalf("error must signal frozen state, got %v", err)
	}
	if !lc.isFrozen() {
		t.Fatal("reality must remain frozen so operator can inspect dead letter")
	}
	if len(lc.thawCalls) != 0 {
		t.Fatal("must NOT thaw on rebuild failure (operator decides)")
	}
}

func TestApply_PartialFailedAggregates_LeavesFrozen(t *testing.T) {
	lc := &fakeLifecycle{}
	tr := &fakeTruncator{}
	in := &fakeInvoker{
		stats:     RebuildStats{AggregatesRebuilt: 8, AggregatesFailed: 2, EventsReplayed: 80},
		lifecycle: lc,
	}
	au := &fakeAudit{}
	deps := RebuildDeps{Lifecycle: lc, Truncator: tr, Invoker: in, Audit: au, Clock: rebuildFixedClock(time.Unix(0, 0))}
	req := RebuildProjectionRequest{RealityID: "r", ProjectionName: "pc", Actor: "a", Reason: "x", Confirm: true}
	_, err := ApplyRebuildProjection(context.Background(), req, deps)
	if err == nil || !strings.Contains(err.Error(), "FROZEN") {
		t.Fatalf("want frozen error on partial failure, got %v", err)
	}
	if !lc.isFrozen() {
		t.Fatal("reality must remain frozen on partial failure")
	}
}
