package prompt

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
)

// Composer assembles a PromptBundle from a PromptContext + user-supplied
// input slots. The Composer SKELETON ships in cycle 21; the per-template
// rendering logic ships in the LLM-logic sub-program (per Q-L6K-1 the
// foundation does not own template copy).
//
// # Q-L6H-1 (LOCKED 2026-05-29): FAIL not best-effort
//
// AssemblePrompt MUST return an error and NOT a partial bundle on:
//
//   - Unknown template_id / version (registry miss)
//   - Required section missing (template declares INSTRUCTION; caller
//     omits it)
//   - User input bytes routed to a non-INPUT section
//   - Token-budget overflow per S09 §12Y.7
//   - Safety hook denial (when a real safety policy lands; V1 hooks
//     no-op per Q-L6L-1)
//
// Best-effort rendering is **explicitly forbidden** per S09 §12Y —
// emitting a malformed prompt is worse than refusing the turn (the
// safer failure mode is observable + retryable; a malformed prompt
// poisons the LLM call without trace).
type Composer interface {
	// AssemblePrompt is the SINGLE entry point. Returns a validated
	// PromptBundle OR an error; never a partial bundle.
	AssemblePrompt(ctx context.Context, pc PromptContext, sections SectionMap) (PromptBundle, error)

	// ResolveContext is the pre-assembly capability + privacy filter
	// (S09 §12Y.5). V1 ships interface only — the foundation does NOT
	// own the policy chain; LLM-logic sub-program implements behavior.
	ResolveContext(ctx context.Context, pc PromptContext) (ResolvedContext, error)
}

// SectionMap binds rendered text to each section. The Composer enforces:
//
//   - Every template-declared section must have an entry (missing = error).
//   - User-controlled bytes may ONLY appear under SectionInput. The
//     Composer's sanitizer pre-checks input slot membership.
//
// Values are []byte (not string) so the Composer can scrub them
// in-place if a sanitizer policy demands.
type SectionMap map[Section][]byte

// ResolvedContext is the output of the pre-assembly filter chain
// (capability + privacy + severance + consent). V1 carries only the
// minimal shape — full filter chain lands in LLM-logic sub-program.
type ResolvedContext struct {
	// AllowedEvents — events that survived all filters.
	AllowedEvents []ContextRef

	// AllowedMemories — memories that survived all filters.
	AllowedMemories []ContextRef

	// RejectedRefs — IDs + reasons for items the filter chain dropped.
	// Persisted into prompt_audit.rejected_refs (NO CONTENT, IDs only).
	RejectedRefs []RejectionRecord
}

// ContextRef is an opaque ID + entity-type pair the LLM-logic
// sub-program dereferences to actual content. Foundation keeps this
// as a thin envelope.
type ContextRef struct {
	EntityType string // "event" | "memory" | "canon_fact"
	EntityID   string // UUID string
}

// RejectionRecord records ONE filter rejection — IDs + reasons ONLY.
// **No content field**: persisting rejected content would replay the
// privacy bug the filter just prevented.
type RejectionRecord struct {
	EntityType string // "event" | "memory" | "canon_fact"
	EntityID   string
	Reason     string // "outside_session_participants" | "privacy_confidential_not_originator" | "severed_by_ancestry" | …
	Filter     string // which filter rejected (e.g., "session_capability" | "privacy_level" | "consent_byok_no_telemetry")
}

// AssembleOutput is the internal shape the Composer fills before
// hashing + bundling. Exported so the LLM-logic sub-program can wire
// concrete renderers + still rely on the foundation Composer for the
// audit + hash + bundle steps.
type AssembleOutput struct {
	// Rendered carries the full rendered prompt text as the Composer
	// builds it. **Lives only inside the Composer call stack** — the
	// foundation public surface (PromptBundle) does NOT expose it.
	Rendered []byte

	// ProviderPayload — opaque bytes the registered ProviderEncoder
	// emitted. Per Q-L4D-1 V1: untyped JSON.
	ProviderPayload json.RawMessage

	// ProviderName + ModelRef pass through into the bundle.
	ProviderName string
	ModelRef     string

	// EstimatedCostUSD — string-form decimal.
	EstimatedCostUSD string
}

// ProviderEncoder is the boundary between the Composer's rendered
// text and a provider's wire shape. **Opaque per Q-L4D-1** — the
// foundation does NOT inspect or validate the bytes.
//
// Per CLAUDE.md "Provider gateway invariant" + Q-L4D-1: this is the
// only interface that may construct provider-shaped payloads. Service
// code MUST route through here (never call provider SDKs directly).
type ProviderEncoder interface {
	// Encode renders a section map + intent into the provider-specific
	// payload bytes (e.g., Anthropic Messages, OpenAI Chat Completions).
	Encode(ctx context.Context, pc PromptContext, rendered []byte) (json.RawMessage, error)

	// ProviderName returns the canonical provider name (opaque to the
	// foundation; the LLM-gateway adapter registry owns the namespace).
	ProviderName() string

	// ModelRef returns the resolved model identifier for this encoder.
	ModelRef() string
}

// ErrComposerFailed is the canonical error class returned by
// AssemblePrompt on any FAIL condition (Q-L6H-1). Wraps a specific
// inner cause via fmt.Errorf("%w: …", ErrComposerFailed, …).
var ErrComposerFailed = errors.New("prompt: composer failed")

// DefaultComposer is the foundation skeleton implementation.
//
// V1 scope:
//   - Validates PromptContext + SectionMap shape (FAIL on issues).
//   - Computes SHA-256 over the assembled section bytes (in canonical
//     section order) → ContextHash.
//   - Invokes ProviderEncoder to produce ProviderPayload.
//   - Invokes Safety + ConsentGate hooks (no-op V1 per Q-L6L-1).
//   - Writes one prompt_audit row via PromptAuditWriter.
//
// V1 does NOT:
//   - Load template strings (templates/ is empty per Q-L6K-1; callers
//     pass SectionMap directly).
//   - Implement ResolveContext policy chain (returns empty ResolvedContext).
//   - Enforce per-intent token budgets (interface present; threshold
//     check belongs to LLM-logic sub-program with real tokenizer).
type DefaultComposer struct {
	Encoder      ProviderEncoder
	Audit        PromptAuditWriter
	Safety       SafetyHooks
	Consent      ConsentGate
	TokenBudget  TokenBudgetGate
	NewAuditID   func() string // returns UUID string; tests override
	Now          func() int64  // returns unix nanos; tests override
}

// AssemblePrompt — see Composer interface comment for FAIL discipline
// (Q-L6H-1). This implementation NEVER returns a non-empty bundle
// together with an error; on any failure path it returns the zero
// bundle + a wrapped ErrComposerFailed.
func (c *DefaultComposer) AssemblePrompt(ctx context.Context, pc PromptContext, sections SectionMap) (PromptBundle, error) {
	if c == nil {
		return PromptBundle{}, fmt.Errorf("%w: nil Composer receiver", ErrComposerFailed)
	}
	if err := c.depsReady(); err != nil {
		return PromptBundle{}, err
	}
	if err := pc.Validate(); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: %v", ErrComposerFailed, err)
	}
	if err := validateSections(sections); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: %v", ErrComposerFailed, err)
	}

	// Safety hooks (no-op V1; Q-L6L-1). PreAssembly may reject by
	// returning an error → FAIL (don't best-effort).
	if err := c.Safety.PreAssembly(ctx, pc, sections); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: safety pre-assembly: %v", ErrComposerFailed, err)
	}
	if err := c.Consent.Check(ctx, pc); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: consent gate: %v", ErrComposerFailed, err)
	}

	// Render = concatenate sections in canonical order, each prefixed
	// with its section header. **This is the rendered text that NEVER
	// leaves the Composer call stack** (body-never-stored).
	rendered := renderInOrder(sections)

	if err := c.TokenBudget.Check(ctx, pc, rendered); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: token budget: %v", ErrComposerFailed, err)
	}

	// SHA-256 ContextHash.
	hash := sha256.Sum256(rendered)

	// Encode via provider boundary. **Q-L4D-1 opaque** — we do not
	// validate the returned bytes beyond non-empty + valid JSON (the
	// Validate() on PromptBundle handles the JSON probe).
	payload, err := c.Encoder.Encode(ctx, pc, rendered)
	if err != nil {
		return PromptBundle{}, fmt.Errorf("%w: provider encode: %v", ErrComposerFailed, err)
	}
	if len(payload) == 0 {
		return PromptBundle{}, fmt.Errorf("%w: provider encode returned empty payload", ErrComposerFailed)
	}

	// PostAssembly safety hook (canary token check, etc. — no-op V1).
	if err := c.Safety.PostAssembly(ctx, pc, hash, payload); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: safety post-assembly: %v", ErrComposerFailed, err)
	}

	auditID := c.NewAuditID()
	if auditID == "" {
		return PromptBundle{}, fmt.Errorf("%w: NewAuditID returned empty", ErrComposerFailed)
	}

	// Write the audit row (body-never-stored: only hash + meta).
	entry := PromptAuditEntry{
		AuditID:           auditID,
		PromptContextHash: hash[:],
		TemplateID:        pickTemplateID(pc),
		TemplateVersion:   pickTemplateVersion(pc),
		Intent:            string(pc.Intent),
		ActorUserRefID:    pc.ActorUserRefID.String(),
		RealityID:         pc.RealityID.String(),
		CreatedAtNanos:    c.Now(),
	}
	if pc.SessionID != nil {
		s := pc.SessionID.String()
		entry.SessionID = &s
	}
	if err := c.Audit.RecordAssembly(ctx, entry); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: audit write: %v", ErrComposerFailed, err)
	}

	bundle := PromptBundle{
		ProviderPayload:  payload,
		ContextHash:      hash,
		PromptAuditID:    mustParseUUID(auditID),
		EstimatedCostUSD: "0",
		TemplateID:       entry.TemplateID,
		TemplateVersion:  entry.TemplateVersion,
		ProviderName:     c.Encoder.ProviderName(),
		ModelRef:         c.Encoder.ModelRef(),
	}
	if err := bundle.Validate(); err != nil {
		return PromptBundle{}, fmt.Errorf("%w: bundle validate: %v", ErrComposerFailed, err)
	}
	return bundle, nil
}

// ResolveContext V1 returns an empty ResolvedContext + nil error. The
// policy chain (S2 capability, S3 privacy, severance, consent) lands
// in the LLM-logic sub-program. We ship the interface here so service
// code can adopt the dependency early.
func (c *DefaultComposer) ResolveContext(ctx context.Context, pc PromptContext) (ResolvedContext, error) {
	if c == nil {
		return ResolvedContext{}, fmt.Errorf("%w: nil Composer receiver", ErrComposerFailed)
	}
	if err := pc.Validate(); err != nil {
		return ResolvedContext{}, fmt.Errorf("%w: %v", ErrComposerFailed, err)
	}
	// V1 stub: empty allowed sets + no rejections. Policy chain owns
	// the real implementation.
	return ResolvedContext{}, nil
}

func (c *DefaultComposer) depsReady() error {
	if c.Encoder == nil {
		return fmt.Errorf("%w: Encoder dep missing", ErrComposerFailed)
	}
	if c.Audit == nil {
		return fmt.Errorf("%w: Audit dep missing", ErrComposerFailed)
	}
	if c.Safety == nil {
		c.Safety = NoopSafetyHooks{}
	}
	if c.Consent == nil {
		c.Consent = NoopConsentGate{}
	}
	if c.TokenBudget == nil {
		c.TokenBudget = NoopTokenBudgetGate{}
	}
	if c.NewAuditID == nil {
		return fmt.Errorf("%w: NewAuditID factory missing", ErrComposerFailed)
	}
	if c.Now == nil {
		return fmt.Errorf("%w: Now clock missing", ErrComposerFailed)
	}
	return nil
}

// validateSections enforces the template+input contract:
//   - At least one section provided.
//   - Every key is a valid Section enum value (Q-L6H-1: FAIL — do not
//     silently drop unknown sections).
//   - SectionInput need not be present (some intents have no user input,
//     e.g., world_seed). But if present, no other section may carry
//     user-tagged bytes (this is enforced by callers via the SectionMap
//     boundary — the foundation type cannot know which bytes are
//     "user" without a sanitizer policy. The LLM-logic sub-program
//     wires the sanitizer.)
func validateSections(m SectionMap) error {
	if len(m) == 0 {
		return errors.New("SectionMap is empty")
	}
	for sec := range m {
		if !sec.IsValid() {
			return fmt.Errorf("unknown section %q", sec)
		}
	}
	// SystemSection is mandatory for every intent V1 (§12Y.4 — SYSTEM
	// bytes are immutable per-intent and always present).
	if _, ok := m[SectionSystem]; !ok {
		return errors.New("SectionSystem missing — every prompt MUST carry SYSTEM bytes")
	}
	return nil
}

// renderInOrder concatenates the SectionMap in canonical section order,
// prefixing each with a header line. Empty sections render as a single
// header + blank line (preserves position for deterministic hashing).
func renderInOrder(m SectionMap) []byte {
	var out []byte
	for _, sec := range sectionOrder {
		header := append([]byte("\n["), sec...)
		header = append(header, []byte("]\n")...)
		out = append(out, header...)
		if v, ok := m[sec]; ok {
			out = append(out, v...)
		}
		out = append(out, '\n')
	}
	return out
}

func pickTemplateID(pc PromptContext) string {
	if pc.TemplateID != "" {
		return pc.TemplateID
	}
	return string(pc.Intent) // fallback: intent name as template id (skeleton convention)
}

func pickTemplateVersion(pc PromptContext) int {
	if pc.TemplateVersion >= 1 {
		return pc.TemplateVersion
	}
	return 1
}
