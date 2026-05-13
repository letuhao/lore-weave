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
