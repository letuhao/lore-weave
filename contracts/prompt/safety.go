package prompt

import (
	"context"
	"encoding/json"
)

// SafetyHooks is the multi-layer prompt-injection defense surface
// (S09 §12Y.6). The interface ships in cycle 21; real fail-closed
// behavior lands in the LLM-safety sub-program per Q-L6L-1 (LOCKED).
//
// # Q-L6L-1 (LOCKED): empty defaults V1, fail-closed in safety sub-program
//
// The DEFAULT implementation (NoopSafetyHooks) returns nil for every
// hook — V1 prompts pass through unchallenged. This is INTENTIONAL:
//   - Foundation cannot ship policy without first locking the canon
//     of attacks + benign-vs-malicious classification (governance work
//     that belongs to the LLM-safety sub-program).
//   - Shipping a half-baked policy that false-positives benign turns
//     is worse than a known no-op; ops can monitor the
//     `lw_prompt_safety_hook_invocations_total` metric to confirm the
//     hook fires once the real policy lands.
//
// The LLM-safety sub-program will swap NoopSafetyHooks for a concrete
// impl that:
//   - Pattern-scans SectionInput bytes for jailbreak phrases.
//   - Injects a canary token in SectionSystem; post-output scanner
//     PAGES SRE if the canary appears in the model response.
//   - Wraps SectionInput content in <user_input> delimiters with
//     XML-escaping (the foundation Composer does not inject the
//     delimiters; that is policy + LLM-tunable).
type SafetyHooks interface {
	// PreAssembly runs BEFORE the section render. Returning an error
	// causes Composer.AssemblePrompt to FAIL per Q-L6H-1 — no partial
	// bundle, no best-effort render.
	PreAssembly(ctx context.Context, pc PromptContext, sections SectionMap) error

	// PostAssembly runs AFTER the ProviderEncoder produced the payload
	// but BEFORE the audit row is written. Receives the SHA-256 hash
	// of the rendered prompt (NOT the body — body never leaves the
	// Composer call stack) so a real impl can index canary token
	// detections against the hash.
	PostAssembly(ctx context.Context, pc PromptContext, contextHash [32]byte, payload json.RawMessage) error
}

// NoopSafetyHooks is the V1 default per Q-L6L-1. Every hook returns
// nil (allow). Construction is intentionally zero-arg so test wiring
// stays one-liner.
type NoopSafetyHooks struct{}

// PreAssembly always allows V1. The LLM-safety sub-program supplies
// the real fail-closed impl.
func (NoopSafetyHooks) PreAssembly(_ context.Context, _ PromptContext, _ SectionMap) error {
	return nil
}

// PostAssembly always allows V1.
func (NoopSafetyHooks) PostAssembly(_ context.Context, _ PromptContext, _ [32]byte, _ json.RawMessage) error {
	return nil
}

// ConsentGate is the BYOK-telemetry / training-on-input consent check
// (S09 §12Y.5 layer 5). Returns an error to FAIL the assembly when
// the provider has training-on-input enabled AND the user has not
// granted telemetry consent.
//
// V1 ships interface + no-op default per Q-L6L-1. Real consent matrix
// lookup lands in cycle 3 user_consent_ledger consumer wiring.
type ConsentGate interface {
	// Check runs after PreAssembly but before render. Returns an error
	// to refuse the call (Composer wraps as ErrComposerFailed).
	Check(ctx context.Context, pc PromptContext) error
}

// NoopConsentGate allows every call. V1 default per Q-L6L-1.
type NoopConsentGate struct{}

// Check always allows V1.
func (NoopConsentGate) Check(_ context.Context, _ PromptContext) error { return nil }

// TokenBudgetGate enforces S09 §12Y.7 per-intent input cap (16K /
// 12K / 8K / 32K / 8K / 24K / 8K for the 7 intents). V1 ships
// interface only — concrete tokenizer integration (anthropic /
// openai BPE) lives in the LLM-logic sub-program because the choice
// of tokenizer is provider-specific.
type TokenBudgetGate interface {
	// Check receives the rendered prompt bytes (NOT exposed via any
	// public surface — only the foundation Composer holds these
	// transiently). Returns an error to FAIL the assembly when the
	// rendered prompt exceeds the per-intent cap.
	Check(ctx context.Context, pc PromptContext, rendered []byte) error
}

// NoopTokenBudgetGate accepts any size. V1 default per Q-L6L-1
// (no real tokenizer in the foundation; LLM-logic owns it).
type NoopTokenBudgetGate struct{}

// Check always allows V1.
func (NoopTokenBudgetGate) Check(_ context.Context, _ PromptContext, _ []byte) error { return nil }
