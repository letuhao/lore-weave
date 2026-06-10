package jobs

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// stubRetrySleep swaps retrySleep for an instant version that still honors
// ctx cancellation, so retry tests run fast without losing the cancel path.
func stubRetrySleep(t *testing.T) {
	t.Helper()
	orig := retrySleep
	retrySleep = func(ctx context.Context, _ time.Duration) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return nil
	}
	t.Cleanup(func() { retrySleep = orig })
}

// ── retryBackoff ────────────────────────────────────────────────────────────

func TestRetryBackoff_Exponential(t *testing.T) {
	cases := []struct {
		attempt int
		want    time.Duration
	}{
		{0, 1 * time.Second},
		{1, 2 * time.Second},
		{2, 4 * time.Second},
		{3, 8 * time.Second},
		{20, 30 * time.Second}, // far past the cap
	}
	for _, c := range cases {
		if got := retryBackoff(c.attempt, errors.New("x")); got != c.want {
			t.Fatalf("retryBackoff(%d): got %v want %v", c.attempt, got, c.want)
		}
	}
}

func TestRetryBackoff_RetryAfterOverrides(t *testing.T) {
	ra := 5.0
	err := &provider.ErrUpstreamRateLimited{StatusCode: 429, RetryAfterS: &ra}
	// Even at attempt 0 (exponential would be 1s), the server Retry-After wins.
	if got := retryBackoff(0, err); got != 5*time.Second {
		t.Fatalf("Retry-After should override the exponential backoff: got %v want 5s", got)
	}
}

func TestRetryBackoff_RetryAfterClampedToCap(t *testing.T) {
	// A misbehaving upstream sending an enormous Retry-After must not park
	// the worker goroutine for hours — the streamable path has no per-job
	// timeout. retryBackoff clamps the hint to retryCapS (/review-impl 6b #1).
	ra := 86400.0 // upstream asks to retry in 24h
	err := &provider.ErrUpstreamRateLimited{StatusCode: 429, RetryAfterS: &ra}
	if got := retryBackoff(0, err); got != 30*time.Second {
		t.Fatalf("a huge Retry-After must clamp to the 30s cap: got %v", got)
	}
}

// ── retryTransient ──────────────────────────────────────────────────────────

func TestRetryTransient_SuccessFirstTry(t *testing.T) {
	stubRetrySleep(t)
	var calls int
	err := retryTransient(context.Background(), 3, nil, func() error {
		calls++
		return nil
	})
	if err != nil || calls != 1 {
		t.Fatalf("success first try: err=%v calls=%d (want nil/1)", err, calls)
	}
}

func TestRetryTransient_TransientThenSuccess(t *testing.T) {
	stubRetrySleep(t)
	var calls int
	err := retryTransient(context.Background(), 3, nil, func() error {
		calls++
		if calls == 1 {
			return &provider.ErrUpstreamTransient{StatusCode: 502}
		}
		return nil
	})
	if err != nil || calls != 2 {
		t.Fatalf("transient-then-success: err=%v calls=%d (want nil/2)", err, calls)
	}
}

func TestRetryTransient_NonTransientImmediate(t *testing.T) {
	stubRetrySleep(t)
	var calls int
	want := &provider.ErrUpstreamPermanent{StatusCode: 400}
	err := retryTransient(context.Background(), 3, nil, func() error {
		calls++
		return want
	})
	if calls != 1 {
		t.Fatalf("a non-transient error must not retry: calls=%d", calls)
	}
	if !errors.Is(err, want) {
		t.Fatalf("expected the non-transient error to propagate, got %v", err)
	}
}

func TestRetryTransient_BudgetExhausted(t *testing.T) {
	stubRetrySleep(t)
	var calls int
	err := retryTransient(context.Background(), 2, nil, func() error {
		calls++
		return &provider.ErrUpstreamTransient{StatusCode: 503}
	})
	// maxRetries=2 → 1 initial + 2 retries = 3 attempts.
	if calls != 3 {
		t.Fatalf("budget exhausted: expected 3 attempts, got %d", calls)
	}
	if err == nil {
		t.Fatal("budget exhausted must return the last error")
	}
}

func TestRetryTransient_CtxCancelledDuringBackoff(t *testing.T) {
	// A cancel mid-backoff (caller DELETE'd the job) must surface ctx.Err(),
	// not be swallowed as a retry.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var calls int
	err := retryTransient(ctx, 3, nil, func() error {
		calls++
		return &provider.ErrUpstreamTransient{StatusCode: 502}
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context.Canceled, got %v", err)
	}
	if calls != 1 {
		t.Fatalf("a cancelled backoff must stop after the first attempt, got %d", calls)
	}
}

// ── per-chunk independent budget (Phase 6b) ─────────────────────────────────

func TestProcessChunks_PerChunkIndependentBudget(t *testing.T) {
	stubRetrySleep(t)
	w := newWorkerForRetryTest()
	w.maxRetries = 1

	// chunk 0 fails once then succeeds (calls 1,2); chunk 1 fails once then
	// succeeds (calls 3,4). Under the OLD shared budget=1, chunk 0's retry
	// would exhaust the budget and chunk 1's failure would be fatal.
	adapter := &fakeAdapter{errSeq: []error{
		&provider.ErrUpstreamTransient{StatusCode: 502},
		nil,
		&provider.ErrUpstreamTransient{StatusCode: 502},
		nil,
	}}
	agg := NewAggregator("chat")
	inputMap := map[string]any{
		"messages": []any{map[string]any{"role": "user", "content": "x"}},
	}
	emit := func(provider.StreamChunk) error { return nil }

	err := w.processChunks(context.Background(), uuid.New(), agg, adapter,
		"openai", "", "", "", inputMap, []string{"a", "b"}, emit, w.logger)
	if err != nil {
		t.Fatalf("per-chunk budget should let both chunks retry + succeed, got %v", err)
	}
	if got := atomic.LoadInt32(&adapter.calls); got != 4 {
		t.Fatalf("expected 4 stream calls (2 chunks × (fail + retry)), got %d", got)
	}
}

// chatContent pulls the assistant message content out of a chat
// aggregator's finalized result — a small helper for the reset tests.
func chatContent(t *testing.T, agg Aggregator) string {
	t.Helper()
	result, _, _ := agg.Finalize()
	msgs, ok := result["messages"].([]any)
	if !ok || len(msgs) == 0 {
		t.Fatalf("result has no messages: %#v", result)
	}
	content, _ := msgs[0].(map[string]any)["content"].(string)
	return content
}

// ── retry discards a failed attempt's partial stream (Phase 6b #2/#3) ───────

func TestStreamWithRetry_RetryDiscardsPartialStream(t *testing.T) {
	// The unchunked path: a transient failure mid-stream then a successful
	// retry must NOT double-accumulate the re-emitted tokens. streamWithRetry
	// brackets the call with StartChunk(0)/EndChunk(0) so the failed
	// attempt's emitted "hello" is discarded (/review-impl 6b #2).
	stubRetrySleep(t)
	w := newWorkerForRetryTest()
	w.maxRetries = 1

	adapter := &fakeAdapter{
		errSeq:    []error{&provider.ErrUpstreamTransient{StatusCode: 502}, nil},
		emitDelta: "hello",
	}
	agg := NewAggregator("chat")
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	err := w.streamWithRetry(context.Background(), agg, adapter,
		"openai", "", "", "", map[string]any{}, emit, w.logger)
	if err != nil {
		t.Fatalf("transient-then-success must succeed, got %v", err)
	}
	if got := chatContent(t, agg); got != "hello" {
		t.Fatalf("retry must discard the failed attempt's partial stream: got %q want %q", got, "hello")
	}
}

func TestProcessChunks_RetryDiscardsPartialChunk(t *testing.T) {
	// The chunked path: agg.StartChunk(i) lives inside the retry op, so a
	// chunk's failed attempt (which emitted "tok") is reset before the
	// successful retry re-emits it. Guards the in-closure StartChunk
	// placement against drift (/review-impl 6b #3).
	stubRetrySleep(t)
	w := newWorkerForRetryTest()
	w.maxRetries = 1

	adapter := &fakeAdapter{
		errSeq:    []error{&provider.ErrUpstreamTransient{StatusCode: 502}, nil},
		emitDelta: "tok",
	}
	agg := NewAggregator("chat")
	inputMap := map[string]any{
		"messages": []any{map[string]any{"role": "user", "content": "x"}},
	}
	emit := func(c provider.StreamChunk) error { agg.Accept(c); return nil }

	err := w.processChunks(context.Background(), uuid.New(), agg, adapter,
		"openai", "", "", "", inputMap, []string{"a"}, emit, w.logger)
	if err != nil {
		t.Fatalf("chunk retry should succeed, got %v", err)
	}
	if got := chatContent(t, agg); got != "tok" {
		t.Fatalf("chunk retry must discard the failed attempt's partial: got %q want %q", got, "tok")
	}
}
