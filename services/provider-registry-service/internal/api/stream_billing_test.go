package api

// Unit tests for the Phase 6a-δ streamGuard logic (no DB). preflightStream +
// the settle reconcile dispatch are covered by stream_guardrail_integration_test.go.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/provider"
)

// ── observe / hard-abort ────────────────────────────────────────────────────

func TestStreamGuard_Observe_AbortsOnRunaway(t *testing.T) {
	// outPerTok = 1000/1e6 = 1e-3 USD/token; abortUSD = 0.01 → aborts past
	// ~10 output tokens. 350 Latin chars ≈ 100 tokens → well over.
	g := &streamGuard{
		op:       "chat",
		pricing:  billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1000)},
		abortUSD: 0.01,
	}
	chunk := provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: strings.Repeat("a", 350)}
	if !g.observe(chunk) {
		t.Fatal("expected a hard-abort once the tally crosses abortUSD")
	}
	if !g.didAbort() {
		t.Fatal("aborted flag must be set after an abort")
	}
}

func TestStreamGuard_Observe_NoAbortUnderBudget(t *testing.T) {
	g := &streamGuard{
		op:       "chat",
		pricing:  billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1)},
		abortUSD: 1000,
	}
	if g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "hello there"}) {
		t.Fatal("must not abort well under budget")
	}
	if g.didAbort() {
		t.Fatal("aborted flag must stay false under budget")
	}
}

func TestStreamGuard_Observe_CJK_IsUpperBound(t *testing.T) {
	// 200 CJK output chars tokenize at ~1 token/char → ~200 tokens. With
	// outPerTok = 1.0 USD/token that is ~$200, which must cross a $100
	// abort threshold. Under the old chars/4 divisor it would be ~50
	// tokens ≈ $50 and would NOT abort — this locks the script-aware count.
	g := &streamGuard{
		op:       "chat",
		pricing:  billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1e6)},
		abortUSD: 100,
	}
	cjk := provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: strings.Repeat("语", 200)}
	if !g.observe(cjk) {
		t.Fatal("200 CJK output chars must cross the $100 abort threshold (chars/4 would under-count to ~$50)")
	}
}

func TestStreamGuard_Observe_ReasoningBillsAsOutput(t *testing.T) {
	g := &streamGuard{
		op:       "chat",
		pricing:  billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1000)},
		abortUSD: 0.01,
	}
	// A reasoning delta accumulates against the output tally just like a
	// token delta.
	if !g.observe(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: strings.Repeat("a", 350)}) {
		t.Fatal("reasoning deltas must count toward the output tally")
	}
}

func TestStreamGuard_Observe_TtsNeverAborts(t *testing.T) {
	g := &streamGuard{op: "tts", abortUSD: 0} // zero budget
	if g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: strings.Repeat("a", 9999)}) {
		t.Fatal("a tts stream must never hard-abort (cost is fixed + reserved up front)")
	}
}

func TestStreamGuard_Observe_CapturesFinalUsage(t *testing.T) {
	g := &streamGuard{op: "chat", abortUSD: 1e9}
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkUsage, InputTokens: 10, OutputTokens: 20})
	if g.finalUsage == nil {
		t.Fatal("a usage chunk must be captured as finalUsage")
	}
	if g.finalUsage.InputTokens != 10 || g.finalUsage.OutputTokens != 20 {
		t.Fatalf("finalUsage wrong: %+v", g.finalUsage)
	}
}

// ── cost arithmetic ─────────────────────────────────────────────────────────

func TestStreamGuard_UsageCostUSD(t *testing.T) {
	g := &streamGuard{pricing: billing.Pricing{InputPerMTok: ptr(2), OutputPerMTok: ptr(10)}}
	reasoning := 100
	u := provider.StreamChunk{
		Kind:        provider.StreamChunkUsage,
		InputTokens: 1000, OutputTokens: 500, ReasoningTokens: &reasoning,
	}
	// 1000/1e6·2 + (500+100)/1e6·10 = 0.002 + 0.006 = 0.008.
	if got := g.usageCostUSD(u); got != 0.008 {
		t.Fatalf("usageCostUSD: got %v want 0.008", got)
	}
}

func TestStreamGuard_TallyCostUSD(t *testing.T) {
	g := &streamGuard{
		pricing:      billing.Pricing{OutputPerMTok: ptr(10)},
		inputCostUSD: 0.005,
		outChars:     350, // → 100 Latin tokens
	}
	g.outNonASCII = 0
	// 0.005 + 100/1e6·10 = 0.005 + 0.001 = 0.006.
	if got := g.tallyCostUSD(); got != 0.006 {
		t.Fatalf("tallyCostUSD: got %v want 0.006", got)
	}
}

// ── nil safety ──────────────────────────────────────────────────────────────

func TestStreamGuard_NilSafe(t *testing.T) {
	var g *streamGuard // a stream with the guardrail not wired
	if g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "x"}) {
		t.Fatal("nil guard observe must return false")
	}
	if g.didAbort() {
		t.Fatal("nil guard didAbort must return false")
	}
	g.settle(context.Background()) // must not panic
}

func TestMinFloat(t *testing.T) {
	if minFloat(3, 7) != 3 || minFloat(7, 3) != 3 || minFloat(5, 5) != 5 {
		t.Fatal("minFloat wrong")
	}
}

// ── settle reconcile dispatch ───────────────────────────────────────────────

// TestStreamGuard_Settle_Dispatch locks which actual_usd settle sends for
// each of its three branches (/review-impl 6a-δ LOW#2).
func TestStreamGuard_Settle_Dispatch(t *testing.T) {
	var lastBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		lastBody = map[string]any{}
		_ = json.Unmarshal(raw, &lastBody)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	// tts → actual_usd omitted (nil → usage-billing charges the stored estimate).
	tts := &streamGuard{guardrail: gc, reservationID: uuid.New(), op: "tts"}
	tts.settle(context.Background())
	if _, present := lastBody["actual_usd"]; present {
		t.Fatalf("tts settle must omit actual_usd, got %v", lastBody["actual_usd"])
	}

	// chat + a final usage chunk → authoritative provider cost.
	reasoning := 0
	chatU := &streamGuard{
		guardrail: gc, reservationID: uuid.New(), op: "chat",
		pricing: billing.Pricing{InputPerMTok: ptr(2), OutputPerMTok: ptr(10)},
		finalUsage: &provider.StreamChunk{
			Kind: provider.StreamChunkUsage, InputTokens: 1000, OutputTokens: 500, ReasoningTokens: &reasoning,
		},
	}
	chatU.settle(context.Background())
	// 1000/1e6·2 + 500/1e6·10 = 0.002 + 0.005 = 0.007.
	if got, _ := lastBody["actual_usd"].(float64); got != 0.007 {
		t.Fatalf("chat+usage settle actual_usd: got %v want 0.007", got)
	}

	// chat + no usage chunk → the delta-estimated running tally.
	chatT := &streamGuard{
		guardrail: gc, reservationID: uuid.New(), op: "chat",
		pricing:      billing.Pricing{OutputPerMTok: ptr(10)},
		inputCostUSD: 0.005,
		outChars:     350, // → 100 Latin tokens
	}
	chatT.settle(context.Background())
	// 0.005 + 100/1e6·10 = 0.006.
	if got, _ := lastBody["actual_usd"].(float64); got != 0.006 {
		t.Fatalf("chat+tally settle actual_usd: got %v want 0.006", got)
	}
}

// ── abort end-to-end (streamChat wire behavior) ─────────────────────────────

// fakeStreamAdapter embeds the provider.Adapter interface (nil) and overrides
// only Stream — the test never calls the other methods. Stream replays
// scripted chunks, stopping on the emit error per the EmitFn contract.
type fakeStreamAdapter struct {
	provider.Adapter
	chunks []provider.StreamChunk
}

func (f *fakeStreamAdapter) Stream(_ context.Context, _, _, _ string, _ map[string]any, emit provider.EmitFn) error {
	for _, c := range f.chunks {
		if err := emit(c); err != nil {
			return err // contract: stop streaming on an emit error
		}
	}
	return nil
}

func TestStreamChat_HardAbort_EmitsErrorFrameAndStops(t *testing.T) {
	// outPerTok = 1e6/1e6 = 1.0 USD/token; abortUSD = 10 → ~10 output
	// tokens. A tiny first delta stays under; a huge second delta crosses.
	guard := &streamGuard{
		op:       "chat",
		pricing:  billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1e6)},
		abortUSD: 10,
	}
	adapter := &fakeStreamAdapter{chunks: []provider.StreamChunk{
		{Kind: provider.StreamChunkToken, Delta: "hi"},                      // ~1 token — under
		{Kind: provider.StreamChunkToken, Delta: strings.Repeat("x", 5000)}, // huge — aborts
		{Kind: provider.StreamChunkToken, Delta: "MUST-NOT-REACH-THE-WIRE"}, // after abort
	}}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/stream", nil)

	(&Server{}).streamChat(req, rr, rr, adapter, "", "", "model-x", streamRequest{}, guard)

	body := rr.Body.String()
	if !strings.Contains(body, "LLM_QUOTA_EXCEEDED") {
		t.Fatalf("an aborted stream must emit an LLM_QUOTA_EXCEEDED error frame; body=%q", body)
	}
	if strings.Contains(body, "MUST-NOT-REACH-THE-WIRE") {
		t.Fatal("chunks after the hard-abort must not be written to the wire")
	}
	if !guard.didAbort() {
		t.Fatal("guard.aborted must be set")
	}
	// The first (under-budget) delta did reach the wire.
	if !strings.Contains(body, "hi") {
		t.Fatal("the under-budget delta before the abort should have streamed")
	}
}
