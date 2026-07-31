// Package llmbudget is glossary-service's call-profile registry — one row per kind of LLM
// call it makes, mirroring composition-service's `app/llm_budget.py` and translation's
// `app/llm_budget.py`. The SDK owns the mechanism; the per-operation facts live with the
// service that knows them.
//
// # What was wrong
//
// Both of glossary's LLM call sites (`runDocExtractor`, `runPlanner`) built a
// `llm.StreamRequest` with NO MaxTokens and never looked at `res.FinishReason` — a field the
// Go SDK populates from the terminal `done` event and both sites discarded.
//
// No cap is a legitimate choice (see `OutputKind.MIRROR`: for a translation the model's
// natural stop IS the bound). It is NOT legitimate here, and the difference is the whole
// point of the kind vocabulary: both of these calls parse JSON. A clipped JSON object does
// not come back short, it comes back UNPARSEABLE — `truncation_is_fatal` in
// contracts/llm-budget.contract.json.
//
// # Why the repair round made it worse
//
// On a parse failure each site runs ONE repair round that re-prompts with
//
//	"Your previous output was invalid: <parse error>"
//
// If the real cause was truncation, that sentence is a lie the model cannot recover from: it
// is told it produced malformed syntax when it actually produced correct syntax that got cut
// off, so it "fixes" grammar it never got wrong — against the same absent budget. The
// likeliest way for a model to satisfy both the complaint and the limit is to emit a SHORTER
// list. That parses cleanly, reports success, and silently drops entities.
//
// So a truncation must be named as a truncation, never fed to the repair round.
package llmbudget

import "fmt"

// TruncatedFinishReason is the wire value provider-registry reports when the model stopped
// because it hit the cap. Pinned against contracts/llm-budget.contract.json by the test in
// this package.
const TruncatedFinishReason = "length"

// Profile is one row: what the call may produce, and what a clip costs.
type Profile struct {
	// MaxTokens is the output cap. 0 would mean "omit — let the model decide", which is the
	// platform-wide sentinel; no row here uses it, because every glossary LLM call parses
	// JSON and an uncapped structured call is precisely the failure documented above.
	MaxTokens int
	// TruncationIsFatal ⇒ a `finish_reason == "length"` DESTROYS the result rather than
	// shortening it, so the caller must treat it as an error and must not "repair" it.
	TruncationIsFatal bool
	Why               string
}

// TokensPerItem is the worst-case JSON cost of ONE emitted row — a kind, a name, up to a
// dozen attribute key/value pairs, a scope label and punctuation. Taken from the Python
// SDK's `_TOKENS_PER_ITEM` so the three registries size the same shape the same way.
const TokensPerItem = 220

// Profiles is the registry, keyed by the function the call lives in.
//
// A cap does NOT prevent a clip; a cap BELOW the legitimate output causes one. Both of these
// calls were previously uncapped, so any fixed number here can only introduce a failure that
// did not exist — which is why the row for a caller-sized output is the omit sentinel and the
// row for a bounded one is derived from that bound.
var Profiles = map[string]Profile{
	// The caller passes `maxCandidates` (up to maxDocExtractCandidates = 200). At
	// TokensPerItem that is ~44k, so ANY flat cap that fits a small model truncates a large
	// document — the first version of this row used 4096, roughly 18 candidates against a
	// declared maximum of 200, on a call that had no cap at all before. The output length
	// here is dictated by the request, exactly like a translation's is dictated by its
	// source, so the model's natural stop is the right bound and `Truncated()` is the guard.
	"doc_extract": {
		MaxTokens:         omitSentinel,
		TruncationIsFatal: true,
		Why: "size is caller-driven (maxCandidates ≤ 200 ≈ 44k tokens) — a flat cap can only " +
			"clip a large doc; the finish_reason check is the guard",
	},
	"doc_extract_repair": {
		MaxTokens:         omitSentinel,
		TruncationIsFatal: true,
		Why:               "the repair re-emits the SAME object, so it inherits the same reasoning",
	},
	// A plan is BOUNDED — loreweave_mcp.MaxPlanOps = 50, enforced at the planner ("over the
	// cap is an error at the planner, never a silent truncation"). So the budget is knowable:
	// 50 × TokensPerItem = 11k. 12000 is the number plan-forge already runs against real
	// models in this repo, and it is ≥ the bound, so no valid plan can hit it.
	"action_plan": {
		MaxTokens:         12000,
		TruncationIsFatal: true,
		Why:               "a validated plan is bounded by MaxPlanOps=50 (~11k tokens); 12000 clears it",
	},
	"action_plan_repair": {
		MaxTokens:         12000,
		TruncationIsFatal: true,
		Why:               "the repair re-emits the SAME object, so it needs the same room",
	},
}

// omitSentinel — 0 means "no cap; drop the field from the wire", the platform-wide
// convention (contracts/llm-budget.contract.json; the Go SDK's `,omitempty` implements it).
const omitSentinel = 0

// For returns the row for code. Unknown codes panic rather than defaulting: a silent
// fallback would re-create the unattributed budget this registry exists to remove, and the
// codes are compile-time constants at their call sites, so a bad one is a programming error
// caught by the package's own test — never a runtime surprise on a user's request.
func For(code string) Profile {
	p, ok := Profiles[code]
	if !ok {
		panic(fmt.Sprintf("unknown glossary call profile %q — add a row to llmbudget.Profiles "+
			"rather than passing a literal at the call site", code))
	}
	return p
}

// MaxTokensFor is the value to put on the wire for code.
func MaxTokensFor(code string) int { return For(code).MaxTokens }

// Truncated reports whether the model stopped because it ran out of budget.
func Truncated(finishReason string) bool { return finishReason == TruncatedFinishReason }

// TruncationError describes a clip in the terms a caller (and the agent reading the tool
// error) can act on. Deliberately NOT phrased as a malformed-output error: that
// misattribution is the bug this package exists to prevent.
//
// The limit is reported as the PROVIDER's when this row sends no cap of its own — otherwise
// the message would name 0 and read as nonsense. An uncapped call that still clipped was
// bounded by the provider (Anthropic substitutes 8192 for a missing cap) or by the context
// window, and the actionable advice differs.
func TruncationError(code string, outputTokens int) error {
	limit := MaxTokensFor(code)
	where := fmt.Sprintf("its output limit of %d tokens", limit)
	advice := fmt.Sprintf("raise the %q budget in internal/llmbudget", code)
	if limit == omitSentinel {
		where = "the PROVIDER's own output limit (this call sends no cap of its own — " +
			"Anthropic substitutes 8192 for a missing one)"
		advice = "use a model with a larger output window"
	}
	return fmt.Errorf(
		"the model's response was cut off at %s (finish_reason=%q) after %d tokens, so the "+
			"JSON is incomplete — this is a capacity limit, not a malformed answer. Retry "+
			"with a smaller input (fewer/shorter passages), or %s",
		where, TruncatedFinishReason, outputTokens, advice)
}
