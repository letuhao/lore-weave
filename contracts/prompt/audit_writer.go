package prompt

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// PromptAuditEntry is the foundation-internal shape that the Composer
// hands to PromptAuditWriter for persistence. Mirrors cycle 4
// contracts/meta.PromptAuditEntry field-for-field so callers can wire
// straight through — but kept LOCAL to this package so contracts/prompt
// does not take a build-time dep on contracts/meta (eventgen-style
// boundary discipline).
//
// **Body-never-stored invariant** (S09 §12Y + L1.A §3.5):
//
//   - NO Body / PromptText / Rendered field on this struct.
//   - PromptContextHash is the SHA-256 of the rendered prompt; the
//     foundation Composer computes this and discards the body bytes
//     before returning from AssemblePrompt.
//   - Type-level shape is the gate; the L1.K body-never-stored lint
//     (cycle 23+) adds the static guarantee that no Go code path
//     stuffs body bytes into the Body-shaped field of any "audit"
//     struct (here OR in contracts/meta).
type PromptAuditEntry struct {
	// AuditID — UUID string (we keep as string here so the writer can
	// be tested without a uuid dep on every test file; the bundle field
	// parses it into uuid.UUID).
	AuditID string

	// PromptContextHash — SHA-256 of the assembled prompt. 32 bytes.
	PromptContextHash []byte

	// TemplateID + TemplateVersion identify the template that produced
	// the prompt.
	TemplateID      string
	TemplateVersion int

	// Intent — the 7-intent enum on the wire (snake_case string).
	Intent string

	// Identity + scope (UUID strings to keep the foundation surface
	// driver-agnostic).
	ActorUserRefID string
	RealityID      string
	SessionID      *string // optional; nil for non-session intents

	// EstimatedCostUSD — decimal-as-string to preserve precision.
	EstimatedCostUSD string

	// RejectedRefs — list of (entity_type, entity_id, reason) tuples
	// from the filter chain. Persisted as JSONB; NO content field.
	RejectedRefs []RejectionRecord

	// CreatedAtNanos — unix nanoseconds at audit-row creation. The
	// foundation Composer's Now() clock supplies this.
	CreatedAtNanos int64
}

// Validate enforces the minimal shape contract that the prompt_audit
// table CHECK constraints would otherwise enforce at INSERT time.
// Fail loudly here so the Composer surfaces a single ErrComposerFailed
// instead of an opaque sqlx error.
func (e PromptAuditEntry) Validate() error {
	if e.AuditID == "" {
		return errors.New("prompt: audit_id is empty")
	}
	if len(e.PromptContextHash) != 32 {
		return fmt.Errorf("prompt: prompt_context_hash must be 32 bytes (SHA-256); got %d", len(e.PromptContextHash))
	}
	if e.TemplateID == "" {
		return errors.New("prompt: template_id is empty")
	}
	if e.TemplateVersion < 1 {
		return fmt.Errorf("prompt: template_version must be >= 1; got %d", e.TemplateVersion)
	}
	if e.Intent == "" {
		return errors.New("prompt: intent is empty")
	}
	if e.ActorUserRefID == "" {
		return errors.New("prompt: actor_user_ref_id is empty")
	}
	if e.RealityID == "" {
		return errors.New("prompt: reality_id is empty")
	}
	if e.CreatedAtNanos <= 1577836800000000000 {
		// Mirrors meta CHECK constraint; rejects clock-skew zeros.
		return fmt.Errorf("prompt: created_at_nanos implausible: %d", e.CreatedAtNanos)
	}
	return nil
}

// PromptAuditWriter persists one PromptAuditEntry. Production wires
// this to contracts/meta.PromptAudit (cycle 4); tests use the
// in-memory recorder below.
type PromptAuditWriter interface {
	RecordAssembly(ctx context.Context, e PromptAuditEntry) error
}

// InMemoryAuditWriter records entries in-memory. Used by the
// foundation Composer tests; also useful as a reference impl for
// integration tests in downstream services.
type InMemoryAuditWriter struct {
	Entries []PromptAuditEntry
}

// RecordAssembly validates + appends.
func (w *InMemoryAuditWriter) RecordAssembly(_ context.Context, e PromptAuditEntry) error {
	if err := e.Validate(); err != nil {
		return err
	}
	w.Entries = append(w.Entries, e)
	return nil
}

// mustParseUUID parses a UUID string or returns uuid.Nil. Used by the
// Composer after it has already validated AuditID via the audit
// writer's Validate(); a parse failure here signals a Composer bug.
func mustParseUUID(s string) uuid.UUID {
	u, err := uuid.Parse(s)
	if err != nil {
		return uuid.Nil
	}
	return u
}
