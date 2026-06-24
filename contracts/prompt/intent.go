package prompt

import (
	"errors"
	"fmt"
)

// Intent enumerates the 7 LLM-call purposes the foundation supports.
// Wire format = canonical snake_case (matches prompt_audit.intent column
// CHECK constraints + S09 §12Y.2 vocabulary).
//
// Adding a new intent is a wire-contract change: bump v1.yaml schema
// version + add a fixture + cross-language enum update (Rust mirror).
type Intent string

const (
	// IntentSessionTurn — a player's turn in an active session. Most common.
	IntentSessionTurn Intent = "session_turn"

	// IntentNPCReply — an NPC's response composition (autonomous or scripted).
	IntentNPCReply Intent = "npc_reply"

	// IntentCanonCheck — validate a proposed canon entry against existing
	// L1/L2 facts (R02 §12B.4).
	IntentCanonCheck Intent = "canon_check"

	// IntentCanonExtraction — knowledge-service batch extraction of entities
	// + facts from a book chunk.
	IntentCanonExtraction Intent = "canon_extraction"

	// IntentAdminTriggered — admin-initiated prompt (bulk summary, audit).
	// Always carries an AdminTier in PromptContext.
	IntentAdminTriggered Intent = "admin_triggered"

	// IntentWorldSeed — one-shot reality bootstrap (R02 §12R.2).
	IntentWorldSeed Intent = "world_seed"

	// IntentSummary — memory compaction (§12H session memory summarizer).
	IntentSummary Intent = "summary"
)

// AllIntents returns every enumerated intent. Used by tests + the future
// template-coverage lint to confirm registry.yaml stays exhaustive.
func AllIntents() []Intent {
	return []Intent{
		IntentSessionTurn,
		IntentNPCReply,
		IntentCanonCheck,
		IntentCanonExtraction,
		IntentAdminTriggered,
		IntentWorldSeed,
		IntentSummary,
	}
}

// IsValid returns true iff i is one of the 7 enumerated intents.
func (i Intent) IsValid() bool {
	for _, ok := range AllIntents() {
		if i == ok {
			return true
		}
	}
	return false
}

// ErrUnknownIntent is returned by ParseIntent on any unknown string.
// Callers MUST NOT silently default to IntentSessionTurn on parse
// failure — that would mask routing bugs as "looked like a session turn".
var ErrUnknownIntent = errors.New("prompt: unknown intent")

// ParseIntent parses the wire format. Errors on unknown strings.
func ParseIntent(s string) (Intent, error) {
	it := Intent(s)
	if !it.IsValid() {
		return "", fmt.Errorf("%w: %q", ErrUnknownIntent, s)
	}
	return it, nil
}

// String returns the canonical wire form. Identity (Intent is already a
// typed string) — defined for fmt.Stringer convenience.
func (i Intent) String() string { return string(i) }
