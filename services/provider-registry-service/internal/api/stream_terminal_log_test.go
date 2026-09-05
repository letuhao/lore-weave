package api

// D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT / D-UPSTREAM-ERROR-WITH-NO-MESSAGE
//
//	THE INVARIANT. A stream that logged its START logs how it ENDED.
//
// Two defect rows spent weeks narrowing their stall to one hop and stopped there, on the same
// wall, written in each row's own words: provider-registry emits "chat context preflight" and
// then NOTHING. The identical single line for a turn that completes and for a turn that hangs
// forever. So "did provider-registry's call to LM Studio ever return?" had no witness on either
// side, and — as D-TURN-STALLS-AFTER-THE-SURFACE-IS-BUILT put it — "a call that was never made
// and a call that never returned look identical from outside".
//
// MEASURED BEFORE THE FIX: the whole file held four slog calls (two in the preflight gate, two
// Warns on billing failures) and finalizeOutcome held none. It computed the terminal status,
// stored it for the usage_logs audit row, and emitted nothing — while streamErr, the only place
// the provider's actual failure exists in this process, was classified into one word and then
// dropped. So every assertion below is RED against the original by construction: there was no
// terminal line to find.
//
// 🔴 WHAT THIS FILE DOES NOT CLAIM. A log line diagnoses nothing by itself. It makes the next
// occurrence readable, which is the state both rows were actually blocked in.

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// captureLogs swaps the default slog logger for one writing JSON to a buffer, runs fn, and
// returns the records. Restores the previous logger.
func captureLogs(t *testing.T, fn func()) []map[string]any {
	t.Helper()
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)
	fn()

	var out []map[string]any
	for _, line := range strings.Split(strings.TrimSpace(buf.String()), "\n") {
		if line == "" {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(line), &m); err != nil {
			t.Fatalf("log line is not JSON: %q (%v)", line, err)
		}
		out = append(out, m)
	}
	return out
}

func terminalLine(t *testing.T, recs []map[string]any) map[string]any {
	t.Helper()
	for _, r := range recs {
		if r["msg"] == "chat stream finished" {
			return r
		}
	}
	t.Fatalf("no terminal line was emitted — a stream that logged its start still says nothing "+
		"about how it ended, which is the wall both stall rows stopped at; got %v", recs)
	return nil
}

func TestAStreamSaysHowItEnded(t *testing.T) {
	cases := []struct {
		name       string
		g          *streamGuard
		err        error
		wantStatus string
		wantLevel  string
	}{
		{"success", &streamGuard{op: "chat"}, nil, "success", "INFO"},
		{"provider_error", &streamGuard{op: "chat"}, errors.New("boom"), "provider_error", "WARN"},
		{"cancelled", &streamGuard{op: "chat"}, context.Canceled, "cancelled", "WARN"},
		{"aborted", &streamGuard{op: "chat", aborted: true}, errStreamBudgetExceeded, "aborted", "WARN"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			recs := captureLogs(t, func() { c.g.finalizeOutcome(c.err) })
			line := terminalLine(t, recs)
			if line["status"] != c.wantStatus {
				t.Errorf("status: got %v want %v", line["status"], c.wantStatus)
			}
			// A silent failure that logs at INFO is a failure nobody greps for.
			if line["level"] != c.wantLevel {
				t.Errorf("level: got %v want %v", line["level"], c.wantLevel)
			}
		})
	}
}

func TestTheProvidersOwnWordsSurvive(t *testing.T) {
	// D-UPSTREAM-ERROR-WITH-NO-MESSAGE exists because this string had nowhere to go. Classifying
	// it into "provider_error" and discarding the text is what produced a row named for the
	// platform reporting a failure without saying why.
	g := &streamGuard{op: "chat"}
	recs := captureLogs(t, func() { g.finalizeOutcome(errors.New("Model is unloaded.")) })
	line := terminalLine(t, recs)
	if got, _ := line["err"].(string); !strings.Contains(got, "Model is unloaded.") {
		t.Fatalf("the provider's own message was dropped: err=%q — the whole point of the line "+
			"is that this text reaches a log", got)
	}
}

func TestASuccessDoesNotCarryAnErrorField(t *testing.T) {
	// The other direction. An err key on a clean stream would make every terminal line look like
	// a failure to anything grepping for one.
	g := &streamGuard{op: "chat"}
	recs := captureLogs(t, func() { g.finalizeOutcome(nil) })
	line := terminalLine(t, recs)
	if _, present := line["err"]; present {
		t.Fatalf("a successful stream logged an err field: %v", line)
	}
}

func TestTheLineAnswersDidTheCallEverReturn(t *testing.T) {
	// 🔴 THE FIELD THE TWO ROWS ACTUALLY NEEDED, and the reason status alone is not enough. Both
	// were stuck on whether the provider ever answered. A final usage chunk is that witness: it
	// arrives only if the stream reached a terminal event upstream. Without this field a
	// provider_error caused by a hung stream and one caused by a mid-stream failure read the same.
	hung := &streamGuard{op: "chat"}
	recs := captureLogs(t, func() { hung.finalizeOutcome(errors.New("read timeout")) })
	if got := terminalLine(t, recs)["usage"]; got != false {
		t.Fatalf("a stream that never got a usage chunk reported usage=%v", got)
	}

	answered := &streamGuard{op: "chat", finalUsage: &provider.StreamChunk{Kind: provider.StreamChunkUsage}}
	recs = captureLogs(t, func() { answered.finalizeOutcome(errors.New("read timeout")) })
	if got := terminalLine(t, recs)["usage"]; got != true {
		t.Fatalf("a stream that DID get a usage chunk reported usage=%v — the field cannot "+
			"distinguish the two cases and is inert", got)
	}
}

func TestASilentStreamGetsALength(t *testing.T) {
	// A hung stream's duration is the measurement the row could not take: it recorded "three
	// minutes of silence" by hand, from the harness side.
	g := &streamGuard{op: "chat"}
	recs := captureLogs(t, func() { g.finalizeOutcome(nil) })
	line := terminalLine(t, recs)
	if _, ok := line["duration_ms"]; !ok {
		t.Fatalf("no duration on the terminal line: %v", line)
	}
}

func TestANilGuardStillDoesNotPanicAndLogsNothing(t *testing.T) {
	// finalizeOutcome is nil-safe by contract and the log must not change that. A logger that
	// makes a nil-safe function panic would turn every unreserved stream into a crash.
	var nilG *streamGuard
	recs := captureLogs(t, func() { nilG.finalizeOutcome(nil) })
	for _, r := range recs {
		if r["msg"] == "chat stream finished" {
			t.Fatal("a nil guard emitted a terminal line for a stream that never opened")
		}
	}
}
