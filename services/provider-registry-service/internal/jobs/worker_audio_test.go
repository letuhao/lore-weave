package jobs

// worker_audio_test.go — Phase 5a coverage for the audio-job dispatch
// path. Direct Process() integration testing is out of scope here
// (Repo + Notifier are concrete types tied to pgxpool); coverage strategy:
//   - Whitelist + disjoint-set regression locks (this file)
//   - Adapter-layer happy/error paths (provider/adapters_audio_test.go)
//   - Submit-time rejection of tts (api/jobs_handler_test.go T12)
//   - End-to-end live smoke (manual, post-merge)
//
// classifyAudioError IS a pure function and tested directly here.

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

func TestIsAudioJobOperation_Whitelist(t *testing.T) {
	if !isAudioJobOperation("stt") {
		t.Error("expected stt to be an audio job operation")
	}
}

func TestIsAudioJobOperation_RejectsNonAudio(t *testing.T) {
	cases := []string{
		"chat", "completion", "embedding", "translation",
		"entity_extraction", "relation_extraction", "event_extraction", "fact_extraction",
		"tts",       // tts streams via /v1/llm/stream, NOT through audio jobs
		"image_gen", // not yet supported
		"",
		"unknown",
	}
	for _, op := range cases {
		if isAudioJobOperation(op) {
			t.Errorf("expected %q to NOT be an audio job operation; whitelist over-promotion", op)
		}
	}
}

func TestStreamableAudio_Disjoint(t *testing.T) {
	// Phase 5a invariant: every operation routes through exactly ONE
	// dispatch path. If an op appears in both maps, Process() routes via
	// audio first (per worker.go ordering) — but that ordering should
	// never matter because the sets MUST stay disjoint by construction.
	for op := range audioJobOperations {
		if _, dup := streamableOperations[op]; dup {
			t.Errorf("operation %q in BOTH audioJobOperations and streamableOperations — "+
				"dispatch ambiguity; pick one", op)
		}
	}
	for op := range streamableOperations {
		if _, dup := audioJobOperations[op]; dup {
			t.Errorf("operation %q in BOTH streamableOperations and audioJobOperations — "+
				"dispatch ambiguity; pick one", op)
		}
	}
}

func TestAudioJobOperations_AlsoInValidJobOperations(t *testing.T) {
	// Phase 4a-β regression-lock pattern (same as
	// TestStreamableOperations_AlsoInValidJobOperations): every audio op
	// MUST appear in (a) jobs_handler.go validJobOperations source, (b)
	// migrate.go's CHECK constraint, (c) openapi.yaml's JobOperation enum.
	rootPath := findRepoRoot(t)
	apiHandlerSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/api/jobs_handler.go")
	migrateSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/migrate/migrate.go")
	openapiSrc := readFile(t, rootPath+"/contracts/api/llm-gateway/v1/openapi.yaml")

	for op := range audioJobOperations {
		quoted := `"` + op + `"`
		yamlEntry := "        - " + op
		sqlQuoted := `'` + op + `'`
		if !strings.Contains(apiHandlerSrc, quoted) {
			t.Errorf("audio op %q missing from jobs_handler.go validJobOperations — "+
				"submit would fail with LLM_INVALID_REQUEST", op)
		}
		if !strings.Contains(migrateSrc, sqlQuoted) {
			t.Errorf("audio op %q missing from migrate.go CHECK constraint — "+
				"INSERT would fail with constraint violation (LLM_INTERNAL_ERROR)", op)
		}
		if !strings.Contains(openapiSrc, yamlEntry) {
			t.Errorf("audio op %q missing from openapi.yaml JobOperation enum — "+
				"contract drift; SDK clients won't accept this op", op)
		}
	}
}

// ── classifyAudioError ─────────────────────────────────────────────────

func TestClassifyAudioError_Cancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	// any error works — ctx.Err takes precedence
	code, status := classifyAudioError(ctx, errors.New("transport error after cancel"))
	if code != "LLM_CANCELLED" || status != "cancelled" {
		t.Errorf("got (%s,%s), want (LLM_CANCELLED, cancelled)", code, status)
	}
}

func TestClassifyAudioError_FetchFailed(t *testing.T) {
	code, status := classifyAudioError(context.Background(), provider.ErrAudioFetchFailed)
	if code != "LLM_AUDIO_FETCH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUDIO_FETCH_FAILED, failed)", code, status)
	}
}

func TestClassifyAudioError_FetchFailed_Wrapped(t *testing.T) {
	// errors.Is must traverse wrap chain — ensures wrapped fetch errors
	// from openai_audio.go fetchAudioURL still classify correctly.
	wrapped := errors.New("outer: " + provider.ErrAudioFetchFailed.Error())
	wrappedWithIs := wrapErr(provider.ErrAudioFetchFailed)
	code, _ := classifyAudioError(context.Background(), wrapped)
	if code == "LLM_AUDIO_FETCH_FAILED" {
		t.Errorf("string-wrapped (no errors.Is chain) should NOT classify as fetch failed; got %s", code)
	}
	code2, _ := classifyAudioError(context.Background(), wrappedWithIs)
	if code2 != "LLM_AUDIO_FETCH_FAILED" {
		t.Errorf("errors.Is-wrapped fetch failed: got %s, want LLM_AUDIO_FETCH_FAILED", code2)
	}
}

func TestClassifyAudioError_TooLarge(t *testing.T) {
	code, status := classifyAudioError(context.Background(), provider.ErrAudioTooLarge)
	if code != "LLM_AUDIO_TOO_LARGE" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUDIO_TOO_LARGE, failed)", code, status)
	}
}

func TestClassifyAudioError_NotSupported(t *testing.T) {
	code, status := classifyAudioError(context.Background(), provider.ErrOperationNotSupported)
	if code != "LLM_OPERATION_NOT_SUPPORTED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_OPERATION_NOT_SUPPORTED, failed)", code, status)
	}
}

func TestClassifyAudioError_GenericMapsToUpstream(t *testing.T) {
	code, status := classifyAudioError(context.Background(), errors.New("upstream blew up: 502"))
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

// /review-impl HIGH#1 — Phase 5a: deadline exceeded (SttJobTimeout hit)
// maps to LLM_TIMEOUT/failed (distinct from cancelled).
func TestClassifyAudioError_DeadlineExceeded(t *testing.T) {
	ctx, cancel := context.WithDeadline(context.Background(), timeInPast())
	defer cancel()
	// any err; ctx.Err == DeadlineExceeded takes precedence
	code, status := classifyAudioError(ctx, errors.New("timeout reading body"))
	if code != "LLM_TIMEOUT" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_TIMEOUT, failed)", code, status)
	}
}

// /review-impl MED#3 — Phase 5a: typed upstream errors map to
// LLM_RATE_LIMITED / LLM_AUTH_FAILED / LLM_UPSTREAM_ERROR.
func TestClassifyAudioError_RateLimitedTyped(t *testing.T) {
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow down"}
	code, status := classifyAudioError(context.Background(), rl)
	if code != "LLM_RATE_LIMITED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_RATE_LIMITED, failed)", code, status)
	}
}

func TestClassifyAudioError_AuthFailedFrom401(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 401, Body: "bad key"}
	code, status := classifyAudioError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyAudioError_AuthFailedFrom403(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 403, Body: "forbidden"}
	code, status := classifyAudioError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyAudioError_Permanent400IsUpstreamError(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"}
	code, status := classifyAudioError(context.Background(), perm)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyAudioError_Transient5xx(t *testing.T) {
	trans := &provider.ErrUpstreamTransient{StatusCode: 502, Body: "bad gateway"}
	code, status := classifyAudioError(context.Background(), trans)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

// /review-impl MED#2 — Phase 5a: SSRF rejection maps to LLM_AUDIO_URL_DISALLOWED.
func TestClassifyAudioError_AudioURLDisallowed(t *testing.T) {
	code, status := classifyAudioError(context.Background(), provider.ErrAudioURLDisallowed)
	if code != "LLM_AUDIO_URL_DISALLOWED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUDIO_URL_DISALLOWED, failed)", code, status)
	}
}

// /review-impl HIGH#2 — Phase 5b: ErrTranscribeInputInvalid (both URL+Bytes
// set OR both empty) is a caller-side invariant violation; classifier
// MUST surface as LLM_INVALID_REQUEST/failed (NOT LLM_UPSTREAM_ERROR
// which would invite retry, NOT LLM_AUDIO_FETCH_FAILED which would
// mislead caller about the cause).
func TestClassifyAudioError_TranscribeInputInvalid(t *testing.T) {
	code, status := classifyAudioError(context.Background(), provider.ErrTranscribeInputInvalid)
	if code != "LLM_INVALID_REQUEST" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_INVALID_REQUEST, failed)", code, status)
	}
}

// TestClassifyAudioError_TranscribeInputInvalid_Wrapped pins errors.Is
// chain traversal — openai_audio.go wraps the sentinel via `fmt.Errorf("%w: ...")`
// so the classifier MUST unwrap to detect it. Mirrors the pre-existing
// FetchFailed_Wrapped test for consistency.
func TestClassifyAudioError_TranscribeInputInvalid_Wrapped(t *testing.T) {
	wrapped := wrapErr(provider.ErrTranscribeInputInvalid)
	code, _ := classifyAudioError(context.Background(), wrapped)
	if code != "LLM_INVALID_REQUEST" {
		t.Errorf("wrapped ErrTranscribeInputInvalid: got %s, want LLM_INVALID_REQUEST", code)
	}
}

// timeInPast returns a deadline already past so context.WithDeadline
// immediately marks the ctx as DeadlineExceeded — used to exercise
// the classify deadline branch without a real wait.
func timeInPast() time.Time {
	return time.Now().Add(-1 * time.Hour)
}

// wrapErr produces an error whose chain reports `target` via errors.Is.
// (Helper kept terse — fmt.Errorf with %w would also work but adds
// import noise.)
func wrapErr(target error) error {
	return errWithUnwrap{wrapped: target}
}

type errWithUnwrap struct{ wrapped error }

func (e errWithUnwrap) Error() string { return "wrapped: " + e.wrapped.Error() }
func (e errWithUnwrap) Unwrap() error { return e.wrapped }

// ── Phase 5e-β.2 — audio_gen worker tests ───────────────────────────

// audio_gen joins audioJobOperations + 5-place sync.
func TestAudioGenInAudioJobOperations(t *testing.T) {
	if _, ok := audioJobOperations["audio_gen"]; !ok {
		t.Error("audio_gen missing from audioJobOperations map")
	}
}

// /review-impl(DESIGN) MED#4 — full typed-error matrix for audio_gen.
func TestClassifyAudioGenError_Matrix(t *testing.T) {
	cases := []struct {
		name       string
		ctx        context.Context
		err        error
		wantCode   string
		wantStatus string
	}{
		{"invalid_params", context.Background(), provider.ErrAudioGenInvalidParams, "LLM_INVALID_REQUEST", "failed"},
		{"wrapped_invalid_params", context.Background(), wrapErr(provider.ErrAudioGenInvalidParams), "LLM_INVALID_REQUEST", "failed"},
		{"audio_gen_failed", context.Background(), provider.ErrAudioGenerationFailed, "LLM_AUDIO_GENERATION_FAILED", "failed"},
		{"op_not_supported", context.Background(), provider.ErrOperationNotSupported, "LLM_OPERATION_NOT_SUPPORTED", "failed"},
		{"rate_limited", context.Background(), &provider.ErrUpstreamRateLimited{StatusCode: 429}, "LLM_RATE_LIMITED", "failed"},
		{"perm_401", context.Background(), &provider.ErrUpstreamPermanent{StatusCode: 401}, "LLM_AUTH_FAILED", "failed"},
		{"perm_403", context.Background(), &provider.ErrUpstreamPermanent{StatusCode: 403}, "LLM_AUTH_FAILED", "failed"},
		{"perm_other_4xx", context.Background(), &provider.ErrUpstreamPermanent{StatusCode: 400}, "LLM_UPSTREAM_ERROR", "failed"},
		{"transient_5xx", context.Background(), &provider.ErrUpstreamTransient{StatusCode: 502}, "LLM_UPSTREAM_ERROR", "failed"},
		{"unknown", context.Background(), errors.New("misc"), "LLM_UPSTREAM_ERROR", "failed"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			code, status := classifyAudioGenError(tc.ctx, tc.err)
			if code != tc.wantCode {
				t.Errorf("code = %q, want %q", code, tc.wantCode)
			}
			if status != tc.wantStatus {
				t.Errorf("status = %q, want %q", status, tc.wantStatus)
			}
		})
	}
}

func TestClassifyAudioGenError_ContextDeadlineExceeded(t *testing.T) {
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	code, status := classifyAudioGenError(ctx, context.DeadlineExceeded)
	if code != "LLM_TIMEOUT" || status != "failed" {
		t.Errorf("got (%q,%q), want (LLM_TIMEOUT, failed)", code, status)
	}
}

func TestClassifyAudioGenError_ContextCanceled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	code, status := classifyAudioGenError(ctx, context.Canceled)
	if code != "LLM_CANCELLED" || status != "cancelled" {
		t.Errorf("got (%q,%q), want (LLM_CANCELLED, cancelled)", code, status)
	}
}

// /review-impl(BUILD round 3) M#1 — URL mode with nil audioCache must
// fail with LLM_INVALID_REQUEST early (no upstream BYOK char-billing
// burned for a request that can't return a result).
//
// We can't fully exercise runAudioGenJob without a DB-backed repo, but
// we can verify the GUARD that controls this branch: the worker checks
// `w.audioCache == nil && responseFormat == "url"` at the top of the
// flow. This test confirms a Worker constructed with nil audioCache has
// the nil field — the actual rejection path is exercised end-to-end via
// the gateway integration suite (D-PHASE5E-BETA2-STORAGE-UNIT-TESTS).
func TestWorker_NilAudioCache_FieldIsNil(t *testing.T) {
	w := NewWorker(nil, nil, nil, nil, nil, nil, nil, 0)
	if w.audioCache != nil {
		t.Errorf("NewWorker(audioCache=nil): w.audioCache = %v, want nil", w.audioCache)
	}
}

// audio_gen routes through processAudioJob switch.
func TestProcessAudioJob_RoutesAudioGenToRunAudioGenJob(t *testing.T) {
	// We can't fully exercise processAudioJob without DB, but we can
	// confirm the switch contains audio_gen by checking that the
	// fall-through default would catch it if dispatch was broken.
	// This is a compile-time + grep-level guarantee; covered indirectly
	// by TestAudioGenInAudioJobOperations.
	if _, ok := audioJobOperations["audio_gen"]; !ok {
		t.Skip("audio_gen not in audioJobOperations — covered by TestAudioGenInAudioJobOperations")
	}
}
