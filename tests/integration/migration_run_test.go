//go:build integration

package integration

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/canary"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/manifest"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/runner"
)

// migration_run_test.go — L1.D.8 integration test (RAID cycle 6).
//
// Per layer-plan acceptance criteria for L1.D §2:
//   "Apply migration to 10 realities, verify state, verify retry on transient
//    fail, verify dead-letter on persistent fail"
//
// This test does not require an actual Postgres stack — it wires the
// orchestrator's runner against an in-memory Applier that simulates per-
// reality DB behavior. The integration we're proving here is between the
// shipped Go packages (runner + manifest + canary), not the live SQL apply.
// The actual SQL apply integration ships in cycle 7+ (L1.C ↔ L1.D live
// MetaWriter wiring), tracked in docs/deferred/DEFERRED.md.

const (
	manifestPath = "../../contracts/migrations/manifest.yaml"
)

// fakeAuditor records all events for later assertions.
type fakeAuditor struct {
	mu     sync.Mutex
	events []runner.AuditEvent
}

func (a *fakeAuditor) RecordEvent(_ context.Context, ev runner.AuditEvent) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.events = append(a.events, ev)
	return nil
}

func (a *fakeAuditor) count(evtype string) int {
	a.mu.Lock()
	defer a.mu.Unlock()
	n := 0
	for _, e := range a.events {
		if e.EventType == evtype {
			n++
		}
	}
	return n
}

type fakeState struct {
	mu      sync.Mutex
	applied map[string]bool
	failed  map[string]string
}

func newFakeState() *fakeState {
	return &fakeState{applied: map[string]bool{}, failed: map[string]string{}}
}
func (s *fakeState) MarkApplied(_ context.Context, r, m string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.applied[r+"|"+m] = true
	return nil
}
func (s *fakeState) MarkFailed(_ context.Context, r, m, reason string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failed[r+"|"+m] = reason
	return nil
}

// scriptedApplier maps reality_id → ordered outcome sequence so we can
// pin transient-then-success and always-fail per reality.
type scriptedApplier struct {
	mu        sync.Mutex
	calls     map[string]int
	scripts   map[string][]applyOutcome
	concurMax int64
	concur    int64
}

type applyOutcome struct {
	succ bool
	err  error
}

func (a *scriptedApplier) Apply(_ context.Context, r, _ string) (bool, error) {
	cur := atomic.AddInt64(&a.concur, 1)
	for {
		max := atomic.LoadInt64(&a.concurMax)
		if cur <= max || atomic.CompareAndSwapInt64(&a.concurMax, max, cur) {
			break
		}
	}
	time.Sleep(2 * time.Millisecond) // hold the slot
	defer atomic.AddInt64(&a.concur, -1)

	a.mu.Lock()
	defer a.mu.Unlock()
	a.calls[r]++
	steps := a.scripts[r]
	if len(steps) == 0 {
		return true, nil
	}
	next := steps[0]
	a.scripts[r] = steps[1:]
	return next.succ, next.err
}

// instantSleeper avoids real backoff delays.
type instantSleeper struct{}

func (instantSleeper) Sleep(ctx context.Context, _ time.Duration) {}

// TestMigrationRun_TenRealities_VerifyStateAndRetryAndDeadLetter is the
// acceptance test. 10 realities; reality 0+1 transient-then-succeed
// (proves retry); reality 2 always-fails (proves dead-letter); rest go
// through cleanly.
func TestMigrationRun_TenRealities_VerifyStateAndRetryAndDeadLetter(t *testing.T) {
	app := &scriptedApplier{
		calls:   map[string]int{},
		scripts: map[string][]applyOutcome{},
	}
	// reality-0 — fail twice with transient, then succeed
	app.scripts["reality-0"] = []applyOutcome{
		{succ: false, err: fmt.Errorf("conn reset: %w", runner.ErrTransient)},
		{succ: false, err: fmt.Errorf("conn reset: %w", runner.ErrTransient)},
		{succ: true},
	}
	// reality-1 — fail once with transient, then succeed
	app.scripts["reality-1"] = []applyOutcome{
		{succ: false, err: fmt.Errorf("timeout: %w", runner.ErrTransient)},
		{succ: true},
	}
	// reality-2 — always fail transient → dead-letter after 3 attempts
	app.scripts["reality-2"] = []applyOutcome{
		{succ: false, err: fmt.Errorf("hard down: %w", runner.ErrTransient)},
		{succ: false, err: fmt.Errorf("hard down: %w", runner.ErrTransient)},
		{succ: false, err: fmt.Errorf("hard down: %w", runner.ErrTransient)},
	}
	aud := &fakeAuditor{}
	st := newFakeState()

	r, err := runner.New(&runner.Config{
		Concurrency: 10,
		MaxAttempts: 3,
		BaseBackoff: time.Microsecond,
		Applier:     app,
		Auditor:     aud,
		StateWriter: st,
		Sleeper:     instantSleeper{},
	})
	if err != nil {
		t.Fatal(err)
	}

	jobs := make([]runner.Job, 10)
	for i := range jobs {
		jobs[i] = runner.Job{
			RealityID:   fmt.Sprintf("reality-%d", i),
			MigrationID: "0001_initial",
			RunID:       fmt.Sprintf("run-%d", i),
		}
	}
	results := r.Run(context.Background(), jobs)
	if len(results) != 10 {
		t.Fatalf("expected 10 results, got %d", len(results))
	}

	// 9 successes (everyone except reality-2)
	succCount := 0
	for _, res := range results {
		if res.Succeeded {
			succCount++
		}
	}
	if succCount != 9 {
		t.Errorf("expected 9 successes, got %d", succCount)
	}

	// reality-0 attempted 3 times
	if got := app.calls["reality-0"]; got != 3 {
		t.Errorf("reality-0 attempts = %d, want 3", got)
	}
	// reality-2 attempted exactly MaxAttempts and then dead-lettered
	if got := app.calls["reality-2"]; got != 3 {
		t.Errorf("reality-2 attempts = %d, want 3 (dead-letter)", got)
	}
	if reason, ok := st.failed["reality-2|0001_initial"]; !ok || reason != "persistent" {
		t.Errorf("reality-2 should be MarkFailed=persistent, got %v / %v", ok, reason)
	}
	// All other realities should be MarkApplied
	for i := 0; i < 10; i++ {
		if i == 2 {
			continue
		}
		k := fmt.Sprintf("reality-%d|0001_initial", i)
		if !st.applied[k] {
			t.Errorf("expected MarkApplied for %s", k)
		}
	}

	// Audit: 10 starts, 9 succeeds, 1 fail
	if got := aud.count("migration_started"); got != 10 {
		t.Errorf("migration_started count = %d, want 10", got)
	}
	if got := aud.count("migration_succeeded"); got != 9 {
		t.Errorf("migration_succeeded count = %d, want 9", got)
	}
	if got := aud.count("migration_failed"); got != 1 {
		t.Errorf("migration_failed count = %d, want 1", got)
	}

	// Concurrency cap holds (≤ 10 simultaneous)
	if peak := atomic.LoadInt64(&app.concurMax); peak > 10 {
		t.Errorf("peak concurrent applies = %d, must be ≤ 10", peak)
	}
}

// TestMigrationManifest_ReferencesPerRealitySkeleton — pinned regression
// test: cycle 5 ships per-reality 0001_initial.up.sql; the cycle-6
// manifest MUST reference it as the first entry. This is the cross-cycle
// integration guard.
func TestMigrationManifest_ReferencesPerRealitySkeleton(t *testing.T) {
	m, err := manifest.Load(manifestPath)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if m.Migrations[0].ID != "0001_initial" {
		t.Fatalf("manifest first migration = %q, want 0001_initial (cycle 5 skeleton)", m.Migrations[0].ID)
	}
}

// TestCanary_BreakingMigration_OneRealityFirstThenFanout — integration
// guard for the breaking-flow contract.
func TestCanary_BreakingMigration_OneRealityFirstThenFanout(t *testing.T) {
	// Use the canary package directly with a fake dispatcher.
	// Records ordering of dispatcher invocations.
	disp := &recordingDispatcher{}
	abort := &noopAborter{}
	gate := canary.NewVerificationGate()
	go func() { time.Sleep(5 * time.Millisecond); gate.Pass() }()

	o, err := canary.New(&canary.Config{
		Dispatcher:        disp,
		Aborter:           abort,
		VerificationGate:  gate,
		VerificationDelay: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	realities := []string{"r-a", "r-b", "r-c", "r-d", "r-e"}
	outcome, err := o.Run(context.Background(), realities, "0002_breaking")
	if err != nil {
		t.Fatal(err)
	}
	if !outcome.Verified {
		t.Fatal("expected verified outcome")
	}
	if len(disp.calls) != 2 || len(disp.calls[0]) != 1 || len(disp.calls[1]) != 4 {
		t.Fatalf("expected canary(1) then fanout(4); got %v", lensOf(disp.calls))
	}
}

type recordingDispatcher struct {
	mu    sync.Mutex
	calls [][]canary.Job
}

func (d *recordingDispatcher) Run(_ context.Context, jobs []canary.Job) []canary.Result {
	d.mu.Lock()
	defer d.mu.Unlock()
	cp := make([]canary.Job, len(jobs))
	copy(cp, jobs)
	d.calls = append(d.calls, cp)
	out := make([]canary.Result, len(jobs))
	for i, j := range jobs {
		out[i] = canary.Result{Job: j, Succeeded: true, Attempts: 1}
	}
	return out
}

type noopAborter struct{}

func (noopAborter) RecordAbort(_ context.Context, _, _, _, _ string) error { return nil }

func lensOf(c [][]canary.Job) []int {
	out := make([]int, len(c))
	for i, x := range c {
		out[i] = len(x)
	}
	return out
}
