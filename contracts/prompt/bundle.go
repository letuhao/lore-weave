package prompt

import (
	"encoding/json"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// PromptBundle is the AssemblePrompt return type — what the caller hands
// to its registered provider adapter.
//
// **Body-never-stored discipline:** there is NO Body / Rendered /
// PromptText field. The rendered prompt exists only inside the
// Composer's execution scope; what crosses the boundary is the opaque
// ProviderPayload (already-redacted, provider-shaped bytes) plus the
// ContextHash for incident replay. Forensics reconstruct the prompt
// via (hash + template + version + deterministic context retrieval)
// per S09 §12Y.
type PromptBundle struct {
	// ProviderPayload — OPAQUE bytes destined for the provider adapter.
	// Per Q-L4D-1 V1: untyped json.RawMessage (cross-provider diversity).
	// V2+ may introduce a typed enum per provider. The Composer's
	// ProviderEncoder shaped this for a specific provider; callers MUST
	// route to the matching adapter (no cross-provider re-shaping).
	ProviderPayload json.RawMessage

	// ContextHash — SHA-256 of the rendered prompt text. 32 bytes.
	// Replaces the body for incident replay; lets ops confirm two
	// reports point at the same exact assembly without persisting text.
	// Wire format = raw bytes (NOT hex) to match prompt_audit column.
	ContextHash [32]byte

	// PromptAuditID — the audit_id of the prompt_audit row written by
	// AssemblePrompt. Callers chain this into downstream audit trails
	// (e.g., turn_outcomes.audit_ref_id).
	PromptAuditID uuid.UUID

	// EstimatedCostUSD — assembly-time cost projection (refined by the
	// completion ledger after the LLM call returns). Stored as a string
	// to preserve decimal precision through JSON without floats.
	EstimatedCostUSD string

	// TemplateID + TemplateVersion — pin the exact template that
	// produced the bundle. Required for replay.
	TemplateID      string
	TemplateVersion int

	// ProviderName — opaque caller hint (e.g., "anthropic", "openai",
	// "byok_local"). Foundation does NOT validate; the LLM-gateway
	// adapter registry owns the canonical names.
	ProviderName string

	// ModelRef — opaque model identifier. Foundation does NOT resolve
	// concrete model names (CLAUDE.md "No hardcoded model names"); the
	// caller's provider-registry config supplies this.
	ModelRef string
}

// Validate enforces the body-never-stored invariant + minimal shape.
// Returns an error if the bundle is unsafe to forward to a provider.
func (b PromptBundle) Validate() error {
	if len(b.ProviderPayload) == 0 {
		return errors.New("prompt: ProviderPayload empty")
	}
	// Quickly verify the payload is at least syntactic JSON. We do NOT
	// validate the payload's shape — that's the provider adapter's job.
	var probe any
	if err := json.Unmarshal(b.ProviderPayload, &probe); err != nil {
		return fmt.Errorf("prompt: ProviderPayload not valid JSON: %w", err)
	}
	if b.ContextHash == ([32]byte{}) {
		return errors.New("prompt: ContextHash is zero")
	}
	if b.PromptAuditID == uuid.Nil {
		return errors.New("prompt: PromptAuditID is zero")
	}
	if b.TemplateID == "" {
		return errors.New("prompt: TemplateID is empty")
	}
	if b.TemplateVersion < 1 {
		return fmt.Errorf("prompt: TemplateVersion must be >= 1, got %d", b.TemplateVersion)
	}
	return nil
}
