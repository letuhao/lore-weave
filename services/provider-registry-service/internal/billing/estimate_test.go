package billing

import (
	"errors"
	"math"
	"strings"
	"testing"
)

func testEstimator() Estimator {
	return Estimator{
		MaxOutputTokensDefault:    4096,
		ExtractionOutputCeiling:   8192,
		SystemPromptTokenEstimate: 1000,
	}
}

// textP is a fully-priced text Pricing.
func textP(in, out float64) Pricing {
	return Pricing{InputPerMTok: usd(in), OutputPerMTok: usd(out)}
}

// ── happy path / pricing presence ──────────────────────────────────────────

func TestEstimate_Chat_HappyPath(t *testing.T) {
	e := testEstimator()
	input := map[string]any{
		"messages":   []any{map[string]any{"role": "user", "content": "hello world"}},
		"max_tokens": float64(100),
	}
	got, err := e.EstimateUSD("chat", input, textP(1.0, 2.0), 1)
	if err != nil {
		t.Fatalf("EstimateUSD: %v", err)
	}
	// tokens_in = ceil(15 ASCII chars / 3.5) = 5; tokens_out = 100.
	want := roundUpUSD(5.0/1e6*1.0 + 100.0/1e6*2.0)
	if math.Abs(got-want) > 1e-12 {
		t.Fatalf("chat estimate: got %v want %v", got, want)
	}
}

func TestEstimate_Chat_OmittedMaxTokens_UsesDefault(t *testing.T) {
	e := testEstimator()
	input := map[string]any{"messages": []any{map[string]any{"content": "hi"}}}
	got, err := e.EstimateUSD("chat", input, textP(0, 3.0), 1)
	if err != nil {
		t.Fatalf("EstimateUSD: %v", err)
	}
	// input_per_mtok is 0; output = MaxOutputTokensDefault(4096) * 3.0/1e6.
	want := roundUpUSD(4096.0 / 1e6 * 3.0)
	if math.Abs(got-want) > 1e-12 {
		t.Fatalf("default max_tokens estimate: got %v want %v", got, want)
	}
}

func TestEstimate_Unpriced_MissingOutputDimension(t *testing.T) {
	e := testEstimator()
	// input_per_mtok present, output_per_mtok absent → unpriced for chat.
	p := Pricing{InputPerMTok: usd(1.0)}
	if _, err := e.EstimateUSD("chat", map[string]any{"messages": "x"}, p, 1); !errors.Is(err, ErrUnpriced) {
		t.Fatalf("expected ErrUnpriced, got %v", err)
	}
}

func TestEstimate_ExplicitZero_IsPricedFree(t *testing.T) {
	e := testEstimator()
	// A genuinely-free local model: both dimensions explicitly 0 → $0, no error.
	got, err := e.EstimateUSD("chat", map[string]any{"messages": "some prompt"}, textP(0, 0), 1)
	if err != nil {
		t.Fatalf("explicit-zero pricing should not error: %v", err)
	}
	if got != 0 {
		t.Fatalf("explicit-zero pricing should cost $0, got %v", got)
	}
}

// ── multilingual upper-bound (/review-impl HIGH#1 + BUILD CJK-divisor fix) ──

func TestEstimate_CJK_IsUpperBound(t *testing.T) {
	// 200 CJK characters. A CJK script tokenizes at ~1 token per character,
	// so the real token count is ~200. The estimate MUST be >= that.
	cjk := strings.Repeat("语", 200)
	e := testEstimator()
	ti := e.InputTokens(map[string]any{"text": cjk}, 1)

	const realTokens = 200
	if ti < realTokens {
		t.Fatalf("CJK estimate %d under-bounds real ~%d tokens — guardrail bug", ti, realTokens)
	}
	// Regression-lock: the old English-average chars/4 divisor would yield
	// ~50 here, a ~4× under-estimate. Lock that this never regresses.
	if ti <= 200/4 {
		t.Fatalf("CJK estimate %d collapsed toward the chars/4 under-bound", ti)
	}
}

func TestEstimate_Latin_StaysAboveAverage(t *testing.T) {
	// 350 ASCII chars / 3.5 = 100 tokens; English averages ~4 chars/token
	// (~87 tokens) so the 3.5 divisor over-estimates — the safe direction.
	latin := strings.Repeat("a", 350)
	ti := testEstimator().InputTokens(map[string]any{"text": latin}, 1)
	if ti != 100 {
		t.Fatalf("Latin estimate: got %d want 100", ti)
	}
}

// ── translation: output scales with input (/review-impl MED#4) ─────────────

func TestEstimate_Translation_OutputScalesWithInput(t *testing.T) {
	e := testEstimator()
	latin := strings.Repeat("a", 350) // → 100 input tokens
	got, err := e.EstimateUSD("translation", map[string]any{"text": latin}, textP(1.0, 1.0), 1)
	if err != nil {
		t.Fatalf("EstimateUSD: %v", err)
	}
	// tokens_out = ceil(100 * 1.5) = 150.
	want := roundUpUSD(100.0/1e6*1.0 + 150.0/1e6*1.0)
	if math.Abs(got-want) > 1e-12 {
		t.Fatalf("translation estimate: got %v want %v", got, want)
	}
}

// ── extraction: bounded JSON output ceiling ────────────────────────────────

func TestEstimate_Extraction_UsesOutputCeiling(t *testing.T) {
	e := testEstimator()
	latin := strings.Repeat("a", 350) // → 100 input tokens
	for _, op := range []string{"entity_extraction", "relation_extraction", "event_extraction", "fact_extraction"} {
		got, err := e.EstimateUSD(op, map[string]any{"text": latin}, textP(1.0, 1.0), 1)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		want := roundUpUSD(100.0/1e6*1.0 + 8192.0/1e6*1.0)
		if math.Abs(got-want) > 1e-12 {
			t.Fatalf("%s estimate: got %v want %v", op, got, want)
		}
	}
}

// ── chunked job: per-chunk system-prompt overhead (/review-impl MED#5) ─────

func TestEstimate_ChunkedJob_AddsPerChunkOverhead(t *testing.T) {
	e := testEstimator()
	input := map[string]any{"text": strings.Repeat("a", 350)} // 100 base tokens

	base := e.InputTokens(input, 1)
	chunked := e.InputTokens(input, 5)
	// 5 chunks re-send the system prompt 4 extra times × 1000 tokens.
	if delta := chunked - base; delta != 4*1000 {
		t.Fatalf("chunk overhead: got delta %d want %d", delta, 4*1000)
	}
	// nchunks < 1 is normalized to 1 (no overhead, no panic).
	if e.InputTokens(input, 0) != base {
		t.Fatalf("nchunks=0 should behave as nchunks=1")
	}
}

// TestEstimate_ChunkedChat_OutputScalesWithNchunks locks /review-impl MED#2:
// a chunked chat job runs nchunks provider calls, each emitting up to
// max_tokens, so the output term must scale with nchunks.
func TestEstimate_ChunkedChat_OutputScalesWithNchunks(t *testing.T) {
	e := testEstimator()
	input := map[string]any{"messages": "short prompt", "max_tokens": float64(1000)}
	p := textP(0, 10.0) // input free → isolates the output term

	single, err := e.EstimateUSD("chat", input, p, 1)
	if err != nil {
		t.Fatalf("single-chunk: %v", err)
	}
	five, err := e.EstimateUSD("chat", input, p, 5)
	if err != nil {
		t.Fatalf("five-chunk: %v", err)
	}
	if math.Abs(five-5*single) > 1e-9 {
		t.Fatalf("chunked chat output must scale ×nchunks: 1-chunk=%v 5-chunk=%v", single, five)
	}
}

// ── pricing validation (/review-impl MED#3) ────────────────────────────────

func TestPricing_Validate(t *testing.T) {
	if err := (Pricing{InputPerMTok: usd(1), OutputPerMTok: usd(0)}).Validate(); err != nil {
		t.Fatalf("a valid pricing (with an explicit 0) was rejected: %v", err)
	}
	if err := (Pricing{}).Validate(); err != nil {
		t.Fatalf("empty pricing must be valid (fail-closed, not invalid): %v", err)
	}
	if err := (Pricing{InputPerMTok: usd(-1)}).Validate(); err == nil {
		t.Fatal("negative input_per_mtok must be rejected")
	}
	if err := (Pricing{PerImage: usd(-0.01)}).Validate(); err == nil {
		t.Fatal("negative per_image must be rejected")
	}
}

// ── embedding: input-only ──────────────────────────────────────────────────

func TestEstimate_Embedding_InputOnly(t *testing.T) {
	e := testEstimator()
	latin := strings.Repeat("a", 350) // 100 tokens
	got, err := e.EstimateUSD("embedding", map[string]any{"text": latin}, Pricing{InputPerMTok: usd(2.0)}, 1)
	if err != nil {
		t.Fatalf("EstimateUSD: %v", err)
	}
	if want := roundUpUSD(100.0 / 1e6 * 2.0); math.Abs(got-want) > 1e-12 {
		t.Fatalf("embedding estimate: got %v want %v", got, want)
	}
}

// ── media operations ───────────────────────────────────────────────────────

func TestEstimate_MediaOps(t *testing.T) {
	e := testEstimator()

	img, err := e.EstimateUSD("image_gen", map[string]any{"n": float64(3)}, Pricing{PerImage: usd(0.04)}, 1)
	if err != nil || math.Abs(img-roundUpUSD(0.12)) > 1e-12 {
		t.Fatalf("image_gen: got %v err %v", img, err)
	}
	// n omitted defaults to 1.
	img1, err := e.EstimateUSD("image_gen", map[string]any{}, Pricing{PerImage: usd(0.04)}, 1)
	if err != nil || math.Abs(img1-roundUpUSD(0.04)) > 1e-12 {
		t.Fatalf("image_gen default n: got %v err %v", img1, err)
	}

	// video_gen reads the `duration` field (matching validateVideoGenInput).
	vid, err := e.EstimateUSD("video_gen", map[string]any{"duration": float64(10)}, Pricing{PerSecond: usd(0.05)}, 1)
	if err != nil || math.Abs(vid-roundUpUSD(0.5)) > 1e-12 {
		t.Fatalf("video_gen: got %v err %v", vid, err)
	}
	// An omitted duration must NOT estimate $0 (that would let an unbounded
	// video job past the guardrail) — it estimates at the 60s validator max.
	vidOmit, err := e.EstimateUSD("video_gen", map[string]any{}, Pricing{PerSecond: usd(0.05)}, 1)
	if err != nil || math.Abs(vidOmit-roundUpUSD(60*0.05)) > 1e-12 {
		t.Fatalf("video_gen omitted duration: got %v err %v (want %v)", vidOmit, err, roundUpUSD(60*0.05))
	}

	aud, err := e.EstimateUSD("audio_gen", map[string]any{"texts": []any{"abc", "de"}}, Pricing{PerKChar: usd(2.0)}, 1)
	if err != nil || math.Abs(aud-roundUpUSD(5.0/1000.0*2.0)) > 1e-12 {
		t.Fatalf("audio_gen: got %v err %v", aud, err)
	}
}

func TestEstimate_MediaOp_Unpriced(t *testing.T) {
	e := testEstimator()
	if _, err := e.EstimateUSD("image_gen", map[string]any{"n": float64(1)}, Pricing{}, 1); !errors.Is(err, ErrUnpriced) {
		t.Fatalf("expected ErrUnpriced for image_gen with no per_image, got %v", err)
	}
}

func TestEstimate_UnknownOperation(t *testing.T) {
	if _, err := testEstimator().EstimateUSD("teleport", map[string]any{}, textP(1, 1), 1); err == nil {
		t.Fatal("expected error for unknown operation")
	}
}

// ── rounding ────────────────────────────────────────────────────────────────

func TestRoundUpUSD_NeverFreeByRounding(t *testing.T) {
	// A sub-quantum positive cost must round UP to one NUMERIC(16,8) unit,
	// never down to $0.
	if got := roundUpUSD(1e-12); got != usdQuantum {
		t.Fatalf("sub-quantum cost: got %v want %v", got, usdQuantum)
	}
	if got := roundUpUSD(0); got != 0 {
		t.Fatalf("zero cost should stay 0, got %v", got)
	}
	// An exact multiple of the quantum is unchanged.
	if got := roundUpUSD(3 * usdQuantum); math.Abs(got-3*usdQuantum) > 1e-20 {
		t.Fatalf("exact-quantum cost: got %v", got)
	}
}

// ── chunk-count derivation ──────────────────────────────────────────────────

func TestEstimateNChunks(t *testing.T) {
	cases := []struct {
		name       string
		strategy   string
		size, toks int
		want       int
	}{
		{"none → 1", "none", 0, 10000, 1},
		{"empty → 1", "", 0, 10000, 1},
		{"zero input → 1", "tokens", 500, 0, 1},
		{"tokens exact", "tokens", 2000, 10000, 5},
		{"tokens ceil", "tokens", 2000, 10001, 6},
		{"tokens default size", "tokens", 0, 10000, 5},
		{"paragraphs proxy", "paragraphs", 8, 10000, 5},
		{"sentences proxy", "sentences", 30, 4001, 3},
		{"unknown strategy proxy", "magic", 0, 2000, 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := EstimateNChunks(tc.strategy, tc.size, tc.toks); got != tc.want {
				t.Fatalf("EstimateNChunks(%q,%d,%d): got %d want %d",
					tc.strategy, tc.size, tc.toks, got, tc.want)
			}
		})
	}
}

// ── script detection ────────────────────────────────────────────────────────

func TestEstimateInputTokens_ScriptDetection(t *testing.T) {
	// Mixed input above the 20% non-ASCII threshold falls to the CJK divisor.
	// 80 ASCII + 20 CJK = 100 chars, 20% non-ASCII → CJK divisor 1.0 → 100.
	if got := estimateInputTokens(100, 20); got != 100 {
		t.Fatalf("20%% non-ASCII should use CJK divisor: got %d want 100", got)
	}
	// Just below threshold → Latin divisor.
	if got := estimateInputTokens(100, 19); got != int(math.Ceil(100.0/3.5)) {
		t.Fatalf("19%% non-ASCII should use Latin divisor: got %d", got)
	}
	if got := estimateInputTokens(0, 0); got != 0 {
		t.Fatalf("empty input should be 0 tokens, got %d", got)
	}
}
