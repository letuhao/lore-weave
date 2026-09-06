package api

import (
	"encoding/json"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// A stream that told its CALLER it failed must not record itself a success.
//
// 🔴 MEASURED 2026-09-01, on the first reproducible instance D-UPSTREAM-ERROR-WITH-NO-MESSAGE
// has had. A chat turn died with `upstream sent "error" with no error message` and this very
// process logged, for that turn's failing pass:
//
//	status='success' usage=false output_chars=0 duration_ms=431
//
// Two defect rows spent weeks narrowing to this hop, shipped a terminal log line to cross it,
// and the line said the opposite of what happened.
//
// THE CAUSE IS ONE SHARED CONVENTION. Every streamer reports a provider failure by EMITTING a
// StreamChunkError and then returning `errStreamDone` — the SAME sentinel a clean end-of-stream
// returns — so streamChat hands finalizeOutcome a nil error. `usage_logs.request_status` and
// the terminal line both read that classification, so both said success.
//
// The fix is in observe(), the one place every streamer's chunks pass through. Per-streamer it
// would be three edits and a fourth to remember.
func TestAStreamThatEmittedAnErrorChunkIsNotASuccess(t *testing.T) {
	g := &streamGuard{op: "chat"}
	g.observe(provider.StreamChunk{
		Kind:    provider.StreamChunkError,
		Code:    "LLM_UPSTREAM_ERROR",
		Message: `upstream sent "error" with no error message (response id "", status "")`,
	})
	g.finalizeOutcome(nil) // exactly what streamChat passes: the sentinel is swallowed

	if g.requestStatus != "provider_error" {
		t.Fatalf("request_status = %q, want provider_error — the stream sent the caller an "+
			"error chunk and then recorded itself a success", g.requestStatus)
	}
}

// The provider's words must reach the log, or the failure is legible only to the client that
// already received it.
func TestTheChunkErrorReachesTheTerminalLine(t *testing.T) {
	const msg = `upstream sent "error" with no error message (response id "", status "")`
	g := &streamGuard{op: "chat"}
	g.observe(provider.StreamChunk{
		Kind: provider.StreamChunkError, Code: "LLM_UPSTREAM_ERROR", Message: msg,
	})

	recs := captureLogs(t, func() { g.finalizeOutcome(nil) })
	line := terminalLine(t, recs)

	if line["status"] != "provider_error" {
		t.Errorf("status = %v, want provider_error", line["status"])
	}
	// A failure logged at INFO is a failure nobody greps for — the sibling guard's rule.
	if line["level"] != "WARN" {
		t.Errorf("level = %v, want WARN", line["level"])
	}
	if line["chunk_err_code"] != "LLM_UPSTREAM_ERROR" {
		t.Errorf("chunk_err_code = %v", line["chunk_err_code"])
	}
	if line["chunk_err"] != msg {
		t.Errorf("chunk_err = %v, want the provider's own message", line["chunk_err"])
	}
}

// The success path must stay success. This change must cost a healthy stream nothing.
func TestACleanStreamIsStillASuccess(t *testing.T) {
	g := &streamGuard{op: "chat"}
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "hello"})
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkUsage})
	g.finalizeOutcome(nil)

	if g.requestStatus != "success" {
		t.Fatalf("request_status = %q, want success", g.requestStatus)
	}
	recs := captureLogs(t, func() { g.finalizeOutcome(nil) })
	if line := terminalLine(t, recs); line["chunk_err"] != nil {
		t.Errorf("a clean stream logged chunk_err = %v", line["chunk_err"])
	}
}

// An ABORT outranks an error chunk: the budget guard cut the stream deliberately, and calling
// that a provider failure would blame the upstream for our own decision.
func TestAnAbortStillOutranksAnErrorChunk(t *testing.T) {
	g := &streamGuard{op: "chat", aborted: true}
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkError, Code: "X"})
	g.finalizeOutcome(nil)

	if g.requestStatus != "aborted" {
		t.Fatalf("request_status = %q, want aborted", g.requestStatus)
	}
}

// Only the FIRST error is kept. A stream that emits several must not have its cause overwritten
// by whatever came last.
func TestTheFirstErrorIsTheOneRecorded(t *testing.T) {
	g := &streamGuard{op: "chat"}
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkError, Code: "FIRST", Message: "the cause"})
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkError, Code: "SECOND", Message: "a consequence"})
	if g.errorCode != "FIRST" || g.errorMessage != "the cause" {
		t.Fatalf("kept %q/%q, want the FIRST error", g.errorCode, g.errorMessage)
	}
}

// A nil guard and a non-chat op must be untouched — observe returns early for both, and a
// panic here would take down every embeddings stream.
func TestObserveIsSafeForNilAndNonChat(t *testing.T) {
	var g *streamGuard
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkError})
	g.finalizeOutcome(nil)

	e := &streamGuard{op: "embeddings"}
	e.observe(provider.StreamChunk{Kind: provider.StreamChunkError, Code: "X"})
	if e.errorEmitted {
		t.Fatalf("a non-chat guard recorded an error chunk")
	}
}

var _ = json.Marshal
