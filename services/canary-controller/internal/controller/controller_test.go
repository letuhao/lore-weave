package controller

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
)

var tc = time.Date(2026, 5, 30, 12, 0, 0, 0, time.UTC)

// ── fakes ────────────────────────────────────────────────────────────────────

type fakeStore struct {
	rec        DeployRecord
	has        bool
	advancedTo canary.Stage
	advanced   bool
	rolledBack bool
	completed  bool
	rbReason   string
}

func (f *fakeStore) ActiveCanary(context.Context) (DeployRecord, bool, error) {
	return f.rec, f.has, nil
}
func (f *fakeStore) AdvanceStage(_ context.Context, _ string, to canary.Stage, _ time.Time, _ string) error {
	f.advanced = true
	f.advancedTo = to
	return nil
}
func (f *fakeStore) MarkRolledBack(_ context.Context, _ string, reason string, _ time.Time) error {
	f.rolledBack = true
	f.rbReason = reason
	return nil
}
func (f *fakeStore) MarkComplete(_ context.Context, _ string, _ time.Time) error {
	f.completed = true
	return nil
}

type fakeSLI struct{ obs canary.Observation }

func (f fakeSLI) Observe(_ context.Context, _ string, _ canary.Stage) (canary.Observation, error) {
	return f.obs, nil
}

type fakeExec struct {
	promotedTo canary.Stage
	promoted   bool
	rolledBack bool
	promoteErr error
}

func (f *fakeExec) Promote(_ context.Context, _ string, to canary.Stage) error {
	if f.promoteErr != nil {
		return f.promoteErr
	}
	f.promoted = true
	f.promotedTo = to
	return nil
}
func (f *fakeExec) Rollback(context.Context, string, string) error {
	f.rolledBack = true
	return nil
}

type fakePager struct{ paged bool }

func (f *fakePager) PageSRE(context.Context, string, string) error { f.paged = true; return nil }

func newCtl(t *testing.T, store *fakeStore, sli fakeSLI, exec *fakeExec, pager *fakePager) *Controller {
	t.Helper()
	c, err := New(store, sli, exec, pager, func() time.Time { return tc })
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return c
}

// ── tests ────────────────────────────────────────────────────────────────────

func TestNew_NilDeps(t *testing.T) {
	if _, err := New(nil, fakeSLI{}, &fakeExec{}, &fakePager{}, nil); err == nil {
		t.Fatal("nil store must error")
	}
}

func TestTick_NoActiveCanary_NoOp(t *testing.T) {
	c := newCtl(t, &fakeStore{has: false}, fakeSLI{}, &fakeExec{}, &fakePager{})
	_, ok, err := c.Tick(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Error("no active canary must yield ok=false")
	}
}

func TestTick_Advance_HealthyWindowElapsed(t *testing.T) {
	store := &fakeStore{has: true, rec: DeployRecord{
		DeployID: "d1", Class: "major", Stage: canary.Stage1pct,
		StageEntered: tc.Add(-31 * time.Minute), BaselineBurn: 0.5,
	}}
	exec := &fakeExec{}
	pager := &fakePager{}
	c := newCtl(t, store, fakeSLI{obs: canary.Observation{CohortBurn: 0.6, Now: tc}}, exec, pager)

	res, ok, err := c.Tick(context.Background())
	if err != nil || !ok {
		t.Fatalf("tick err=%v ok=%v", err, ok)
	}
	if res.Action != canary.ActionAdvance {
		t.Fatalf("action = %s want advance", res.Action)
	}
	if !exec.promoted || exec.promotedTo != canary.Stage10pct {
		t.Errorf("expected promote to stage 2, got promoted=%v to=%d", exec.promoted, exec.promotedTo)
	}
	if !store.advanced || store.advancedTo != canary.Stage10pct {
		t.Errorf("expected store advance to stage 2")
	}
	if pager.paged {
		t.Error("healthy advance must not page SRE")
	}
}

func TestTick_Abort_OnBurnBreach_RollsBackAndPages(t *testing.T) {
	store := &fakeStore{has: true, rec: DeployRecord{
		DeployID: "d2", Class: "major", Stage: canary.Stage10pct,
		StageEntered: tc.Add(-5 * time.Minute), BaselineBurn: 0.5,
	}}
	exec := &fakeExec{}
	pager := &fakePager{}
	// burn 1.5 > 2× 0.5 = 1.0 → abort.
	c := newCtl(t, store, fakeSLI{obs: canary.Observation{CohortBurn: 1.5, Now: tc}}, exec, pager)

	res, ok, err := c.Tick(context.Background())
	if err != nil || !ok {
		t.Fatalf("tick err=%v ok=%v", err, ok)
	}
	if res.Action != canary.ActionAbort {
		t.Fatalf("action = %s want abort", res.Action)
	}
	if !exec.rolledBack {
		t.Error("abort must trigger rollback")
	}
	if !store.rolledBack || store.rbReason == "" {
		t.Error("abort must mark deploy_audit rolled_back with a reason")
	}
	if !pager.paged {
		t.Error("abort must page SRE")
	}
}

func TestTick_Hold_WindowNotElapsed(t *testing.T) {
	store := &fakeStore{has: true, rec: DeployRecord{
		DeployID: "d3", Class: "major", Stage: canary.Stage1pct,
		StageEntered: tc.Add(-5 * time.Minute), BaselineBurn: 0.5,
	}}
	exec := &fakeExec{}
	c := newCtl(t, store, fakeSLI{obs: canary.Observation{CohortBurn: 0.6, Now: tc}}, exec, &fakePager{})
	res, _, err := c.Tick(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Action != canary.ActionHold {
		t.Errorf("action = %s want hold", res.Action)
	}
	if exec.promoted {
		t.Error("hold must not promote")
	}
}

func TestTick_Complete_AtFullStage(t *testing.T) {
	store := &fakeStore{has: true, rec: DeployRecord{
		DeployID: "d4", Class: "major", Stage: canary.StageFull, StageEntered: tc,
	}}
	c := newCtl(t, store, fakeSLI{obs: canary.Observation{Now: tc}}, &fakeExec{}, &fakePager{})
	res, _, err := c.Tick(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Action != canary.ActionComplete {
		t.Errorf("action = %s want complete", res.Action)
	}
	if !store.completed {
		t.Error("complete must mark completed_at")
	}
}

func TestTick_PromoteError_Surfaces_NoAdvancePersisted(t *testing.T) {
	store := &fakeStore{has: true, rec: DeployRecord{
		DeployID: "d5", Class: "major", Stage: canary.Stage1pct,
		StageEntered: tc.Add(-1 * time.Hour), BaselineBurn: 0.5,
	}}
	exec := &fakeExec{promoteErr: errors.New("deploy tooling down")}
	c := newCtl(t, store, fakeSLI{obs: canary.Observation{CohortBurn: 0.6, Now: tc}}, exec, &fakePager{})
	_, _, err := c.Tick(context.Background())
	if err == nil {
		t.Fatal("promote error must surface")
	}
	if store.advanced {
		t.Error("stage must NOT be persisted when promote fails (no phantom advance)")
	}
}
