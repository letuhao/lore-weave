package jobs

import (
	"context"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

// #286 / plan 2026-09-19 T13 — a model-load abort is retried, and never trips the breaker.

type countingBrk struct{ failures, successes int }

func (b *countingBrk) Allow(ctx context.Context, kind string) (bool, error) { return true, nil }
func (b *countingBrk) Record(ctx context.Context, kind string, success bool) {
	if success {
		b.successes++
	} else {
		b.failures++
	}
}

func contention() error {
	return &provider.ErrUpstreamModelContention{StatusCode: 400, Body: "Failed to load model x. Error: Engine protocol startup was aborted."}
}

func TestContention_IsRetried_ThenSucceeds(t *testing.T) {
	calls := 0
	err := retryTransient(context.Background(), 3, nil, func() error {
		calls++
		if calls < 3 {
			return contention()
		}
		return nil
	})
	if err != nil || calls != 3 {
		t.Fatalf("contention must be retried until the load succeeds: err=%v calls=%d", err, calls)
	}
}

func TestContention_NeverCountsTowardTheBreaker(t *testing.T) {
	brk := &countingBrk{}
	for i := 0; i < 10; i++ { // twice the default threshold
		_ = ratelimit.Guard(context.Background(), nil, brk, "cred", 0, provider.IsTransientUpstreamError,
			func() error { return contention() })
	}
	if brk.failures != 0 {
		t.Fatalf("contention recorded %d breaker failures — it would open the circuit on a busy GPU", brk.failures)
	}
}
