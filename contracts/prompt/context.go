package prompt

import (
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// PromptContext is the input to AssemblePrompt. It carries the WHO + the
// WHAT-FOR, plus retrieval shaping hints. The Composer turns this into
// a rendered prompt via the active template for `Intent`.
//
// **Body bytes are NOT a field on this type.** User-authored content
// enters via the Composer-bound Inputs map (one entry per template-
// declared user-input slot), not via context. This keeps the type
// shape itself a gate against accidentally stuffing user text into
// non-INPUT sections.
type PromptContext struct {
	// RealityID — the home reality for this prompt call. Required (audit +
	// privacy filter need it).
	RealityID uuid.UUID

	// SessionID — nil for non-session intents (world_seed, canon_extraction).
	// Required for session_turn / npc_reply.
	SessionID *uuid.UUID

	// ActorUserRefID — the human user on whose behalf this prompt runs.
	// Required for audit + S2/S3 filters.
	ActorUserRefID uuid.UUID

	// ActorPCID — the player character ID (nil for non-PC intents like
	// canon_extraction or world_seed).
	ActorPCID *uuid.UUID

	// Intent — see intent.go. Required + must validate.
	Intent Intent

	// RetrievalHints — caps on memory + history depth and the relevance
	// query used by retrieval. The Composer's ResolveContext consults
	// these. Foundation V1 ships only the type; ResolveContext is a
	// caller-supplied interface (cycle 21 ships the shape, LLM-logic
	// sub-program ships behavior).
	RetrievalHints RetrievalHints

	// AdminTier — present iff Intent == IntentAdminTriggered. The actual
	// enum lives in contracts/admin-related cycles; we carry an opaque
	// string here to avoid premature cross-cycle import.
	AdminTier string

	// ConsentSnapshotID — opaque reference to a ConsentSnapshot row
	// (cycle 3 user_consent_ledger). The Composer's resolver dereferences
	// this when applying the consent gate; type-level we keep the ID only.
	ConsentSnapshotID *uuid.UUID

	// TemplateID + TemplateVersion — when nil (zero value) the Composer
	// resolves the active template via registry.yaml; callers may pin
	// explicitly for replay (incident reproduction).
	TemplateID      string
	TemplateVersion int
}

// RetrievalHints shape retrieval depth on a per-call basis. Concrete
// limits live in templates' meta.yaml; these are CALLER overrides.
type RetrievalHints struct {
	MaxMemories       int    // <= 0 = use template default
	MaxHistoryEvents  int    // <= 0 = use template default
	RelevanceQuery    string // free-text retrieval seed (e.g., turn text)
}

// Validate enforces the minimal shape contract. Missing required fields
// fail loudly — the Composer MUST NOT silently default.
func (c PromptContext) Validate() error {
	if c.RealityID == uuid.Nil {
		return errors.New("prompt: RealityID is zero")
	}
	if c.ActorUserRefID == uuid.Nil {
		return errors.New("prompt: ActorUserRefID is zero")
	}
	if !c.Intent.IsValid() {
		return fmt.Errorf("prompt: invalid intent %q", c.Intent)
	}
	// session_turn + npc_reply MUST carry a session_id.
	switch c.Intent {
	case IntentSessionTurn, IntentNPCReply:
		if c.SessionID == nil {
			return fmt.Errorf("prompt: intent %q requires SessionID", c.Intent)
		}
	}
	if c.Intent == IntentAdminTriggered && c.AdminTier == "" {
		return errors.New("prompt: admin_triggered requires AdminTier")
	}
	if c.TemplateVersion < 0 {
		return errors.New("prompt: TemplateVersion is negative")
	}
	return nil
}
