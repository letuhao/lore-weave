// Package billing holds the Phase 6a Subsystem A spend-guardrail logic that
// lives on the gateway (provider-registry) side: the pre-flight cost
// estimator, the default price table, and the HTTP client to usage-billing.
//
// See docs/03_planning/LLM_PIPELINE_PHASE6A_DESIGN.md §3.2–§3.5.
package billing

import (
	"errors"
	"fmt"
	"math"
)

// ErrUnpriced is returned by EstimateUSD when the model's pricing JSONB lacks
// a dimension the requested operation needs. The model exists but cannot be
// priced — the caller maps this to a fail-closed 402 ("model pricing not
// configured"). It is NOT the same as a missing model (a 404 — handled by the
// caller, not here; see design §3.5 MED#7).
var ErrUnpriced = errors.New("model pricing not configured")

// Pricing is a model's per-dimension cost table, decoded from the `pricing`
// JSONB column. Every field is a POINTER on purpose:
//
//   - nil   → the dimension is ABSENT → unpriced → fail closed (402).
//   - non-nil 0 → an explicit, priced, genuinely-free dimension (a local
//     model registered at $0); it passes the gate and contributes $0.
//
// A plain float64 cannot distinguish "absent" from "explicitly zero", and the
// design forbids treating absent as 0 (design §3.2).
type Pricing struct {
	InputPerMTok  *float64 `json:"input_per_mtok,omitempty"`
	OutputPerMTok *float64 `json:"output_per_mtok,omitempty"`
	PerImage      *float64 `json:"per_image,omitempty"`
	PerSecond     *float64 `json:"per_second,omitempty"`
	PerKChar      *float64 `json:"per_kchar,omitempty"`
}

// Estimator computes a worst-case USD upper bound for a job. The three int
// fields are token-estimation tuning knobs sourced from provider-registry
// config (design §3.6).
type Estimator struct {
	MaxOutputTokensDefault    int // chat/completion output ceiling when max_tokens omitted
	ExtractionOutputCeiling   int // per-op output estimate for extraction ops
	SystemPromptTokenEstimate int // per-chunk system-prompt re-send overhead
}

const (
	// Script-aware token divisors. LoreWeave is a multilingual novel
	// platform; chars/4 is the *English average* and would under-estimate a
	// CJK chapter ~4× (/review-impl HIGH#1). Both divisors must sit at or
	// BELOW the real chars-per-token ratio for their script, so dividing by
	// them OVER-estimates the token count — the safe direction for a bound.
	//
	// CJK/Thai/Devanagari tokenize at ~1 token per character, so the divisor
	// is exactly 1.0 (the design's original 1.1 was an arithmetic slip:
	// chars/1.1 ≈ 0.91·chars UNDER-bounds a 1-token-per-char script — a
	// guardrail bug, corrected here with the user during BUILD).
	cjkDivisor   = 1.0 // CJK / Thai / Devanagari: ~1 token per char
	latinDivisor = 3.5 // ASCII / Latin scripts (~4 chars per token)

	// A job whose non-ASCII rune share is at or above this fraction is
	// treated as CJK-heavy. Low on purpose: "when in doubt, fall to the CJK
	// divisor — over-estimating is safe" (design §3.3).
	nonASCIIShareThreshold = 0.2

	// translationOutputRatio — translation output scales with input and
	// carries no request max_tokens; a flat ceiling would under-bound a
	// chapter-sized job (/review-impl MED#4).
	translationOutputRatio = 1.5

	// usdQuantum is the last representable unit of NUMERIC(16,8). Every
	// estimate rounds UP to this so no job is ever free-by-rounding.
	usdQuantum = 1e-8

	// UsdQuantum exports usdQuantum for callers that need to reason about
	// the post-rounding cost cliff — e.g. `affordableMaxTokens` reserves
	// one quantum of price headroom so a re-estimate's `roundUpUSD` can't
	// push the capped cost back over budget (D-PHASE6A-CAP-ROUNDUP).
	UsdQuantum = usdQuantum

	// sttFallbackChars — conservative flat char-equivalent for a speech job
	// whose input carries no `audio_chars` hint (design §3.3 "flat fallback
	// if unknown"). The multipart submit path should pass `audio_chars`
	// computed from the real audio for an accurate bound.
	sttFallbackChars = 60000

	// chunkSizeTokensDefault mirrors chunker.DefaultTokensSize — the chunk
	// size assumed when a "tokens" strategy omits an explicit size, and the
	// proxy chunk size for the paragraphs/sentences strategies (whose unit
	// isn't tokens, so an exact count needs the real text structure).
	chunkSizeTokensDefault = 2000

	// videoMaxDurationSeconds mirrors the 60s ceiling in
	// api.validateVideoGenInput — the upper bound used to estimate a
	// video_gen job that omits an explicit duration.
	videoMaxDurationSeconds = 60

	// visionImageTokenCeiling — PDF-import vision op (docs/specs/2026-07-06-
	// pdf-book-import.md L5). A conservative flat per-image input-token
	// ceiling for a single-image vision-caption call, covering high-detail
	// tiling across common OpenAI-compatible vision models (~765-1105
	// tokens/image in practice). Deliberately NOT derived from the
	// base64 image byte count: walkText's generic char-count approach
	// would treat the entire base64 payload as "text" and inflate the
	// estimate by orders of magnitude (a 200KB image ≈ 266K b64 chars →
	// tens of thousands of phantom tokens) — over-estimating is normally
	// the safe direction (see walkText's doc comment), but at this
	// magnitude it would make ordinary vision calls look artificially
	// expensive enough to spuriously blow a legitimate spend cap. A flat,
	// named ceiling keeps the estimate realistic while still erring high.
	visionImageTokenCeiling = 1500
)

// EstimateUSD returns a worst-case USD upper bound for one job. "Upper bound"
// is load-bearing: an estimate that can sit below the real cost is not a
// guardrail. Returns ErrUnpriced when a required pricing dimension is absent.
func (e Estimator) EstimateUSD(operation string, input map[string]any, pricing Pricing, nchunks int) (float64, error) {
	if nchunks < 1 {
		nchunks = 1
	}
	switch operation {
	case "chat", "completion":
		ti := e.InputTokens(input, nchunks)
		// A chunked chat/completion job runs nchunks separate provider
		// calls, each able to emit up to max_tokens — so the output bound
		// scales with nchunks (/review-impl MED#2). A non-chunked job has
		// nchunks=1, so this is a no-op for the common case.
		return textCost(ti, e.chatOutputTokens(input)*nchunks, pricing)
	case "translation":
		ti := e.InputTokens(input, nchunks)
		to := int(math.Ceil(float64(ti) * translationOutputRatio))
		return textCost(ti, to, pricing)
	case "entity_extraction", "relation_extraction", "event_extraction", "fact_extraction":
		ti := e.InputTokens(input, nchunks)
		return textCost(ti, e.ExtractionOutputCeiling, pricing)
	case "summarize_level":
		// P3 hierarchical reduce — single-shot chat-shaped call returning
		// a short JSON summary (LevelSummary; ~150 tokens worst-case per
		// the prompt + 2000-char Pydantic ceiling on summary_text). Reuse
		// the extraction output ceiling for the cap.
		ti := e.InputTokens(input, nchunks)
		return textCost(ti, e.ExtractionOutputCeiling, pricing)
	case "embedding":
		return embeddingCost(e.InputTokens(input, nchunks), pricing)
	case "image_gen":
		n := getInt(input, "n", 1)
		if n < 1 {
			n = 1
		}
		return perUnitCost(float64(n), pricing.PerImage)
	case "video_gen":
		// The job input field is `duration` (see api.validateVideoGenInput,
		// which also caps it at videoMaxDurationSeconds). An omitted/zero
		// duration means "upstream default" — estimate at the validator
		// maximum so the bound holds for any accepted video job.
		dur := getFloat(input, "duration", 0)
		if dur <= 0 {
			dur = videoMaxDurationSeconds
		}
		return perUnitCost(dur, pricing.PerSecond)
	case "tts", "audio_gen":
		chars, _ := walkText(input)
		return perUnitCost(float64(chars)/1000.0, pricing.PerKChar)
	case "stt":
		chars := getInt(input, "audio_chars", sttFallbackChars)
		return perUnitCost(float64(chars)/1000.0, pricing.PerKChar)
	case "vision":
		// PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md L5).
		// Deliberately does NOT call e.InputTokens/walkText on the whole
		// input map — that would walk into image_b64 and treat the raw
		// base64 image bytes as "text", wildly over-counting (see
		// visionImageTokenCeiling's doc comment). Only the prompt string
		// is char-counted; the image contributes a flat, conservative
		// per-image ceiling instead.
		promptChars, promptNonASCII := 0, 0
		if p, ok := input["prompt"].(string); ok {
			promptChars, promptNonASCII = CountScriptChars(p)
		}
		ti := estimateInputTokens(promptChars, promptNonASCII) + visionImageTokenCeiling
		return textCost(ti, e.chatOutputTokens(input), pricing)
	default:
		return 0, fmt.Errorf("estimate: unknown operation %q", operation)
	}
}

// InputTokens returns the worst-case input-token count for a text job: the
// script-aware token estimate of every string in `input`, plus the per-chunk
// system-prompt overhead for a chunked job. Exported so the doSubmitJob
// max_tokens cap can reuse the same count (design §3.5 step 3).
func (e Estimator) InputTokens(input map[string]any, nchunks int) int {
	chars, nonASCII := walkText(input)
	ti := estimateInputTokens(chars, nonASCII)
	// A chunked extraction/translation job re-sends the system prompt +
	// context on every chunk; charge (nchunks-1) extra copies (design §3.3).
	if nchunks > 1 {
		ti += (nchunks - 1) * e.SystemPromptTokenEstimate
	}
	return ti
}

// EstimateNChunks derives a worst-case chunk count from a job's chunk config,
// used to size the per-chunk system-prompt overhead in InputTokens. Running
// the real chunker pre-flight would duplicate worker logic, so this estimates
// from the config alone — and over-estimating the count only over-estimates
// cost, the safe direction for a guardrail.
//
//   - empty / "none" strategy → 1 (unchunked).
//   - "tokens" → ceil(inputTokens / stride), where stride = size - overlap
//     (the chunker re-overlaps `overlap` tokens at the start of every chunk
//     after the first, so the effective advance per chunk is the stride; a
//     positive overlap means MORE chunks than ceil(tokens/size) and a slightly
//     larger system-prompt overhead total — D-PHASE6A-NCHUNKS-OVERLAP).
//   - "paragraphs" / "sentences" / anything else → ceil(inputTokens /
//     chunkSizeTokensDefault), a coarse proxy (the strategy's unit is not
//     tokens; this assumes a ~2000-token chunk). overlap is irrelevant for
//     non-token strategies (semantic units are not re-overlapped).
//
// `overlap` is silently clamped to [0, size-1]; an overlap >= size would
// produce a non-positive stride (the chunker itself rejects this at runtime,
// but the estimator must never divide by zero).
func EstimateNChunks(strategy string, size, overlap, inputTokens int) int {
	if inputTokens <= 0 {
		return 1
	}
	switch strategy {
	case "", "none":
		return 1
	case "tokens":
		if size <= 0 {
			size = chunkSizeTokensDefault
		}
		if overlap < 0 {
			overlap = 0
		}
		if overlap >= size {
			// Defensive: a malformed config would otherwise divide by zero
			// or negative. Treat as no-overlap so we still produce a
			// finite (and over-estimated, hence guardrail-safe) count.
			overlap = 0
		}
		stride := size - overlap
		return ceilDiv(inputTokens, stride)
	default:
		return ceilDiv(inputTokens, chunkSizeTokensDefault)
	}
}

// ceilDiv returns ceil(a/b) for positive ints, never below 1.
func ceilDiv(a, b int) int {
	if b <= 0 {
		return 1
	}
	n := (a + b - 1) / b
	if n < 1 {
		return 1
	}
	return n
}

// chatOutputTokens resolves the output-token ceiling for a chat/completion
// job: the request's max_tokens when present and positive, else the config
// default.
func (e Estimator) chatOutputTokens(input map[string]any) int {
	if mt := getInt(input, "max_tokens", 0); mt > 0 {
		return mt
	}
	return e.MaxOutputTokensDefault
}

// textCost prices a job with both an input and an output token dimension.
func textCost(tokIn, tokOut int, p Pricing) (float64, error) {
	if p.InputPerMTok == nil || p.OutputPerMTok == nil {
		return 0, ErrUnpriced
	}
	usd := float64(tokIn)/1e6*(*p.InputPerMTok) + float64(tokOut)/1e6*(*p.OutputPerMTok)
	return roundUpUSD(usd), nil
}

// embeddingCost prices an input-only job.
func embeddingCost(tokIn int, p Pricing) (float64, error) {
	if p.InputPerMTok == nil {
		return 0, ErrUnpriced
	}
	return roundUpUSD(float64(tokIn) / 1e6 * (*p.InputPerMTok)), nil
}

// PriceText prices an EXPLICIT input/output token pair — the S5a estimate path,
// where the caller (campaign-service) supplies a token heuristic derived from
// chapter sizes rather than the raw job text. Same pricing + ErrUnpriced +
// round-up semantics as the live textCost guardrail path, so an estimate and the
// real reconcile can never disagree on the pricing math.
func PriceText(inputTokens, outputTokens int, p Pricing) (float64, error) {
	return textCost(inputTokens, outputTokens, p)
}

// PriceEmbedding prices an explicit input-only token count (the S5a estimate
// path for the embedding stage). Mirrors PriceText.
func PriceEmbedding(inputTokens int, p Pricing) (float64, error) {
	return embeddingCost(inputTokens, p)
}

// PriceSTT prices a REAL-TIME voice speech-to-text invocation by AUDIO DURATION (C6 / SD-C6). The
// model's rate is `per_second` (a per-minute rate is per_second×60; pricing the seconds directly is
// equivalent), so the billing math lives with the model in provider-registry — never hardcoded in a
// consumer. A model with no per_second rate is ErrUnpriced (fail closed) — the price-voice endpoint
// surfaces that as status='unpriced' and the chat caller WARNS (a paid model billing $0 is observable,
// not silent). A $0 local model (Whisper) carries an explicit per_second=0 → priced, cost 0.
//
// NOTE (cold-review HIGH-1): the async STT-JOB estimate path (EstimateUSD case "stt") prices by
// per_kchar(audio_chars) — a pre-flight PROXY for a different operation. Voice STT (accurate duration
// meter) uses per_second. A model intended for VOICE must carry per_second. Unifying the two STT
// metering conventions is tracked as D-STT-METER-UNIFY.
func PriceSTT(audioSeconds float64, p Pricing) (float64, error) {
	return perUnitCost(audioSeconds, p.PerSecond)
}

// PriceTTS prices a text-to-speech invocation by CHARACTER count (C6 / SD-C6). The model's rate is
// `per_kchar` (per 1000 characters). Mirrors the estimate path's tts/audio_gen op so an estimate and the
// real charge never disagree. Unpriced ⇒ fail closed (a local Kokoro carries per_kchar=0).
func PriceTTS(chars int, p Pricing) (float64, error) {
	if chars < 0 {
		chars = 0
	}
	return perUnitCost(float64(chars)/1000.0, p.PerKChar)
}

// perUnitCost prices a job with a single per-unit dimension (per_image,
// per_second, per_kchar). A nil rate is unpriced → fail closed.
func perUnitCost(units float64, rate *float64) (float64, error) {
	if rate == nil {
		return 0, ErrUnpriced
	}
	if units < 0 {
		units = 0
	}
	return roundUpUSD(units * (*rate)), nil
}

// EstimateTokens is the exported, script-aware char→token estimate. Used by
// the input estimator (below) and by the streaming guardrail's running
// output tally (Phase 6a-δ) so streamed CJK output is not under-counted.
func EstimateTokens(chars, nonASCII int) int {
	return estimateInputTokens(chars, nonASCII)
}

// CountScriptChars returns the rune count and the non-ASCII rune count of s —
// the two inputs EstimateTokens needs. Exported for the streaming tally.
func CountScriptChars(s string) (chars, nonASCII int) {
	for _, r := range s {
		chars++
		if r > 127 {
			nonASCII++
		}
	}
	return chars, nonASCII
}

// estimateInputTokens converts a char count to a worst-case token count using
// the script-aware divisor (design §3.3).
func estimateInputTokens(chars, nonASCII int) int {
	if chars <= 0 {
		return 0
	}
	divisor := latinDivisor
	if float64(nonASCII)/float64(chars) >= nonASCIIShareThreshold {
		divisor = cjkDivisor
	}
	return int(math.Ceil(float64(chars) / divisor))
}

// walkText recursively sums the rune count (chars) and the non-ASCII rune
// count (nonASCII) of every string value reachable in v. Counting *every*
// string — including role labels and field values — only ever over-counts,
// which is the safe direction for an upper bound, and keeps the estimator
// resilient to per-operation input-schema drift.
func walkText(v any) (chars, nonASCII int) {
	switch t := v.(type) {
	case string:
		return CountScriptChars(t)
	case []any:
		for _, e := range t {
			c, n := walkText(e)
			chars += c
			nonASCII += n
		}
	case map[string]any:
		for _, e := range t {
			c, n := walkText(e)
			chars += c
			nonASCII += n
		}
	}
	return chars, nonASCII
}

// Validate rejects a Pricing with any negative dimension. A negative price
// would make EstimateUSD floor the cost to $0 via roundUpUSD, silently
// disabling the spend guardrail for that model (/review-impl MED#3).
func (p Pricing) Validate() error {
	for _, d := range []struct {
		name string
		v    *float64
	}{
		{"input_per_mtok", p.InputPerMTok},
		{"output_per_mtok", p.OutputPerMTok},
		{"per_image", p.PerImage},
		{"per_second", p.PerSecond},
		{"per_kchar", p.PerKChar},
	} {
		if d.v != nil && *d.v < 0 {
			return fmt.Errorf("pricing.%s must be >= 0", d.name)
		}
	}
	return nil
}

// roundUpUSD rounds up to the last NUMERIC(16,8) unit so no job is ever
// free-by-rounding (design §3.3).
//
// The `- noiseEpsilon` before Ceil absorbs floating-point division error: a
// value a few parts-per-million of a quantum below an integer (e.g. v/quantum
// = 20500.0000004 from float arithmetic) is that integer, not a reason to
// bump up a whole extra quantum. A genuine fraction of a quantum still rounds
// up — noiseEpsilon (1e-6 quanta) is far below any representable cost.
func roundUpUSD(v float64) float64 {
	if v <= 0 {
		return 0
	}
	const noiseEpsilon = 1e-6
	return math.Ceil(v/usdQuantum-noiseEpsilon) * usdQuantum
}

// getInt reads a JSON-decoded numeric field (float64 in a map[string]any) as
// an int, falling back to def when absent or not numeric.
func getInt(m map[string]any, key string, def int) int {
	switch n := m[key].(type) {
	case float64:
		return int(n)
	case int:
		return n
	default:
		return def
	}
}

// getFloat reads a JSON-decoded numeric field as a float64.
func getFloat(m map[string]any, key string, def float64) float64 {
	switch n := m[key].(type) {
	case float64:
		return n
	case int:
		return float64(n)
	default:
		return def
	}
}
