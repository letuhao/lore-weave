package api

// Unit tests for the Phase 6a-δ streamGuard logic (no DB). preflightStream +
// the settle reconcile dispatch are covered by stream_guardrail_integration_test.go.

import (
	"context"
	"encoding/json"
	"errors"
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
	var lastReconcile map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		// Only capture reconcile payloads here so /record doesn't overwrite
		// what each chat-branch assertion is checking. The new
		// D-PHASE6A-BETA-STREAM-RECORD path fires /record after /reconcile,
		// and the original test asserted on the LAST body of either kind —
		// that became chat+usage's /record payload (no actual_usd field) and
		// silently broke the test. /record gets its own dedicated test
		// below.
		if !strings.Contains(r.URL.Path, "/reconcile") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok"}`))
			return
		}
		lastReconcile = map[string]any{}
		_ = json.Unmarshal(raw, &lastReconcile)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	// tts → actual_usd omitted (nil → usage-billing charges the stored estimate).
	tts := &streamGuard{guardrail: gc, reservationID: uuid.New(), op: "tts"}
	tts.settle(context.Background())
	if _, present := lastReconcile["actual_usd"]; present {
		t.Fatalf("tts settle must omit actual_usd, got %v", lastReconcile["actual_usd"])
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
	if got, _ := lastReconcile["actual_usd"].(float64); got != 0.007 {
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
	if got, _ := lastReconcile["actual_usd"].(float64); got != 0.006 {
		t.Fatalf("chat+tally settle actual_usd: got %v want 0.006", got)
	}
}

// ── D-PHASE6A-BETA-STREAM-RECORD: model-level usage audit row ───────────────

// usageCapture records every call to a usage-billing stub so a single
// settle invocation can be inspected for both /reconcile AND /record.
type usageCapture struct {
	reconcileCount int
	recordCount    int
	recordBody     map[string]any
}

func newUsageStub(t *testing.T) (*httptest.Server, *usageCapture) {
	t.Helper()
	cap := &usageCapture{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		switch {
		case strings.Contains(r.URL.Path, "/reconcile"):
			cap.reconcileCount++
		case strings.Contains(r.URL.Path, "/record"):
			cap.recordCount++
			cap.recordBody = map[string]any{}
			_ = json.Unmarshal(raw, &cap.recordBody)
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	t.Cleanup(srv.Close)
	return srv, cap
}

// TestStreamGuard_Settle_RecordUsage_HappyPath locks the new audit-row
// write. A successfully-completed chat stream with a final usage chunk
// MUST fire BOTH /reconcile AND /record, with the record carrying the
// authoritative token counts + the synthetic job_id as request_id.
func TestStreamGuard_Settle_RecordUsage_HappyPath(t *testing.T) {
	srv, cap := newUsageStub(t)
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	jobID := uuid.New()
	ownerID := uuid.New()
	modelRef := uuid.New()
	reasoning := 7
	g := &streamGuard{
		guardrail: gc, reservationID: uuid.New(),
		jobID: jobID, ownerUserID: ownerID,
		modelSource: "user_model", modelRef: modelRef,
		op:      "chat",
		pricing: billing.Pricing{InputPerMTok: ptr(2), OutputPerMTok: ptr(10)},
		finalUsage: &provider.StreamChunk{
			Kind: provider.StreamChunkUsage,
			InputTokens: 1000, OutputTokens: 500,
			ReasoningTokens: &reasoning,
		},
	}
	g.settle(context.Background())

	if cap.reconcileCount != 1 || cap.recordCount != 1 {
		t.Fatalf("expected 1 reconcile + 1 record, got reconcile=%d record=%d",
			cap.reconcileCount, cap.recordCount)
	}
	body := cap.recordBody
	if body["request_id"] != jobID.String() {
		t.Errorf("request_id: got %v want %v", body["request_id"], jobID)
	}
	if body["owner_user_id"] != ownerID.String() {
		t.Errorf("owner_user_id: got %v want %v", body["owner_user_id"], ownerID)
	}
	if body["model_ref"] != modelRef.String() {
		t.Errorf("model_ref: got %v want %v", body["model_ref"], modelRef)
	}
	if body["model_source"] != "user_model" {
		t.Errorf("model_source: got %v want user_model", body["model_source"])
	}
	if body["purpose"] != "chat" {
		t.Errorf("purpose: got %v want chat", body["purpose"])
	}
	// Input tokens: 1000. Output: provider 500 + reasoning 7 = 507
	// (reasoning bills as output, mirrors usageCostUSD's pricing rule).
	if in, _ := body["input_tokens"].(float64); int(in) != 1000 {
		t.Errorf("input_tokens: got %v want 1000", body["input_tokens"])
	}
	if out, _ := body["output_tokens"].(float64); int(out) != 507 {
		t.Errorf("output_tokens: got %v want 507 (500 output + 7 reasoning)", body["output_tokens"])
	}
}

// TestStreamGuard_Settle_RecordUsage_RecordsOnAbort. P0-2 (B2): a hard-aborted
// stream still spent real tokens + produced partial output, so it MUST write an
// audit row (never zero rows) — carrying request_status="aborted". This overturns
// the pre-P0-2 behavior that skipped /record on abort (the audit hole).
func TestStreamGuard_Settle_RecordUsage_RecordsOnAbort(t *testing.T) {
	srv, cap := newUsageStub(t)
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	g := &streamGuard{
		guardrail: gc, reservationID: uuid.New(),
		jobID: uuid.New(), ownerUserID: uuid.New(),
		modelSource: "user_model", modelRef: uuid.New(),
		op:      "chat",
		pricing: billing.Pricing{InputPerMTok: ptr(2), OutputPerMTok: ptr(10)},
		finalUsage: &provider.StreamChunk{
			Kind: provider.StreamChunkUsage, InputTokens: 1000, OutputTokens: 500,
		},
		aborted:       true, // hard-abort from observe()
		requestStatus: "aborted",
	}
	g.settle(context.Background())

	if cap.reconcileCount != 1 {
		t.Fatalf("expected 1 reconcile (always runs), got %d", cap.reconcileCount)
	}
	if cap.recordCount != 1 {
		t.Fatalf("B2: an aborted stream MUST still record an audit row, got %d", cap.recordCount)
	}
	if cap.recordBody["request_status"] != "aborted" {
		t.Errorf("request_status: got %v want aborted", cap.recordBody["request_status"])
	}
}

// TestStreamGuard_Settle_RecordUsage_RecordsWithTallyWhenNoUsageChunk. P0-2 (B2):
// when the provider omitted the final usage chunk (disconnect / provider quirk) we
// still record — using the delta-estimated tally (the same numbers reconcile used)
// so the call is never audit-invisible.
func TestStreamGuard_Settle_RecordUsage_RecordsWithTallyWhenNoUsageChunk(t *testing.T) {
	srv, cap := newUsageStub(t)
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	g := &streamGuard{
		guardrail: gc, reservationID: uuid.New(),
		jobID: uuid.New(), ownerUserID: uuid.New(),
		modelSource: "user_model", modelRef: uuid.New(),
		op:            "chat",
		pricing:       billing.Pricing{OutputPerMTok: ptr(10)},
		inputCostUSD:  0.005,
		inputTokens:   42,
		outChars:      350, // → 100 Latin tokens via EstimateTokens
		requestStatus: "success",
		// finalUsage intentionally nil
	}
	g.settle(context.Background())

	if cap.reconcileCount != 1 {
		t.Fatalf("expected 1 reconcile, got %d", cap.reconcileCount)
	}
	if cap.recordCount != 1 {
		t.Fatalf("B2: chat with no usage chunk must still record (tally estimate), got %d", cap.recordCount)
	}
	if in, _ := cap.recordBody["input_tokens"].(float64); int(in) != 42 {
		t.Errorf("input_tokens: got %v want 42 (estimated)", cap.recordBody["input_tokens"])
	}
	if out, _ := cap.recordBody["output_tokens"].(float64); int(out) != 100 {
		t.Errorf("output_tokens: got %v want 100 (tally: 350 chars → 100 tokens)", cap.recordBody["output_tokens"])
	}
}

// TestStreamGuard_Settle_RecordUsage_LogsPayloads. P0-2 (B1): a completed chat
// stream MUST record a non-empty request payload (the assembled messages) + response
// payload (the accumulated completion) so the highest-volume path is auditable.
func TestStreamGuard_Settle_RecordUsage_LogsPayloads(t *testing.T) {
	srv, cap := newUsageStub(t)
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	g := &streamGuard{
		guardrail: gc, reservationID: uuid.New(),
		jobID: uuid.New(), ownerUserID: uuid.New(),
		modelSource: "user_model", modelRef: uuid.New(),
		op:      "chat",
		pricing: billing.Pricing{InputPerMTok: ptr(2), OutputPerMTok: ptr(10)},
		finalUsage: &provider.StreamChunk{
			Kind: provider.StreamChunkUsage, InputTokens: 5, OutputTokens: 6,
		},
		requestStatus: "success",
		requestPayload: map[string]any{
			"messages": []any{map[string]any{"role": "user", "content": "hi"}},
		},
	}
	g.completion.WriteString("hello world")
	g.settle(context.Background())

	if cap.recordCount != 1 {
		t.Fatalf("expected 1 record, got %d", cap.recordCount)
	}
	in, ok := cap.recordBody["input_payload"].(map[string]any)
	if !ok || in["messages"] == nil {
		t.Fatalf("B1: input_payload must carry the assembled request, got %v", cap.recordBody["input_payload"])
	}
	out, ok := cap.recordBody["output_payload"].(map[string]any)
	if !ok || out["content"] != "hello world" {
		t.Fatalf("B1: output_payload must carry the completion, got %v", cap.recordBody["output_payload"])
	}
	if cap.recordBody["request_status"] != "success" {
		t.Errorf("request_status: got %v want success", cap.recordBody["request_status"])
	}
}

// TestStreamGuard_FinalizeOutcome_Classifies locks the terminal-status mapping the
// settle audit row records (P0-2 B2).
func TestStreamGuard_FinalizeOutcome_Classifies(t *testing.T) {
	cases := []struct {
		name string
		g    *streamGuard
		err  error
		want string
	}{
		{"success", &streamGuard{}, nil, "success"},
		{"provider_error", &streamGuard{}, errors.New("boom"), "provider_error"},
		{"cancelled", &streamGuard{}, context.Canceled, "cancelled"},
		{"aborted", &streamGuard{aborted: true}, errStreamBudgetExceeded, "aborted"},
	}
	for _, c := range cases {
		c.g.finalizeOutcome(c.err)
		if c.g.requestStatus != c.want {
			t.Errorf("%s: got %q want %q", c.name, c.g.requestStatus, c.want)
		}
	}
	var nilG *streamGuard
	nilG.finalizeOutcome(nil) // must not panic
}

// TestStreamGuard_Observe_AccumulatesCompletion. P0-2 (B1): observe accumulates the
// visible answer (token deltas) but NOT reasoning deltas (hidden thinking).
func TestStreamGuard_Observe_AccumulatesCompletion(t *testing.T) {
	g := &streamGuard{op: "chat", abortUSD: 1e9}
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "Hello, "})
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkReasoning, Delta: "(thinking)"})
	g.observe(provider.StreamChunk{Kind: provider.StreamChunkToken, Delta: "world"})
	if got := g.completion.String(); got != "Hello, world" {
		t.Fatalf("completion must accumulate token deltas only (not reasoning): got %q", got)
	}
}

// TestStreamGuard_Settle_RecordUsage_SkipsForTts. tts streams have no
// token usage to record — the audit row is tied to per-token pricing
// which doesn't apply to fixed-per-char tts cost. Skip /record.
func TestStreamGuard_Settle_RecordUsage_SkipsForTts(t *testing.T) {
	srv, cap := newUsageStub(t)
	gc := billing.NewGuardrailClient(srv.URL, "tok", nil)

	g := &streamGuard{
		guardrail: gc, reservationID: uuid.New(),
		jobID: uuid.New(), ownerUserID: uuid.New(),
		modelSource: "user_model", modelRef: uuid.New(),
		op: "tts",
	}
	g.settle(context.Background())

	if cap.reconcileCount != 1 {
		t.Fatalf("expected 1 reconcile, got %d", cap.reconcileCount)
	}
	if cap.recordCount != 0 {
		t.Fatalf("tts must NOT call /record, got %d", cap.recordCount)
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
