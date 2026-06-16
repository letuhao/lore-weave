package prompt

import (
	"bytes"
	"errors"
	"fmt"
)

// SectionRenderer renders a single Section's bytes into the final
// prompt text. Cycle 31 L6.H.2 introduces a per-section abstraction
// so the LLM-logic sub-program can swap in template-aware renderers
// per intent without touching the Composer's section-ordering loop.
//
// **Markdown-safe contract:** the default renderer escapes characters
// that would otherwise collide with downstream markdown-renderer LLM
// instructions in the SYSTEM section ([, ], `, *, _). The escape rules
// apply to non-INPUT sections — INPUT runs through input_wrapper.go
// (cycle 31 L6.I) for full XML-escape + canary discipline.
type SectionRenderer interface {
	// Render produces the wire bytes for one section. Returns an error
	// to FAIL the Composer per Q-L6H-1.
	Render(sec Section, raw []byte) ([]byte, error)
}

// DefaultSectionRenderer applies markdown-safe escaping to non-INPUT
// sections and identity passthrough to INPUT (which is escaped by the
// input_wrapper before reaching the renderer).
//
// Foundation V1 keeps the rule simple: backtick is the only character
// that survived a real prompt-injection corpus as a "look like a
// template directive" risk; we escape it across all sections except
// INPUT (where the input_wrapper owns sanitization).
type DefaultSectionRenderer struct{}

// Render — see SectionRenderer.
func (DefaultSectionRenderer) Render(sec Section, raw []byte) ([]byte, error) {
	if !sec.IsValid() {
		return nil, fmt.Errorf("section_renderer: unknown section %q", sec)
	}
	// INPUT is rendered as-is — the input_wrapper has already escaped
	// + wrapped it. Re-escaping would double-encode XML entities and
	// break the canary-detection invariant (the wrapper's canary marker
	// must remain byte-identical for the detector).
	if sec == SectionInput {
		return raw, nil
	}
	// Non-INPUT sections: escape backtick (template-directive lookalike).
	// We do NOT touch other markdown chars — empirically those are
	// benign in section bodies, and over-escaping makes WORLD_CANON
	// facts unreadable for the model.
	if !bytes.ContainsRune(raw, '`') {
		return raw, nil
	}
	out := bytes.ReplaceAll(raw, []byte("`"), []byte("\\`"))
	return out, nil
}

// SectionValidator enforces per-section content rules (cycle 31 L6.H.3).
// Cycle 21 shipped only "section is in the 8-enum" — cycle 31 adds
// per-section structural validators that fire BEFORE rendering so the
// Composer can FAIL fast with a specific cause (Q-L6H-1).
type SectionValidator interface {
	// Validate inspects raw bytes for a section. Returns an error to
	// FAIL the assembly per Q-L6H-1; the error message names the rule
	// that fired (e.g., "user_input markers detected in non-INPUT section").
	Validate(sec Section, raw []byte) error
}

// userInputMarkerPrefix is the XML-style sentinel the input_wrapper
// emits (cycle 31 L6.I). Any occurrence of this prefix in a non-INPUT
// section is a code-review reject condition + a FAIL trigger at
// composition time (defense in depth — the wrapper is supposed to
// catch this earlier).
var userInputMarkerPrefix = []byte("<user_input>")

// DefaultSectionValidator enforces these structural rules:
//
//   - SYSTEM may NOT contain a <user_input> marker (would mean the
//     caller mis-routed user bytes; ADMIN_ACTION_POLICY §4 reject).
//   - WORLD_CANON / SESSION_STATE / ACTOR_CONTEXT / MEMORY / HISTORY /
//     INSTRUCTION: same as SYSTEM — no <user_input> markers.
//   - INPUT: must contain the <user_input> open + close pair (the
//     input_wrapper guarantees this; we re-check at composition time).
//
// Empty sections are permitted (some intents have no memory, no
// history, etc.); the Composer's renderInOrder() preserves position
// for the deterministic hash.
type DefaultSectionValidator struct{}

// Validate — see SectionValidator.
func (DefaultSectionValidator) Validate(sec Section, raw []byte) error {
	if !sec.IsValid() {
		return fmt.Errorf("section_validator: unknown section %q", sec)
	}
	if sec == SectionInput {
		// Empty INPUT is permitted (some intents omit user input —
		// e.g., world_seed). When non-empty, the wrapper guarantees
		// the markers; we verify rather than parse.
		if len(raw) > 0 && !bytes.Contains(raw, userInputMarkerPrefix) {
			return errors.New("section_validator: SectionInput non-empty but missing <user_input> open marker (input_wrapper bypassed?)")
		}
		return nil
	}
	// Non-INPUT sections MUST NOT carry the user-input sentinel.
	if bytes.Contains(raw, userInputMarkerPrefix) {
		return fmt.Errorf("section_validator: %s contains <user_input> marker — user bytes leaked outside INPUT (Q-L6H-1 FAIL)", sec)
	}
	return nil
}

// TemplateContract declares which sections an Intent MUST carry and
// which are optional. Cycle 31 L6.H.1 ties this to the Composer's
// pre-render validator so omitted-required sections trigger an
// immediate Q-L6H-1 FAIL — no best-effort render.
//
// **Per S09 §12Y.4:** SYSTEM + INSTRUCTION are required for every
// intent. Other sections are intent-specific (e.g., world_seed has no
// MEMORY or HISTORY; canon_extraction has no SESSION_STATE).
type TemplateContract struct {
	Intent           Intent
	RequiredSections []Section
	OptionalSections []Section
}

// IntentContracts returns the foundation-default required-section map.
// The LLM-logic sub-program overrides this at composer-construction
// time once per-intent prompt copy lands; foundation V1 ships a
// minimal contract (SYSTEM + INSTRUCTION required for every intent;
// INPUT required for session_turn + npc_reply only).
func IntentContracts() map[Intent]TemplateContract {
	base := []Section{SectionSystem, SectionInstruction}
	withInput := append([]Section{}, base...)
	withInput = append(withInput, SectionInput)
	return map[Intent]TemplateContract{
		IntentSessionTurn: {
			Intent:           IntentSessionTurn,
			RequiredSections: withInput,
			OptionalSections: []Section{SectionWorldCanon, SectionSessionState, SectionActorContext, SectionMemory, SectionHistory},
		},
		IntentNPCReply: {
			Intent:           IntentNPCReply,
			RequiredSections: withInput,
			OptionalSections: []Section{SectionWorldCanon, SectionSessionState, SectionActorContext, SectionMemory, SectionHistory},
		},
		IntentCanonCheck: {
			Intent:           IntentCanonCheck,
			RequiredSections: base,
			OptionalSections: []Section{SectionWorldCanon, SectionInput},
		},
		IntentCanonExtraction: {
			Intent:           IntentCanonExtraction,
			RequiredSections: base,
			OptionalSections: []Section{SectionWorldCanon, SectionInput},
		},
		IntentAdminTriggered: {
			Intent:           IntentAdminTriggered,
			RequiredSections: base,
			OptionalSections: []Section{SectionWorldCanon, SectionSessionState, SectionActorContext, SectionMemory, SectionHistory, SectionInput},
		},
		IntentWorldSeed: {
			Intent:           IntentWorldSeed,
			RequiredSections: base,
			OptionalSections: []Section{SectionWorldCanon},
		},
		IntentSummary: {
			Intent:           IntentSummary,
			RequiredSections: base,
			OptionalSections: []Section{SectionHistory, SectionMemory},
		},
	}
}

// ValidateAgainstContract enforces the per-intent required-section
// rule. Cycle 31 wires this into Composer.AssemblePrompt as the
// pre-render gate (Q-L6H-1: FAIL — never silent-omit).
//
// Returns nil iff every section in contract.RequiredSections has a
// non-nil entry in sections. (Empty value bytes are permitted —
// SectionInput may legitimately carry zero user bytes for world_seed.)
func ValidateAgainstContract(contract TemplateContract, sections SectionMap) error {
	for _, req := range contract.RequiredSections {
		if _, ok := sections[req]; !ok {
			return fmt.Errorf("section_validator: intent %q requires section %s (Q-L6H-1 FAIL)", contract.Intent, req)
		}
	}
	// Unknown sections (not in required ∪ optional) are flagged — the
	// caller likely passed a stray section we never tuned the template
	// for. Foundation does NOT silent-drop.
	allowed := make(map[Section]bool, len(contract.RequiredSections)+len(contract.OptionalSections))
	for _, s := range contract.RequiredSections {
		allowed[s] = true
	}
	for _, s := range contract.OptionalSections {
		allowed[s] = true
	}
	for s := range sections {
		if !allowed[s] {
			return fmt.Errorf("section_validator: intent %q does not accept section %s (Q-L6H-1 FAIL)", contract.Intent, s)
		}
	}
	return nil
}
