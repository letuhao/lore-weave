package chaos

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestNoopHook(t *testing.T) {
	h := &NoopHook{HookID: "test.noop"}
	if h.ID() != "test.noop" {
		t.Fatal("id")
	}
	if err := h.Apply(context.Background()); err != nil {
		t.Fatalf("noop.Apply should be nil, got %v", err)
	}
	if !h.IsExhausted() {
		t.Fatal("noop is permanently exhausted")
	}
}

func TestFailOnce_TripsOnce(t *testing.T) {
	h := &FailOnce{HookID: "test.fail", Reason: "drill"}
	if h.IsExhausted() {
		t.Fatal("FailOnce starts un-tripped")
	}
	err := h.Apply(context.Background())
	if err == nil || !errors.Is(err, ErrChaosInjected) {
		t.Fatalf("first call must return ErrChaosInjected, got %v", err)
	}
	if !h.IsExhausted() {
		t.Fatal("FailOnce must mark exhausted after first trip")
	}
	for i := 0; i < 5; i++ {
		if err := h.Apply(context.Background()); err != nil {
			t.Fatalf("post-trip call %d must be nil, got %v", i, err)
		}
	}
}

func TestFailOnce_ConcurrentTrip(t *testing.T) {
	// Many goroutines hammer Apply; exactly ONE sees ErrChaosInjected,
	// all others see nil. CompareAndSwap invariant.
	h := &FailOnce{HookID: "test.fail.concurrent", Reason: "race"}
	var (
		wg       sync.WaitGroup
		injected counterT
	)
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := h.Apply(context.Background()); err != nil {
				injected.add(1)
			}
		}()
	}
	wg.Wait()
	if got := injected.get(); got != 1 {
		t.Fatalf("FailOnce concurrent invariant violated: %d injections (want 1)", got)
	}
}

// counterT — tiny test-local int counter (avoid clashing with
// sync/atomic package name).
type counterT struct {
	mu sync.Mutex
	n  int
}

func (a *counterT) add(d int) { a.mu.Lock(); a.n += d; a.mu.Unlock() }
func (a *counterT) get() int  { a.mu.Lock(); defer a.mu.Unlock(); return a.n }

func TestDelayOnce_BasicDelay(t *testing.T) {
	h := &DelayOnce{HookID: "test.delay", Delay: 20 * time.Millisecond}
	start := time.Now()
	if err := h.Apply(context.Background()); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	elapsed := time.Since(start)
	if elapsed < 18*time.Millisecond {
		t.Fatalf("DelayOnce delayed only %v (want ≥ 20ms)", elapsed)
	}
	// Subsequent call must NOT delay (short-circuit).
	start = time.Now()
	if err := h.Apply(context.Background()); err != nil {
		t.Fatalf("second Apply: %v", err)
	}
	if d := time.Since(start); d > 5*time.Millisecond {
		t.Fatalf("second Apply must short-circuit; took %v", d)
	}
}

func TestDelayOnce_HonorsCancellation(t *testing.T) {
	h := &DelayOnce{HookID: "test.delay.cancel", Delay: 5 * time.Second}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	start := time.Now()
	err := h.Apply(ctx)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected DeadlineExceeded, got %v", err)
	}
	if d := time.Since(start); d > 200*time.Millisecond {
		t.Fatalf("Apply ignored cancellation; took %v", d)
	}
}

func TestDelayOnce_ZeroDelayNoOp(t *testing.T) {
	h := &DelayOnce{HookID: "test.delay.zero", Delay: 0}
	start := time.Now()
	if err := h.Apply(context.Background()); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	if d := time.Since(start); d > 2*time.Millisecond {
		t.Fatalf("zero delay must be ~instant; took %v", d)
	}
}

// ─────────────────────────────────────────────────────────────────────
// HookRegistry
// ─────────────────────────────────────────────────────────────────────

func TestHookRegistry_DefaultIsEmpty(t *testing.T) {
	// CRITICAL invariant: a fresh service has NO chaos hooks bound,
	// so the hot-path Apply returns nil and zero hooks fire.
	r := NewHookRegistry()
	if r.Len() != 0 {
		t.Fatalf("fresh registry must be empty, got %d", r.Len())
	}
	if err := r.Apply(context.Background(), "any.path"); err != nil {
		t.Fatalf("Apply with no hook bound must be nil, got %v", err)
	}
}

func TestHookRegistry_RegisterGetDeregister(t *testing.T) {
	r := NewHookRegistry()
	h := &FailOnce{HookID: "x.y.z", Reason: "test"}
	if prev := r.Register(h); prev != nil {
		t.Fatal("Register on empty must return nil prev")
	}
	if r.Len() != 1 {
		t.Fatalf("Len after register: %d", r.Len())
	}
	got := r.Get("x.y.z")
	if got != h {
		t.Fatal("Get must return registered hook")
	}
	if missing := r.Get("not.bound"); missing != nil {
		t.Fatal("Get for unknown must be nil")
	}
	removed := r.Deregister("x.y.z")
	if removed != h {
		t.Fatal("Deregister must return removed hook")
	}
	if r.Len() != 0 {
		t.Fatal("Len after deregister must be 0")
	}
}

func TestHookRegistry_Register_Replace(t *testing.T) {
	r := NewHookRegistry()
	a := &NoopHook{HookID: "x"}
	b := &NoopHook{HookID: "x"}
	r.Register(a)
	if prev := r.Register(b); prev != a {
		t.Fatal("Register on existing must return previous")
	}
	if r.Get("x") != b {
		t.Fatal("Get must return latest hook")
	}
}

func TestHookRegistry_Register_NilSafe(t *testing.T) {
	r := NewHookRegistry()
	if prev := r.Register(nil); prev != nil {
		t.Fatal("Register(nil) must be no-op")
	}
	if r.Len() != 0 {
		t.Fatal("Register(nil) must not change Len")
	}
}

func TestHookRegistry_Apply_RoutesToHook(t *testing.T) {
	r := NewHookRegistry()
	r.Register(&FailOnce{HookID: "the.hook", Reason: "boom"})
	err := r.Apply(context.Background(), "the.hook")
	if !errors.Is(err, ErrChaosInjected) {
		t.Fatalf("expected ErrChaosInjected, got %v", err)
	}
	// Hook tripped — second call returns nil.
	if err := r.Apply(context.Background(), "the.hook"); err != nil {
		t.Fatalf("after-trip Apply must be nil, got %v", err)
	}
}

// ─────────────────────────────────────────────────────────────────────
// DrillAuditEntry + example drill
// ─────────────────────────────────────────────────────────────────────

func TestDrillAuditEntry_Validate_Happy(t *testing.T) {
	a := DrillAuditEntry{
		DrillID:          uuid.New(),
		DrillName:        "meta_outage",
		TargetService:    "meta-postgres",
		Environment:      DrillEnvironmentStaging,
		Outcome:          DrillOutcomeSuccess,
		StartedAtNanos:   1700000000000000000,
		CompletedAtNanos: 1700000001000000000,
		OperatorActorID:  "sre@loreweave.dev",
	}
	if err := a.Validate(); err != nil {
		t.Fatalf("happy: %v", err)
	}
}

func TestDrillAuditEntry_Validate_Rejects(t *testing.T) {
	base := DrillAuditEntry{
		DrillID:          uuid.New(),
		DrillName:        "x",
		TargetService:    "y",
		Environment:      DrillEnvironmentDev,
		Outcome:          DrillOutcomeSuccess,
		StartedAtNanos:   1700000000000000000,
		CompletedAtNanos: 1700000001000000000,
		OperatorActorID:  "op",
	}
	cases := map[string]func(*DrillAuditEntry){
		"zero drill_id":         func(d *DrillAuditEntry) { d.DrillID = uuid.Nil },
		"empty drill_name":      func(d *DrillAuditEntry) { d.DrillName = "" },
		"empty target_service":  func(d *DrillAuditEntry) { d.TargetService = "" },
		"invalid environment":   func(d *DrillAuditEntry) { d.Environment = "bogus" },
		"invalid outcome":       func(d *DrillAuditEntry) { d.Outcome = "bogus" },
		"implausible started":   func(d *DrillAuditEntry) { d.StartedAtNanos = 1577836800000000000 },
		"completed < started":   func(d *DrillAuditEntry) { d.CompletedAtNanos = d.StartedAtNanos - 1 },
		"empty operator":        func(d *DrillAuditEntry) { d.OperatorActorID = "" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			d := base
			mutate(&d)
			if err := d.Validate(); err == nil {
				t.Fatalf("%s: Validate must reject", name)
			}
		})
	}
}

func TestExampleDrillMetaOutageProbe(t *testing.T) {
	d := ExampleDrillMetaOutageProbe{
		TargetService: "meta-postgres",
		Environment:   DrillEnvironmentStaging,
	}
	hooks := d.HooksFired()
	if len(hooks) != 2 {
		t.Fatalf("HooksFired len: %d", len(hooks))
	}
	tpl := d.AuditTemplate()
	if tpl.DrillName != "meta_outage" {
		t.Fatalf("DrillName: %q", tpl.DrillName)
	}
	if tpl.TargetService != "meta-postgres" {
		t.Fatalf("TargetService: %q", tpl.TargetService)
	}
	if tpl.Environment != DrillEnvironmentStaging {
		t.Fatalf("Environment: %q", tpl.Environment)
	}
	if len(tpl.HookIDsTriggered) != 2 {
		t.Fatalf("HookIDsTriggered len: %d", len(tpl.HookIDsTriggered))
	}
	// Template intentionally leaves DrillID + timestamps zero — the
	// caller (chaos-engine V1+30d) sets them at drill kickoff.
	if tpl.DrillID != uuid.Nil {
		t.Fatal("template DrillID must be zero")
	}
	if tpl.StartedAtNanos != 0 {
		t.Fatal("template StartedAtNanos must be zero")
	}
}

func TestDrillOutcomeIsValid(t *testing.T) {
	for _, o := range []DrillOutcome{
		DrillOutcomeSuccess, DrillOutcomeFailure, DrillOutcomeAborted, DrillOutcomePreconditionFail,
	} {
		if !o.IsValid() {
			t.Errorf("%q must be valid", o)
		}
	}
	if DrillOutcome("nope").IsValid() {
		t.Fatal("nope is not valid")
	}
}

func TestDrillEnvironmentIsValid(t *testing.T) {
	for _, e := range []DrillEnvironment{
		DrillEnvironmentDev, DrillEnvironmentStaging, DrillEnvironmentProd,
	} {
		if !e.IsValid() {
			t.Errorf("%q must be valid", e)
		}
	}
	if DrillEnvironment("qa").IsValid() {
		t.Fatal("qa is not valid")
	}
}
