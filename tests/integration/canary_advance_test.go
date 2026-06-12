//go:build integration

package integration

import (
	"context"
	"testing"
	"time"

	cf "github.com/loreweave/foundation/services/canary-controller/pkg/canaryflow"
)

// ── in-memory deploy_audit store backed by a DeployRecord ────────────────────

type memDeployStore struct {
	rec       cf.DeployRecord
	has       bool
	advances  []cf.Stage
	rolled    bool
	completed bool
}

func (m *memDeployStore) ActiveCanary(context.Context) (cf.DeployRecord, bool, error) {
	return m.rec, m.has, nil
}
func (m *memDeployStore) AdvanceStage(_ context.Context, _ string, to cf.Stage, at time.Time, _ string) error {
	m.advances = append(m.advances, to)
	m.rec.Stage = to
	m.rec.StageEntered = at
	return nil
}
func (m *memDeployStore) MarkRolledBack(_ context.Context, _ string, _ string, _ time.Time) error {
	m.rolled = true
	m.has = false
	return nil
}
func (m *memDeployStore) MarkComplete(_ context.Context, _ string, _ time.Time) error {
	m.completed = true
	m.has = false
	return nil
}

// programmable SLI source — yields a single (mutable) reading.
type scriptedSLI struct{ obs cf.Observation }

func (s *scriptedSLI) Observe(_ context.Context, _ string, _ cf.Stage) (cf.Observation, error) {
	return s.obs, nil
}

type recExec struct {
	promotes  []cf.Stage
	rollbacks int
}

func (e *recExec) Promote(_ context.Context, _ string, to cf.Stage) error {
	e.promotes = append(e.promotes, to)
	return nil
}
func (e *recExec) Rollback(context.Context, string, string) error { e.rollbacks++; return nil }

type recPager struct{ pages int }

func (p *recPager) PageSRE(context.Context, string, string) error { p.pages++; return nil }

// TestCanaryAdvance_HealthyRolloutThroughAllStages — inject a healthy cohort
// SLI and verify the controller advances 0→1→2→3→4 and marks complete. This is
// the L7.K.10 "verify auto-advance at threshold" acceptance.
func TestCanaryAdvance_HealthyRolloutThroughAllStages(t *testing.T) {
	t0 := time.Date(2026, 5, 30, 9, 0, 0, 0, time.UTC)
	clock := t0
	store := &memDeployStore{
		has: true,
		rec: cf.DeployRecord{
			DeployID: "d-int-1", Class: "major", Stage: cf.StageInternal,
			StageEntered: t0, BaselineBurn: 0.4,
		},
	}
	sli := &scriptedSLI{obs: cf.Observation{CohortBurn: 0.5, ErrorRate: 0}}
	exec := &recExec{}
	pager := &recPager{}

	now := func() time.Time { return clock }
	ctl, err := cf.NewController(store, sli, exec, pager, now)
	if err != nil {
		t.Fatal(err)
	}

	// Walk ticks: each tick jumps the clock past the current stage's window so
	// the healthy SLI advances. The SLI observation carries Now = clock.
	for store.has && !store.completed {
		w := cf.MonitorWindow(store.rec.Stage)
		clock = clock.Add(w + time.Minute)
		sli.obs.Now = clock
		_, ok, err := ctl.Tick(context.Background())
		if err != nil {
			t.Fatalf("tick err: %v", err)
		}
		if !ok {
			break
		}
	}

	if !store.completed {
		t.Fatalf("expected rollout to complete; advances=%v", store.advances)
	}
	wantPromotes := []cf.Stage{cf.Stage1pct, cf.Stage10pct, cf.Stage50pct, cf.StageFull}
	if len(exec.promotes) != len(wantPromotes) {
		t.Fatalf("promotes = %v want %v", exec.promotes, wantPromotes)
	}
	for i, w := range wantPromotes {
		if exec.promotes[i] != w {
			t.Errorf("promote %d = %d want %d", i, exec.promotes[i], w)
		}
	}
	if exec.rollbacks != 0 || pager.pages != 0 {
		t.Errorf("healthy rollout must not rollback (%d) or page (%d)", exec.rollbacks, pager.pages)
	}
}

// TestCanaryAbort_OnCohortBurnOver2xBaseline — inject a cohort SLI burn above
// 2× baseline at stage 2 and verify the controller auto-aborts: rollback fired,
// deploy_audit marked rolled_back, SRE paged. L7.K.10 "verify auto-abort".
func TestCanaryAbort_OnCohortBurnOver2xBaseline(t *testing.T) {
	t0 := time.Date(2026, 5, 30, 9, 0, 0, 0, time.UTC)
	store := &memDeployStore{
		has: true,
		rec: cf.DeployRecord{
			DeployID: "d-int-2", Class: "major", Stage: cf.Stage10pct,
			StageEntered: t0, BaselineBurn: 0.5,
		},
	}
	// baseline 0.5 × 2 = 1.0 threshold; burn 1.8 breaches.
	sli := &scriptedSLI{obs: cf.Observation{CohortBurn: 1.8, Now: t0.Add(10 * time.Minute)}}
	exec := &recExec{}
	pager := &recPager{}
	ctl, _ := cf.NewController(store, sli, exec, pager, func() time.Time { return t0.Add(10 * time.Minute) })

	res, ok, err := ctl.Tick(context.Background())
	if err != nil || !ok {
		t.Fatalf("tick err=%v ok=%v", err, ok)
	}
	if res.Action != cf.ActionAbort {
		t.Fatalf("action = %v want abort", res.Action)
	}
	if exec.rollbacks != 1 {
		t.Errorf("expected 1 rollback, got %d", exec.rollbacks)
	}
	if !store.rolled {
		t.Error("deploy_audit must be marked rolled_back")
	}
	if pager.pages != 1 {
		t.Error("SRE must be paged on auto-abort")
	}
}

// TestCohortRouter_StagesGateRealities — the cohort router + canary stage table
// together gate which realities are live at each stage (cross-package contract).
func TestCohortRouter_StagesGateRealities(t *testing.T) {
	src := &cf.StaticSource{Realities: []cf.Reality{
		{RealityID: "r0", DeployCohort: 0, Tier: "free", Status: "active"},
		{RealityID: "r7", DeployCohort: 7, Tier: "paid", Status: "active"},
		{RealityID: "r40", DeployCohort: 40, Tier: "premium", Status: "active"},
		{RealityID: "r88", DeployCohort: 88, Tier: "free", Status: "active"},
	}}
	r, err := cf.NewRouter(src)
	if err != nil {
		t.Fatal(err)
	}
	// stage 1 (1%) → only cohort 0
	got, _ := r.RealitiesInStage(context.Background(), cf.Stage1pct)
	if len(got) != 1 || got[0].RealityID != "r0" {
		t.Errorf("stage1 realities = %+v want [r0]", got)
	}
	// stage 2 (10%) → cohorts 0..10 → r0 + r7
	got, _ = r.RealitiesInStage(context.Background(), cf.Stage10pct)
	if len(got) != 2 {
		t.Errorf("stage2 realities = %d want 2", len(got))
	}
	// stage 4 (100%) → all 4
	got, _ = r.RealitiesInStage(context.Background(), cf.StageFull)
	if len(got) != 4 {
		t.Errorf("stage4 realities = %d want 4", len(got))
	}
}

// TestDeployClassify_FromSignals — the classification re-export used by deploy.yml.
func TestDeployClassify_FromSignals(t *testing.T) {
	if got := cf.Classify(cf.Signals{ChangedFiles: []string{"services/a/x.go", "services/b/y.go"}}); got != cf.ClassMajor {
		t.Errorf("multi-service = %v want major", got)
	}
	if got := cf.Classify(cf.Signals{ChangedFiles: []string{"services/a/x.go"}}); got != cf.ClassPatch {
		t.Errorf("single-service = %v want patch", got)
	}
}
