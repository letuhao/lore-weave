package meta

import (
	"fmt"

	"github.com/google/uuid"
)

// PromptAuditEntry is the input to the prompt-audit recorder. Note what is
// **deliberately absent**:
//
//   - NO `Body` / `PromptText` / `Assembled` field. The type cannot carry a
//     prompt body. Callers that need to audit a prompt must first hash it
//     and pass the hash, never the text.
//   - NO accessor on this struct that ever returns the original body.
//
// This is the type-level enforcement of the L1A §3.5 "body NEVER stored"
// invariant. The L1.K lint cycle adds the static guarantee that no
// production code path stuffs body bytes into a PromptAuditEntry field by
// accident. Until then, the struct shape itself is the gate.
type PromptAuditEntry struct {
	// PromptContextHash is the SHA-256 of the assembled prompt text. 32 bytes.
	// Persisted to prompt_audit.prompt_context_hash.
	PromptContextHash []byte

	// TemplateID + TemplateVersion identify the prompt template used.
	TemplateID      string
	TemplateVersion int

	// Intent enumerates the assembly purpose (e.g., "turn_resolution",
	// "npc_dialogue"). Free-text by design — the prompt assembler library
	// owns the canonical enum and validates against it before calling here.
	Intent string

	// Identity + scope
	ActorUserRefID uuid.UUID
	RealityID      uuid.UUID
	SessionID      *uuid.UUID // optional — nil for non-session prompts

	// EstimatedCostUSD is the assembly-time cost projection. The completion
	// ledger refines this when the LLM call returns; this is the assembler's
	// best estimate at audit time.
	EstimatedCostUSD float64

	// RejectedRefs lists context refs the assembler chose NOT to include
	// (capacity / consent / staleness). Each entry is {ref_id, reason}.
	// The JSONB column accepts arbitrary shape; library does not validate
	// (the assembler owns the schema).
	RejectedRefs []map[string]any
}

// Validate enforces the body-never-stored invariant at write time, plus the
// minimal shape rules the prompt_audit table enforces via CHECK constraints.
// Returns ErrBadIntent on any violation.
func (e PromptAuditEntry) Validate() error {
	if len(e.PromptContextHash) != 32 {
		return fmt.Errorf("%w: PromptContextHash must be SHA-256 (32 bytes), got %d",
			ErrBadIntent, len(e.PromptContextHash))
	}
	if e.TemplateID == "" {
		return fmt.Errorf("%w: TemplateID is empty", ErrBadIntent)
	}
	if e.TemplateVersion < 1 {
		return fmt.Errorf("%w: TemplateVersion must be >= 1, got %d",
			ErrBadIntent, e.TemplateVersion)
	}
	if e.Intent == "" {
		return fmt.Errorf("%w: Intent is empty", ErrBadIntent)
	}
	if e.ActorUserRefID == uuid.Nil {
		return fmt.Errorf("%w: ActorUserRefID is zero", ErrBadIntent)
	}
	if e.RealityID == uuid.Nil {
		return fmt.Errorf("%w: RealityID is zero", ErrBadIntent)
	}
	if e.EstimatedCostUSD < 0 {
		return fmt.Errorf("%w: EstimatedCostUSD is negative", ErrBadIntent)
	}
	return nil
}

// PromptAudit is the canonical recorder interface for the prompt-audit table.
// The interface signature deliberately omits anything resembling a "raw
// prompt body" parameter — only the post-hash envelope can flow through.
//
// Production implementation ships in cycle 21 (prompt stack); cycle 4 lands
// the interface + a test recorder so the prompt assembler library can adopt
// the dependency early without waiting on L4.
type PromptAudit interface {
	// RecordAssembly persists one assembled-prompt audit row. The entry
	// must already carry the hash — there is no API path for the raw text.
	RecordAssembly(entry PromptAuditEntry) error
}
