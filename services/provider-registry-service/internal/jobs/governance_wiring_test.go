package jobs

import (
	"context"
	"sync/atomic"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// S3a /review-impl #1: lock the WIRING — every other jobs test runs with nil
// governance (pass-through), so a regression that dropped the ratelimit.Guard
// wrap in processChunks/streamWithRetry would pass silently. These inject a spy
// governor/breaker into a real Worker and assert Guard is actually invoked on
// the provider-call path.

type spyGov struct{ acquired, released int }

func (g *spyGov) Acquire(ctx context.Context, concClass string, limit int) (func(), error) {
	g.acquired++
	return func() { g.released++ }, nil
}

type spyBrk struct {
	kinds   []string
	allowed bool
}

func (b *spyBrk) Allow(ctx context.Context, kind string) (bool, error) {
	b.kinds = append(b.kinds, kind)
	return b.allowed, nil
}
func (b *spyBrk) Record(ctx context.Context, kind string, success bool) {}

func TestStreamWithRetry_InvokesGovernorAndBreaker(t *testing.T) {
	w := newWorkerForRetryTest()
	gov := &spyGov{}
	brk := &spyBrk{allowed: true}
	w.WithGovernance(gov, brk)

	adapter := &fakeAdapter{errSeq: []error{nil}, emitDelta: "x"}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	err := w.streamWithRetry(context.Background(), agg, adapter,
		"ollama", 1, "", "", "", map[string]any{}, emit, w.logger)
	if err != nil {
		t.Fatalf("unexpected err %v", err)
	}
	if gov.acquired != 1 || gov.released != 1 {
		t.Fatalf("governor must be acquired+released once (Guard wired); got %d/%d", gov.acquired, gov.released)
	}
	if len(brk.kinds) != 1 || brk.kinds[0] != "ollama" {
		t.Fatalf("breaker must be checked with the resolved providerKind; got %v", brk.kinds)
	}
}

func TestStreamWithRetry_OpenBreakerFailsFastWithoutCallingProvider(t *testing.T) {
	w := newWorkerForRetryTest()
	w.maxRetries = 3 // even with a retry budget, an open circuit must NOT retry
	gov := &spyGov{}
	brk := &spyBrk{allowed: false} // circuit open
	w.WithGovernance(gov, brk)

	adapter := &fakeAdapter{errSeq: []error{nil}, emitDelta: "x"}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	err := w.streamWithRetry(context.Background(), agg, adapter,
		"openai", 8, "", "", "", map[string]any{}, emit, w.logger)
	if err == nil {
		t.Fatal("open circuit must surface an error")
	}
	if classifyStreamErrorCode(err) != "LLM_CIRCUIT_OPEN" {
		t.Fatalf("open circuit must classify as LLM_CIRCUIT_OPEN; got %s", classifyStreamErrorCode(err))
	}
	if gov.acquired != 0 {
		t.Fatal("must not acquire a governor slot when the circuit is open")
	}
	if c := atomic.LoadInt32(&adapter.calls); c != 0 {
		t.Fatalf("provider must NOT be called when circuit is open; got %d calls", c)
	}
}
