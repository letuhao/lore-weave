package loreweave_mcp

import (
	"fmt"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// C-TOOL `_meta` convention. Every kit-registered tool MUST carry machine-readable
// metadata so the consumer (auto-apply vs confirm), the gateway (prefix), and the
// FE behave correctly without hardcoding tool names. Enforcement is NET-NEW in the
// kit: a tool registered without a valid tier AND scope is rejected (legacy
// glossary/knowledge tools predate `_meta` and are exempt — only kit-registered
// providers go through ValidateToolMeta / MustValidateToolMeta).
//
// The metadata lives in mcp.Tool.Meta (the `_meta` JSON object), under these keys:
const (
	MetaKeyTier     = "tier"     // R|A|W|S — drives auto-apply vs confirm
	MetaKeyScope    = "scope"    // book|project|user|none — drives which guard runs
	MetaKeyUndoHint = "undo_hint" // optional {tool, args} for C-ACTIVITY
	MetaKeySynonyms = "synonyms"  // optional alias terms feeding find_tools (H6)
)

// Tier is the C-TOOL tier enum: R(ead) A(uto) W(rite-confirm) S(chema/secret).
type Tier string

const (
	TierR Tier = "R" // read — no confirm, doesn't count against the write budget
	TierA Tier = "A" // auto-commit + activity/Undo strip
	TierW Tier = "W" // confirm_action (write)
	TierS Tier = "S" // confirm_action (schema/secret)
)

// Scope is the C-TOOL scope enum, selecting which kit guard a tool's handler runs.
type Scope string

const (
	ScopeBook    Scope = "book"
	ScopeProject Scope = "project"
	ScopeUser    Scope = "user"
	ScopeNone    Scope = "none"
)

func validTier(s string) bool {
	switch Tier(s) {
	case TierR, TierA, TierW, TierS:
		return true
	default:
		return false
	}
}

func validScope(s string) bool {
	switch Scope(s) {
	case ScopeBook, ScopeProject, ScopeUser, ScopeNone:
		return true
	default:
		return false
	}
}

// ValidateToolMeta rejects a tool whose `_meta` is missing or carries an invalid
// tier or scope. It is the C-TOOL gate every kit-registered provider runs before
// AddTool. Returns a descriptive error naming the offending tool + field.
func ValidateToolMeta(t *mcp.Tool) error {
	if t == nil {
		return fmt.Errorf("loreweave_mcp: nil tool")
	}
	if t.Meta == nil {
		return fmt.Errorf("loreweave_mcp: tool %q has no _meta (tier+scope required)", t.Name)
	}
	tierVal, ok := t.Meta[MetaKeyTier].(string)
	if !ok || !validTier(tierVal) {
		return fmt.Errorf("loreweave_mcp: tool %q _meta.tier missing or invalid (want R|A|W|S, got %v)", t.Name, t.Meta[MetaKeyTier])
	}
	scopeVal, ok := t.Meta[MetaKeyScope].(string)
	if !ok || !validScope(scopeVal) {
		return fmt.Errorf("loreweave_mcp: tool %q _meta.scope missing or invalid (want book|project|user|none, got %v)", t.Name, t.Meta[MetaKeyScope])
	}
	return nil
}

// MustValidateToolMeta panics on an invalid `_meta`. Use it at registration time
// (server construction) where a malformed tool is a programming error that should
// fail the build/boot, not a runtime condition.
func MustValidateToolMeta(t *mcp.Tool) {
	if err := ValidateToolMeta(t); err != nil {
		panic(err)
	}
}

// NewToolMeta builds a C-TOOL-compliant mcp.Meta with the required tier+scope and
// optional extras, so providers don't hand-assemble the map (and can't typo a
// key). Pass nil/"" for unused optionals.
func NewToolMeta(tier Tier, scope Scope, undoHint map[string]any, synonyms []string) mcp.Meta {
	m := mcp.Meta{
		MetaKeyTier:  string(tier),
		MetaKeyScope: string(scope),
	}
	if undoHint != nil {
		m[MetaKeyUndoHint] = undoHint
	}
	if len(synonyms) > 0 {
		m[MetaKeySynonyms] = synonyms
	}
	return m
}
