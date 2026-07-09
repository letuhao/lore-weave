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
	MetaKeyTier       = "tier"       // R|A|W|S — drives auto-apply vs confirm
	MetaKeyScope      = "scope"      // book|project|user|none — drives which guard runs
	MetaKeyUndoHint   = "undo_hint"  // optional {tool, args} for C-ACTIVITY
	MetaKeySynonyms   = "synonyms"   // optional alias terms feeding find_tools (H6)
	MetaKeyVisibility = "visibility" // discoverable|legacy — CAT-4 (mcp-tool-io.md Part 4)
	MetaKeyAsync      = "async"      // true ⇒ tool STARTS a background job (async-honesty)
	MetaKeyPaid       = "paid"       // true ⇒ calling it SPENDS real money (Track D CD1)
	// MetaKeySupersededBy — the tool that replaces a `legacy` one. Consumers already
	// read it (`tool_list`/`tool_load` label it); until now NOTHING produced it.
	MetaKeySupersededBy = "superseded_by"
)

// Visibility is the CAT-4 catalog-hygiene enum. Absent (zero value) reads as
// VisibilityDiscoverable — a tool with no explicit visibility is discoverable by
// default, so existing tools need no change. A "legacy" tool keeps its schema and
// handler working for any existing caller; it is excluded from find_tools/
// search_catalog and from any domain hot-seed on BOTH federation surfaces
// (chat-service tool_discovery.py + ai-gateway find-tools.ts must stay in
// lockstep — see mcp-tool-io.md CAT-4). The ONLY path back to a legacy tool is
// an explicit, user-initiated per-session pin (Settings & Configuration Boundary
// SET-1) — never a blanket unlock.
type Visibility string

const (
	VisibilityDiscoverable Visibility = "discoverable"
	VisibilityLegacy       Visibility = "legacy"
)

// WithVisibility returns a copy of m with _meta.visibility set. A plain function,
// not a method — mcp.Meta is a map type owned by the go-sdk package, so we can't
// attach methods to it from here. Callers chain it onto NewToolMeta's result:
//
//	Meta: lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy)
func WithVisibility(m mcp.Meta, v Visibility) mcp.Meta {
	m[MetaKeyVisibility] = string(v)
	return m
}

// WithAsync returns a copy of m with _meta.async=true — the tool STARTS a background
// job (queued; not done when the call returns). Chained onto NewToolMeta like
// WithVisibility. This is the DURABLE async-honesty signal: a consumer (the workflow
// step-runner) reads it from the catalog instead of guessing from the tool name.
//
//	Meta: lwmcp.WithAsync(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil))
func WithAsync(m mcp.Meta) mcp.Meta {
	m[MetaKeyAsync] = true
	return m
}

// WithPaid returns a copy of m with _meta.paid=true — calling this tool SPENDS REAL
// MONEY (an outward paid API, or LLM/embedding tokens). Track D CD1.
//
// `paid` is ORTHOGONAL to `tier`: spend governs money, tier governs mutation. A PAID
// READ (e.g. web search) is legitimate — it stays tier R and remains callable in `ask`
// mode — but it must clear a SPEND gate, never a write gate. Do NOT coerce a tool to
// tier A/W merely because it costs money.
//
//	Meta: lwmcp.WithPaid(lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, nil))
func WithPaid(m mcp.Meta) mcp.Meta {
	m[MetaKeyPaid] = true
	return m
}

// WithSupersededBy returns a copy of m with _meta.superseded_by set — names the tool
// that REPLACES this one. Pair it with WithVisibility(..., VisibilityLegacy) when a tool
// is renamed: the old name keeps working (deprecate, never delete — CAT-4) and both
// `tool_list` and `tool_load` label it with its replacement so an agent migrates itself.
//
//	Meta: lwmcp.WithSupersededBy(
//	        lwmcp.WithVisibility(lwmcp.NewToolMeta(...), lwmcp.VisibilityLegacy),
//	        "web_search")
func WithSupersededBy(m mcp.Meta, tool string) mcp.Meta {
	m[MetaKeySupersededBy] = tool
	return m
}

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
