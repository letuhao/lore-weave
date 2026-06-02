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
		"translation",     // chat-shaped; wired 2026-05-31 after TR-4 caught it gated
	}
	for _, op := range cases {
		if !isStreamableOperation(op) {
			t.Errorf("expected %q to be streamable; whitelist drift", op)
		}
	}
}

func TestIsStreamableOperation_RejectsNonStreamable(t *testing.T) {
	// These ops exist in openapi.JobOperation but route OUTSIDE the
	// chat-streaming machinery. After Phase 5a + 5c-α + 5d, the
	// dedicated dispatch maps are:
	//   - stt, tts → audioJobOperations (adapter.Transcribe/Speak)
	//   - image_gen → imageJobOperations (adapter.GenerateImage)
	//   - video_gen → videoJobOperations (adapter.GenerateVideo)
	//   - embedding → not yet wired (LLM_OPERATION_NOT_SUPPORTED at the worker
	//     until its dedicated adapter lands; different upstream HTTP shape)
	// Either way, isStreamableOperation MUST return false for all of these
	// so they don't accidentally route through the chat aggregator.
	// (translation is NOT here — it is chat-shaped and now streamable; see
	// TestIsStreamableOperation_WhitelistedOps.)
	cases := []string{
		"embedding",
		"stt",
		"tts",
		"image_gen",
		"video_gen",
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
//
// emitDelta, when non-empty, makes every Stream call emit one token chunk
// with that delta BEFORE returning its scripted error — so a retry-after-
// partial-emit scenario can be exercised (the per-chunk reset discipline
// must discard a failed attempt's emitted tokens).
type fakeAdapter struct {
	calls     int32
	errSeq    []error // err[0] returned on first call, err[1] on retry, ...
	emitDelta string
	provider.Adapter
}

func (f *fakeAdapter) Stream(_ context.Context, _, _, _ string, _ map[string]any, emit provider.EmitFn) error {
	idx := atomic.AddInt32(&f.calls, 1) - 1
	if f.emitDelta != "" {
		_ = emit(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: f.emitDelta})
	}
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
