package lifecycle

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestDrain_RejectsNonPositiveTimeout(t *testing.T) {
	for _, bad := range []time.Duration{0, -1, -time.Second} {
		_, err := Drain(context.Background(), bad, DrainHooks{})
		if !errors.Is(err, ErrDrainTimeoutInvalid) {
			t.Errorf("timeout=%v err = %v, want ErrDrainTimeoutInvalid", bad, err)
		}
	}
}

func TestDrain_NilParentTreatedAsBackground(t *testing.T) {
	// nolint - intentional nil to exercise the defensive ctx fallback
	res, err := Drain(nil, time.Second, DrainHooks{})
	if err != nil {
		t.Errorf("nil parent err = %v, want nil (treated as background)", err)
	}
	if res.Elapsed < 0 {
		t.Errorf("elapsed should be non-negative; got %v", res.Elapsed)
	}
}

// TestDrain_HookExecutionOrder is the load-bearing test: the SR06 §12AI.11
// shutdown order is a CORRECTNESS invariant — if FlushOutbox runs after
// CloseResources, the DB pool is gone and outbox flush hits a panic.
func TestDrain_HookExecutionOrder(t *testing.T) {
	var (
		mu    sync.Mutex
		order []string
	)
	record := func(name string) {
		mu.Lock()
		order = append(order, name)
		mu.Unlock()
	}
	hooks := DrainHooks{
		StopAccepting:  func() { record("stop_accepting") },
		WaitInFlight:   func(ctx context.Context) error { record("wait_inflight"); return nil },
		FlushOutbox:    func(ctx context.Context) error { record("flush_outbox"); return nil },
		CloseBreakers:  func() error { record("close_breakers"); return nil },
		CloseResources: func() error { record("close_resources"); return nil },
	}
	res, err := Drain(context.Background(), time.Second, hooks)
	if err != nil {
		t.Fatalf("Drain err = %v", err)
	}
	if !res.IsSuccess() {
		t.Errorf("expected success result; got %+v", res)
	}
	want := []string{"stop_accepting", "wait_inflight", "flush_outbox", "close_breakers", "close_resources"}
	if len(order) != len(want) {
		t.Fatalf("order = %v, want %v", order, want)
	}
	for i := range want {
		if order[i] != want[i] {
			t.Errorf("step %d: got %q, want %q (full order: %v)", i, order[i], want[i], order)
		}
	}
}

func TestDrain_NilHooksSkipped(t *testing.T) {
	// Stateless service supplies only StopAccepting + CloseResources.
	called := map[string]bool{}
	hooks := DrainHooks{
		StopAccepting:  func() { called["stop"] = true },
		CloseResources: func() error { called["close"] = true; return nil },
	}
	res, err := Drain(context.Background(), time.Second, hooks)
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if !called["stop"] || !called["close"] {
		t.Errorf("expected stop + close called; got %v", called)
	}
	if res.WaitedInFlight || res.FlushedOutbox || res.ClosedBreakers {
		t.Errorf("nil hooks should not register as ran; got %+v", res)
	}
}

func TestDrain_DeadlineExceeded_StillRunsCloseResources(t *testing.T) {
	// WaitInFlight hangs past the deadline. CloseResources MUST still run
	// (resource leaks are worse than a noisy drain log).
	closed := false
	hooks := DrainHooks{
		WaitInFlight: func(ctx context.Context) error {
			<-ctx.Done()
			return ctx.Err()
		},
		CloseResources: func() error { closed = true; return nil },
	}
	res, err := Drain(context.Background(), 10*time.Millisecond, hooks)
	if err == nil {
		t.Fatalf("expected non-nil err; got nil")
	}
	if !res.DeadlineExceeded {
		t.Errorf("DeadlineExceeded should be true; got %+v", res)
	}
	if !closed {
		t.Errorf("CloseResources MUST run even on deadline-exceeded")
	}
}

func TestDrain_StepErrorsPropagateToResult(t *testing.T) {
	hooks := DrainHooks{
		WaitInFlight:   func(ctx context.Context) error { return fmt.Errorf("inflight err") },
		FlushOutbox:    func(ctx context.Context) error { return fmt.Errorf("flush err") },
		CloseBreakers:  func() error { return fmt.Errorf("breakers err") },
		CloseResources: func() error { return fmt.Errorf("resources err") },
	}
	res, err := Drain(context.Background(), time.Second, hooks)
	if err == nil {
		t.Fatal("expected non-nil err")
	}
	if res.WaitInFlightErr == nil || res.FlushOutboxErr == nil ||
		res.CloseBreakersErr == nil || res.CloseResourcesErr == nil {
		t.Errorf("expected all per-step errors recorded; got %+v", res)
	}
	if res.IsSuccess() {
		t.Errorf("IsSuccess should be false when any step errored")
	}
}

func TestDrainTimeoutDefaults(t *testing.T) {
	if DrainTimeoutDefault != 30*time.Second {
		t.Errorf("DrainTimeoutDefault = %v, want 30s per SR06 §12AI.11", DrainTimeoutDefault)
	}
	if DrainTimeoutStateless != 10*time.Second {
		t.Errorf("DrainTimeoutStateless = %v, want 10s", DrainTimeoutStateless)
	}
	if DrainTimeoutLongRunner != 120*time.Second {
		t.Errorf("DrainTimeoutLongRunner = %v, want 120s", DrainTimeoutLongRunner)
	}
}
