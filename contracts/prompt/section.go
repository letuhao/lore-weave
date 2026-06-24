package prompt

import (
	"errors"
	"fmt"
)

// Section enumerates the 8 prompt sections from S09 §12Y.4.
//
// **Order is fixed.** Models are tuned against this exact sequence via
// L9 fixtures (S09 §12Y.4). Reordering is a model-regression risk + a
// wire-contract change.
//
// **User-authored content lives ONLY in SectionInput.** Injecting it
// into any other section is a code-review reject condition (S09 §12Y.4
// + ADMIN_ACTION_POLICY §4 amendment).
type Section string

const (
	// SectionSystem — immutable per-intent system instructions; role,
	// rules, canon hierarchy, injection-defense instructions.
	SectionSystem Section = "SYSTEM"

	// SectionWorldCanon — L1/L2 facts, filtered to actor-knowable; each
	// fact tagged with lock layer (R02 §12B).
	SectionWorldCanon Section = "WORLD_CANON"

	// SectionSessionState — session_participants sheet, turn order,
	// scene state.
	SectionSessionState Section = "SESSION_STATE"

	// SectionActorContext — actor's PC data (stats, inventory,
	// capabilities, known NPCs).
	SectionActorContext Section = "ACTOR_CONTEXT"

	// SectionMemory — retrieved npc_session_memory via L4 filter
	// (S2-compliant).
	SectionMemory Section = "MEMORY"

	// SectionHistory — recent events via L4 visibility filter
	// (S3-compliant).
	SectionHistory Section = "HISTORY"

	// SectionInstruction — current turn instruction (template-owned;
	// never user-editable, never string-concatenated with user input).
	SectionInstruction Section = "INSTRUCTION"

	// SectionInput — user-authored content. The ONLY section that may
	// carry user-controlled bytes. Sandboxed with <user_input>...</user_input>
	// delimiters by the Composer (S09 §12Y.6).
	SectionInput Section = "INPUT"
)

// SectionOrder is the canonical render order. **Do not reorder.**
// Returned as a slice so callers can range over it deterministically.
var sectionOrder = []Section{
	SectionSystem,
	SectionWorldCanon,
	SectionSessionState,
	SectionActorContext,
	SectionMemory,
	SectionHistory,
	SectionInstruction,
	SectionInput,
}

// AllSections returns the 8 sections in their canonical render order.
// Used by Composer to enforce the fixed sequence + by tests to assert
// the enum stays exhaustive.
func AllSections() []Section {
	out := make([]Section, len(sectionOrder))
	copy(out, sectionOrder)
	return out
}

// IsValid returns true iff s is one of the 8 enumerated sections.
func (s Section) IsValid() bool {
	for _, ok := range sectionOrder {
		if s == ok {
			return true
		}
	}
	return false
}

// IsUserSandbox reports whether this section is the user-authored
// sandbox. Only SectionInput returns true. Used by sanitizers to verify
// the user-content boundary at type level.
func (s Section) IsUserSandbox() bool { return s == SectionInput }

// ErrUnknownSection is returned by ParseSection on any unknown string.
var ErrUnknownSection = errors.New("prompt: unknown section")

// ParseSection parses the wire format. Section names are UPPERCASE on
// the wire (mirrors S09 §12Y.4 vocabulary).
func ParseSection(s string) (Section, error) {
	sec := Section(s)
	if !sec.IsValid() {
		return "", fmt.Errorf("%w: %q", ErrUnknownSection, s)
	}
	return sec, nil
}

// String returns the canonical wire form.
func (s Section) String() string { return string(s) }
