package jobs

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

// #286 / plan 2026-09-19 T12 — the model lease is on the provider-call path ONLY for a job whose
// credential opted in, it is held around the call itself, and without the opt-in nothing changes.

type spyLease struct {
	calls    []string // "endpoint|model" per Acquire
	held     int32    // >0 while a lease is held
	released int32
	err      error
}

func (l *spyLease) Acquire(ctx context.Context, endpoint, model string) (func(), error) {
	l.calls = append(l.calls, endpoint+"|"+model)
	if l.err != nil {
		return func() {}, l.err
	}
	atomic.AddInt32(&l.held, 1)
	return func() { atomic.AddInt32(&l.held, -1); atomic.AddInt32(&l.released, 1) }, nil
}

// heldDuringCall fails the provider call if the lease is not held at that moment.
type heldDuringCall struct {
	fakeAdapter
	lease *spyLease
}

func (a *heldDuringCall) Stream(ctx context.Context, baseURL, secret, model string, input map[string]any, emit provider.EmitFn) error {
	if atomic.LoadInt32(&a.lease.held) != 1 {
		return fmt.Errorf("provider called without the model lease held")
	}
	return a.fakeAdapter.Stream(ctx, baseURL, secret, model, input, emit)
}

func TestModelLease_HeldAroundTheCall_WhenTheCredentialOptedIn(t *testing.T) {
	w := newWorkerForRetryTest()
	lease := &spyLease{}
	w.WithModelLease(lease)
	adapter := &heldDuringCall{fakeAdapter: fakeAdapter{errSeq: []error{nil}, emitDelta: "x"}, lease: lease}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	ctx := withModelLeaseReq(context.Background(), "http://host.docker.internal:1234", "gemma-12b")
	if err := w.streamWithRetry(ctx, agg, adapter, "cred", 0, "http://host.docker.internal:1234", "", "gemma-12b",
		map[string]any{}, emit, w.logger); err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	if len(lease.calls) != 1 || lease.calls[0] != "http://host.docker.internal:1234|gemma-12b" {
		t.Fatalf("lease must be taken once for (endpoint, model); got %v", lease.calls)
	}
	if lease.released != 1 || atomic.LoadInt32(&lease.held) != 0 {
		t.Fatalf("lease must be released after the call; released=%d held=%d", lease.released, lease.held)
	}
}

func TestModelLease_NotTaken_WithoutTheOptIn(t *testing.T) {
	w := newWorkerForRetryTest()
	lease := &spyLease{}
	w.WithModelLease(lease)
	adapter := &fakeAdapter{errSeq: []error{nil}, emitDelta: "x"}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	if err := w.streamWithRetry(context.Background(), agg, adapter, "cred", 0, "http://x:1234", "", "m",
		map[string]any{}, emit, w.logger); err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	if len(lease.calls) != 0 {
		t.Fatalf("a credential that did not opt in must never wait on the lease; got %v", lease.calls)
	}
}

func TestModelLease_ChunkedJobsTakeItPerChunk(t *testing.T) {
	w := newWorkerForRetryTest()
	lease := &spyLease{}
	w.WithModelLease(lease)
	adapter := &heldDuringCall{fakeAdapter: fakeAdapter{errSeq: []error{nil, nil, nil}, emitDelta: "x"}, lease: lease}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }
	ctx := withModelLeaseReq(context.Background(), "http://e:1", "m")
	input := map[string]any{"messages": []any{map[string]any{"role": "user", "content": "x"}}}
	if err := w.processChunks(ctx, [16]byte{}, agg, adapter, "cred", 0, "http://e:1", "", "m", input,
		[]string{"a", "b", "c"}, emit, w.logger); err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	if len(lease.calls) != 3 || lease.released != 3 {
		t.Fatalf("each chunk's call must hold the lease; calls=%d released=%d", len(lease.calls), lease.released)
	}
}

func TestModelLease_TimeoutIsItsOwnErrorCode(t *testing.T) {
	w := newWorkerForRetryTest()
	w.maxRetries = 2
	lease := &spyLease{err: ratelimit.ErrModelLeaseTimeout}
	w.WithModelLease(lease)
	adapter := &fakeAdapter{errSeq: []error{nil}, emitDelta: "x"}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }
	ctx := withModelLeaseReq(context.Background(), "http://e:1", "m")

	err := w.streamWithRetry(ctx, agg, adapter, "cred", 0, "http://e:1", "", "m", map[string]any{}, emit, w.logger)
	if got := classifyStreamErrorCode(err); got != "LLM_MODEL_BUSY" {
		t.Fatalf("a lease timeout must surface as LLM_MODEL_BUSY, got %s (%v)", got, err)
	}
	if c := atomic.LoadInt32(&adapter.calls); c != 0 {
		t.Fatal("the provider must not be called when the lease was never granted")
	}
}
