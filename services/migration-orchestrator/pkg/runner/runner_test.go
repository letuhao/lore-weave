package runner

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeApplier records calls + can be primed to fail N times then succeed.
type fakeApplier struct {
	mu        sync.Mutex
	calls     map[string]int            // (reality,migration) → attempt count
	failUntil map[string]int            // fail first N attempts then succeed
	always    map[string]error          // always return this error (overrides failUntil)
	peak      *PeakConcurrency
	delay     time.Duration             // simulated work
}

func newFakeApplier() *fakeApplier {
	return &fakeApplier{
		calls:     map[string]int{},
		failUntil: map[string]int{},
		always:    map[string]error{},
		peak:      &PeakConcurrency{},
	}
}

func key(r, m string) string { return r + "|" + m }

func (f *fakeApplier) Apply(ctx context.Context, r, m string) (bool, error) {
	f.peak.Enter()
	defer f.peak.Exit()
	if f.delay > 0 {
		// Hold the slot so peak concurrency is observable.
		time.Sleep(f.delay)
	}

	f.mu.Lock()
	defer f.mu.Unlock()
	k := key(r, m)
	f.calls[k]++

	if err, ok := f.always[k]; ok {
		return false, err
	}
	if remaining, ok := f.failUntil[k]; ok && remaining > 0 {
		f.failUntil[k] = remaining - 1
		return false, fmt.Errorf("transient: attempt left=%d: %w", remaining-1, ErrTransient)
	}
	return true, nil
}

type fakeAuditor struct {
	mu     sync.Mutex
	events []AuditEvent
}

func (a *fakeAuditor) RecordEvent(_ context.Context, ev AuditEvent) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.events = append(a.events, ev)
	return nil
}

func (a *fakeAuditor) eventsFor(reality, migration, evtype string) int {
	a.mu.Lock()
	defer a.mu.Unlock()
	n := 0
	for _, e := range a.events {
		if e.RealityID == reality && e.MigrationID == migration && e.EventType == evtype {
			n++
		}
	}
	return n
}

type fakeStateWriter struct {
	mu      sync.Mutex
	applied map[string]bool
	failed  map[string]string // key → reason
}

func newFakeState() *fakeStateWriter {
	return &fakeStateWriter{applied: map[string]bool{}, failed: map[string]string{}}
}
func (s *fakeStateWriter) MarkApplied(_ context.Context, r, m string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.applied[key(r, m)] = true
	return nil
}
func (s *fakeStateWriter) MarkFailed(_ context.Context, r, m, reason string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failed[key(r, m)] = reason
	return nil
}

// instantSleeper makes backoff a no-op in tests.
type instantSleeper struct{ count int64 }

func (s *instantSleeper) Sleep(_ context.Context, _ time.Duration) {
	atomic.AddInt64(&s.count, 1)
}

func mkRunner(t *testing.T, cfg *Config) *Runner {
	t.Helper()
	r, err := New(cfg)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return r
}

// TestConcurrencyCapHoldsAt10 — the load-bearing test for L1.D §2 acceptance
// criteria "Concurrency=10 verified (no thread starvation)". Submits 50
// jobs and asserts the peak concurrent Applier.Apply call count was ≤ 10.
func TestConcurrencyCapHoldsAt10(t *testing.T) {
	app := newFakeApplier()
	app.delay = 5 * time.Millisecond // hold the slot long enough to overlap

	r := mkRunner(t, &Config{
		Concurrency: 10,
		MaxAttempts: 1,
		Applier:     app,
		Auditor:     &fakeAuditor{},
		StateWriter: newFakeState(),
		Sleeper:     &instantSleeper{},
	})

	jobs := make([]Job, 50)
	for i := range jobs {
		jobs[i] = Job{
			RealityID:   fmt.Sprintf("reality-%02d", i),
			MigrationID: "0001_initial",
			RunID:       fmt.Sprintf("run-%02d", i),
		}
	}
	results := r.Run(context.Background(), jobs)

	if len(results) != len(jobs) {
		t.Fatalf("results len=%d want=%d", len(results), len(jobs))
	}
	for _, res := range results {
		if !res.Succeeded {
			t.Errorf("job %s failed: %v", res.Job.RealityID, res.FinalError)
		}
	}
	if peak := app.peak.Peak(); peak > 10 {
		t.Errorf("peak concurrency = %d, must be ≤ 10 (L1.D §2 acceptance)", peak)
	}
}

func TestRetryOnTransientThenSucceed(t *testing.T) {
	app := newFakeApplier()
	app.failUntil[key("r-1", "0001_initial")] = 2 // fail twice, succeed on attempt 3

	aud := &fakeAuditor{}
	st := newFakeState()
	r := mkRunner(t, &Config{
		Concurrency: 1,
		MaxAttempts: 3,
		BaseBackoff: time.Microsecond,
		Applier:     app,
		Auditor:     aud,
		StateWriter: st,
		Sleeper:     &instantSleeper{},
	})

	res := r.Run(context.Background(), []Job{{RealityID: "r-1", MigrationID: "0001_initial", RunID: "run-1"}})
	if len(res) != 1 || !res[0].Succeeded {
		t.Fatalf("expected success after retries, got %+v", res)
	}
	if res[0].Attempts != 3 {
		t.Errorf("expected 3 attempts, got %d", res[0].Attempts)
	}
	if aud.eventsFor("r-1", "0001_initial", "migration_started") != 1 {
		t.Error("expected 1 migration_started audit row")
	}
	if aud.eventsFor("r-1", "0001_initial", "migration_succeeded") != 1 {
		t.Error("expected 1 migration_succeeded audit row")
	}
	if !st.applied[key("r-1", "0001_initial")] {
		t.Error("expected MarkApplied on success")
	}
}

func TestRetryExhaustedThenPersistentFailure(t *testing.T) {
	app := newFakeApplier()
	app.always[key("r-1", "0001_initial")] = fmt.Errorf("db unreachable: %w", ErrTransient)

	aud := &fakeAuditor{}
	st := newFakeState()
	r := mkRunner(t, &Config{
		Concurrency: 1,
		MaxAttempts: 3,
		BaseBackoff: time.Microsecond,
		Applier:     app,
		Auditor:     aud,
		StateWriter: st,
		Sleeper:     &instantSleeper{},
	})

	res := r.Run(context.Background(), []Job{{RealityID: "r-1", MigrationID: "0001_initial", RunID: "run-1"}})
	if res[0].Succeeded {
		t.Fatal("expected failure after retries exhausted")
	}
	if res[0].Attempts != 3 {
		t.Errorf("expected 3 attempts, got %d", res[0].Attempts)
	}
	if res[0].FinalReason != "persistent" {
		t.Errorf("expected reason 'persistent', got %q", res[0].FinalReason)
	}
	if aud.eventsFor("r-1", "0001_initial", "migration_failed") != 1 {
		t.Errorf("expected 1 migration_failed audit row")
	}
	if got := st.failed[key("r-1", "0001_initial")]; got != "persistent" {
		t.Errorf("expected MarkFailed reason=persistent, got %q", got)
	}
}

func TestPermanentErrorDoesNotRetry(t *testing.T) {
	app := newFakeApplier()
	app.always[key("r-1", "0001_initial")] = errors.New("syntax error in SQL")

	aud := &fakeAuditor{}
	st := newFakeState()
	r := mkRunner(t, &Config{
		Concurrency: 1,
		MaxAttempts: 3,
		BaseBackoff: time.Microsecond,
		Applier:     app,
		Auditor:     aud,
		StateWriter: st,
		Sleeper:     &instantSleeper{},
	})

	res := r.Run(context.Background(), []Job{{RealityID: "r-1", MigrationID: "0001_initial", RunID: "run-1"}})
	if res[0].Succeeded {
		t.Fatal("expected failure")
	}
	if res[0].Attempts != 1 {
		t.Errorf("expected 1 attempt (permanent error), got %d", res[0].Attempts)
	}
	if res[0].FinalReason != "permanent_error" {
		t.Errorf("expected reason 'permanent_error', got %q", res[0].FinalReason)
	}
}

func TestBackoffIsExponential(t *testing.T) {
	r := &Runner{cfg: &Config{BaseBackoff: 100 * time.Millisecond, MaxBackoff: 30 * time.Second}}
	if got := r.backoff(1); got != 100*time.Millisecond {
		t.Errorf("attempt 1: got %v, want 100ms", got)
	}
	if got := r.backoff(2); got != 200*time.Millisecond {
		t.Errorf("attempt 2: got %v, want 200ms", got)
	}
	if got := r.backoff(3); got != 400*time.Millisecond {
		t.Errorf("attempt 3: got %v, want 400ms", got)
	}
	// Cap kicks in at high attempts.
	if got := r.backoff(20); got != 30*time.Second {
		t.Errorf("attempt 20 should cap at 30s, got %v", got)
	}
}

func TestNoAutoRollbackInV1(t *testing.T) {
	// Q-L1D-1 V1: the runner MUST NOT invoke any rollback API after a
	// persistent failure. We assert this by giving the StateWriter
	// only MarkApplied + MarkFailed (no Rollback method) and checking
	// that the failed run only calls MarkFailed.
	app := newFakeApplier()
	app.always[key("r-1", "0001_initial")] = fmt.Errorf("transient: %w", ErrTransient)

	st := newFakeState()
	r := mkRunner(t, &Config{
		Concurrency: 1,
		MaxAttempts: 2,
		BaseBackoff: time.Microsecond,
		Applier:     app,
		Auditor:     &fakeAuditor{},
		StateWriter: st,
		Sleeper:     &instantSleeper{},
	})
	r.Run(context.Background(), []Job{{RealityID: "r-1", MigrationID: "0001_initial", RunID: "run-1"}})
	// Only MarkFailed should be set. MarkApplied must be empty.
	if len(st.applied) != 0 {
		t.Errorf("expected no MarkApplied calls on persistent failure (Q-L1D-1: V1 doc-only rollback); got %v", st.applied)
	}
	if got := st.failed[key("r-1", "0001_initial")]; got != "persistent" {
		t.Errorf("expected MarkFailed=persistent, got %q", got)
	}
}

func TestConfigValidate_RejectsMissingCollaborators(t *testing.T) {
	if _, err := New(&Config{}); err == nil {
		t.Error("expected error on empty Config")
	}
	if _, err := New(&Config{Applier: newFakeApplier()}); err == nil {
		t.Error("expected error when Auditor missing")
	}
	if _, err := New(&Config{Applier: newFakeApplier(), Auditor: &fakeAuditor{}}); err == nil {
		t.Error("expected error when StateWriter missing")
	}
}

func TestDefaultsAreApplied(t *testing.T) {
	r, err := New(&Config{Applier: newFakeApplier(), Auditor: &fakeAuditor{}, StateWriter: newFakeState()})
	if err != nil {
		t.Fatal(err)
	}
	if r.Concurrency() != DefaultConcurrency {
		t.Errorf("default concurrency = %d, want %d", r.Concurrency(), DefaultConcurrency)
	}
	if r.MaxAttempts() != DefaultMaxAttempts {
		t.Errorf("default max attempts = %d, want %d", r.MaxAttempts(), DefaultMaxAttempts)
	}
}
