package jobs

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// Phase 4a-α Step 0a — operation whitelist regression locks. The worker
// gates non-whitelisted operations with LLM_OPERATION_NOT_SUPPORTED at
// worker.go:140 (now via isStreamableOperation). Tests guard against:
//   1. accidental drop of an extraction operation from the map
//   2. accidental promotion of a non-whitelisted operation
// Behavioral integration coverage (Process actually reaches the aggregator
// for whitelisted ops) lives in api/jobs_router_test.go + the cycle-20
// aggregator_test.go suite.

func TestIsStreamableOperation_WhitelistedOps(t *testing.T) {
	cases := []string{
		"chat",
		"completion",
		"entity_extraction",
		"relation_extraction",
		"event_extraction",
		"fact_extraction", // Phase 4a-β
	}
	for _, op := range cases {
		if !isStreamableOperation(op) {
			t.Errorf("expected %q to be streamable; whitelist drift", op)
		}
	}
}

func TestIsStreamableOperation_RejectsNonStreamable(t *testing.T) {
	// These ops exist in openapi.JobOperation but don't go through the
	// chat-streaming machinery — they need their own adapters.
	cases := []string{
		"embedding",
		"translation",
		"stt",
		"tts",
		"image_gen",
		"",
		"unknown_operation",
	}
	for _, op := range cases {
		if isStreamableOperation(op) {
			t.Errorf("expected %q to NOT be streamable; whitelist over-promotion", op)
		}
	}
}

func TestStreamableOperations_AlsoInValidJobOperations(t *testing.T) {
	// Phase 4a-β regression-lock: every streamable op MUST also be in
	// the API-layer validJobOperations whitelist. Otherwise jobs_handler
	// rejects the submit with LLM_INVALID_REQUEST before reaching the
	// worker — a silent gap that bit fact_extraction during 4a-β BUILD
	// (worker accepted it, validator didn't).
	//
	// /review-impl MED#3 widening: this test now also asserts the op
	// appears in (a) jobs_handler.go's validJobOperations source, (b)
	// migrate.go's CHECK constraint, (c) openapi.yaml's JobOperation
	// enum. Source-grep approach (not import) because cross-package
	// import would either circularize or require exporting the
	// validator. This pins the 5-place invariant: worker whitelist +
	// API validator + DB CHECK + openapi enum + (Python SDK Literal,
	// covered separately by import-time validation in pydantic).
	rootPath := findRepoRoot(t)
	apiHandlerSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/api/jobs_handler.go")
	migrateSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/migrate/migrate.go")
	openapiSrc := readFile(t, rootPath+"/contracts/api/llm-gateway/v1/openapi.yaml")

	for op := range streamableOperations {
		quoted := `"` + op + `"`
		yamlEntry := "        - " + op
		if !strings.Contains(apiHandlerSrc, quoted) {
			t.Errorf("streamable op %q missing from jobs_handler.go validJobOperations — "+
				"submit would fail with LLM_INVALID_REQUEST", op)
		}
		// migrate.go references ops as quoted SQL strings: 'op_name'.
		sqlQuoted := `'` + op + `'`
		if !strings.Contains(migrateSrc, sqlQuoted) {
			t.Errorf("streamable op %q missing from migrate.go CHECK constraint — "+
				"INSERT would fail with constraint violation (LLM_INTERNAL_ERROR)", op)
		}
		if !strings.Contains(openapiSrc, yamlEntry) {
			t.Errorf("streamable op %q missing from openapi.yaml JobOperation enum — "+
				"contract drift; SDK clients won't accept this op", op)
		}
	}
}

// findRepoRoot walks up from the test binary's working directory to find
// the repo root (the dir containing both `services` and `contracts`).
// Tests run from package dir; repo root is 3 levels up
// (services/provider-registry-service/internal/jobs).
func findRepoRoot(t *testing.T) string {
	t.Helper()
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for d := cwd; d != filepath.Dir(d); d = filepath.Dir(d) {
		if _, err := os.Stat(filepath.Join(d, "services")); err == nil {
			if _, err := os.Stat(filepath.Join(d, "contracts")); err == nil {
				return d
			}
		}
	}
	t.Fatalf("could not find repo root from %s", cwd)
	return ""
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("readFile %s: %v", path, err)
	}
	return string(data)
}

func TestStreamableOperations_MatchesAggregatorFactory(t *testing.T) {
	// Cross-check: every whitelisted op MUST have a matching case in
	// NewAggregator() — otherwise worker reaches Process but builds the
	// default chatAggregator for an extraction op, producing wrong-shape
	// result. This test pins the invariant.
	for op := range streamableOperations {
		agg := NewAggregator(op)
		if agg == nil {
			t.Errorf("NewAggregator(%q) returned nil; aggregator factory drift", op)
		}
	}
}

// Phase 4a-α Step 0b — streamWithRetry transient-error semantics.

func TestClassifyStreamErrorCode_RateLimitedDistinct(t *testing.T) {
	// LLM_RATE_LIMITED is a distinct code from LLM_UPSTREAM_ERROR so
	// callers can apply different backoff policies. Today's chat-service
	// SSE bridge passes the code through to the FE.
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow down"}
	if got := classifyStreamErrorCode(rl); got != "LLM_RATE_LIMITED" {
		t.Errorf("got %q, want LLM_RATE_LIMITED", got)
	}
}

func TestClassifyStreamErrorCode_TransientFolds(t *testing.T) {
	trans := &provider.ErrUpstreamTransient{StatusCode: 502, Body: "bad gateway"}
	if got := classifyStreamErrorCode(trans); got != "LLM_UPSTREAM_ERROR" {
		t.Errorf("transient: got %q, want LLM_UPSTREAM_ERROR", got)
	}
	to := &provider.ErrUpstreamTimeout{Underlying: errors.New("dial timeout")}
	if got := classifyStreamErrorCode(to); got != "LLM_UPSTREAM_ERROR" {
		t.Errorf("timeout: got %q, want LLM_UPSTREAM_ERROR", got)
	}
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"}
	if got := classifyStreamErrorCode(perm); got != "LLM_UPSTREAM_ERROR" {
		t.Errorf("permanent: got %q, want LLM_UPSTREAM_ERROR", got)
	}
	if got := classifyStreamErrorCode(provider.ErrStreamNotSupported); got != "LLM_STREAM_NOT_SUPPORTED" {
		t.Errorf("stream-not-supported: got %q, want LLM_STREAM_NOT_SUPPORTED", got)
	}
}

// fakeAdapter records adapter.Stream invocations and replays a scripted
// sequence of errors (then nil for success). Used to drive streamWithRetry
// without a real upstream HTTP server.
type fakeAdapter struct {
	calls    int32
	errSeq   []error // err[0] returned on first call, err[1] on retry, ...
	provider.Adapter
}

func (f *fakeAdapter) Stream(_ context.Context, _, _, _ string, _ map[string]any, _ provider.EmitFn) error {
	idx := atomic.AddInt32(&f.calls, 1) - 1
	if int(idx) < len(f.errSeq) {
		return f.errSeq[int(idx)]
	}
	return nil
}

func newWorkerForRetryTest() *Worker {
	// Discard logger to keep test output clean.
	return &Worker{logger: slog.New(slog.NewTextHandler(discardWriter{}, nil))}
}

type discardWriter struct{}

func (discardWriter) Write(p []byte) (int, error) { return len(p), nil }

func TestStreamWithRetry_TransientThenSuccess(t *testing.T) {
	w := newWorkerForRetryTest()
	adapter := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamTransient{StatusCode: 502, Body: "first attempt fails"},
			// nil on second attempt = success
		},
	}
	err := w.streamWithRetry(context.Background(), adapter, "", "", "", nil, nil, w.logger)
	if err != nil {
		t.Fatalf("expected success after retry, got %v", err)
	}
	if got := atomic.LoadInt32(&adapter.calls); got != 2 {
		t.Errorf("expected 2 adapter calls (initial + 1 retry), got %d", got)
	}
}

func TestStreamWithRetry_NonTransientFailsImmediately(t *testing.T) {
	w := newWorkerForRetryTest()
	adapter := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"},
		},
	}
	err := w.streamWithRetry(context.Background(), adapter, "", "", "", nil, nil, w.logger)
	if err == nil {
		t.Fatal("expected error to propagate, got nil")
	}
	if got := atomic.LoadInt32(&adapter.calls); got != 1 {
		t.Errorf("expected 1 adapter call (no retry on permanent), got %d", got)
	}
}

func TestStreamWithRetry_TransientBudgetExhausted(t *testing.T) {
	w := newWorkerForRetryTest()
	adapter := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamTransient{StatusCode: 502, Body: "first"},
			&provider.ErrUpstreamTransient{StatusCode: 503, Body: "retry also fails"},
		},
	}
	err := w.streamWithRetry(context.Background(), adapter, "", "", "", nil, nil, w.logger)
	if err == nil {
		t.Fatal("expected error after budget exhausted, got nil")
	}
	if got := atomic.LoadInt32(&adapter.calls); got != 2 {
		t.Errorf("expected 2 adapter calls (initial + 1 retry), got %d", got)
	}
}

func TestStreamWithRetry_RateLimitedHonorsRetryAfter(t *testing.T) {
	// Smoke test that retry-after path is exercised. We don't time the
	// sleep itself (would slow tests); instead set a tiny retry_after_s
	// and assert the second call still happens.
	w := newWorkerForRetryTest()
	tinyWait := 0.01
	adapter := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow down", RetryAfterS: &tinyWait},
		},
	}
	err := w.streamWithRetry(context.Background(), adapter, "", "", "", nil, nil, w.logger)
	if err != nil {
		t.Fatalf("expected success after rate-limit retry, got %v", err)
	}
	if got := atomic.LoadInt32(&adapter.calls); got != 2 {
		t.Errorf("expected 2 adapter calls, got %d", got)
	}
}

func TestStreamWithRetry_ContextCancelledDuringBackoff(t *testing.T) {
	// A cancel mid-backoff (from caller-side DELETE /v1/llm/jobs/{id})
	// must propagate ctx.Err() instead of swallowing it as a successful
	// retry. Cancel-race correctness invariant (ADR §5.5).
	w := newWorkerForRetryTest()
	adapter := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamTransient{StatusCode: 502, Body: "first"},
		},
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-cancel — backoff sleep returns immediately via ctx.Done
	err := w.streamWithRetry(ctx, adapter, "", "", "", nil, nil, w.logger)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context.Canceled, got %v", err)
	}
}

// /review-impl MED#5 — job-level shared budget across chunks.

func TestStreamWithBudget_SharedBudgetExhaustsAcrossChunks(t *testing.T) {
	// Simulates 3 chunks each hitting transient on first attempt. With
	// shared budget=1, ONLY the first chunk gets to retry; chunks 2+3
	// must fail immediately on transient because budget is depleted.
	// This pins the "9 chunks × 2 attempts ≠ N×2 amplification" fix.
	w := newWorkerForRetryTest()
	budget := 1

	// Chunk 0: transient → retry (budget consumed) → success
	adapter0 := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamTransient{StatusCode: 502, Body: "chunk0 first"},
		},
	}
	if err := w.streamWithBudget(context.Background(), adapter0, "", "", "", nil, nil, &budget, w.logger); err != nil {
		t.Fatalf("chunk0 expected success after retry, got %v", err)
	}
	if budget != 0 {
		t.Fatalf("expected budget=0 after chunk0 retry, got %d", budget)
	}

	// Chunk 1: transient → NO retry (budget exhausted) → propagate failure
	adapter1 := &fakeAdapter{
		errSeq: []error{
			&provider.ErrUpstreamTransient{StatusCode: 502, Body: "chunk1 first"},
		},
	}
	err := w.streamWithBudget(context.Background(), adapter1, "", "", "", nil, nil, &budget, w.logger)
	if err == nil {
		t.Fatal("chunk1 expected failure (budget exhausted), got nil")
	}
	if got := atomic.LoadInt32(&adapter1.calls); got != 1 {
		t.Errorf("chunk1 expected 1 adapter call (no retry), got %d", got)
	}
}

func TestStreamWithBudget_SuccessfulChunksDoNotConsumeBudget(t *testing.T) {
	// Successful chunks must NOT consume budget — only transient errors do.
	// Otherwise a job with all-successful chunks would still deplete budget.
	w := newWorkerForRetryTest()
	budget := 1
	adapter := &fakeAdapter{errSeq: []error{}} // all success

	for i := 0; i < 5; i++ {
		if err := w.streamWithBudget(context.Background(), adapter, "", "", "", nil, nil, &budget, w.logger); err != nil {
			t.Fatalf("call %d unexpected error: %v", i, err)
		}
	}
	if budget != 1 {
		t.Errorf("expected budget=1 (untouched after all-success), got %d", budget)
	}
}
