package provider

// capabilities.go — Provider Context Strategy §3 (spec
// docs/specs/2026-07-06-provider-context-strategy.md). A static, code-owned map of
// which caching / context optimizations a provider_kind supports. This is the SINGLE
// HOME of the capability facts ("one home / one name" — Settings & Config Boundary);
// chat-service consumes it (surfaced on the resolved credential) to pick a
// ContextStrategy and to LABEL the caching-monitoring section — it never re-derives
// caching behavior from `if kind == "..."` (spec §2: capability, not provider name).
//
// Keyed on provider_kind — the SAME closed set ResolveAdapter switches on — not a
// model literal (no-hardcoded-model) and not the provider display-name.

// ProviderCapabilities declares the context-optimization surface of a provider kind.
type ProviderCapabilities struct {
	// PromptCacheControl — the provider honors EXPLICIT cache_control:{ephemeral}
	// breakpoints on the request (Anthropic). Drives applyAnthropicPromptCache +
	// chat-service's system-prefix marking.
	PromptCacheControl bool `json:"prompt_cache_control"`
	// ResponsesAPI — the provider offers the stateful /v1/responses API with
	// server-held context chained by previous_response_id (Phase 2 StatefulResponses).
	ResponsesAPI bool `json:"responses_api"`
	// AutoPrefixCache — the server caches a repeated prefix AUTOMATICALLY (server-side
	// KV-prefix reuse), so the request carries NOTHING. Informational: it drives
	// monitoring classification, not request-shaping (OpenAI / vLLM / LM-Studio
	// chat-completions / Ollama all cache automatically).
	AutoPrefixCache bool `json:"auto_prefix_cache"`
}

// CapabilitiesFor returns the static capabilities for a provider_kind. Unknown /
// custom kinds (the same ones ResolveAdapter routes to the openai-compat adapter,
// e.g. vLLM behind a custom endpoint) get auto_prefix_cache only — server-side
// prefix caching is on by default there and the request must send nothing (vLLM 400s
// on unknown fields), but they do NOT expose the OpenAI Responses API.
func CapabilitiesFor(providerKind string) ProviderCapabilities {
	switch providerKind {
	case "anthropic":
		return ProviderCapabilities{PromptCacheControl: true}
	case "openai":
		return ProviderCapabilities{ResponsesAPI: true, AutoPrefixCache: true}
	case "lm_studio":
		return ProviderCapabilities{ResponsesAPI: true, AutoPrefixCache: true}
	case "ollama":
		return ProviderCapabilities{AutoPrefixCache: true}
	default:
		// custom / openai-compat / vLLM — automatic server-side prefix cache; no Responses API.
		return ProviderCapabilities{AutoPrefixCache: true}
	}
}

// AsMap renders the capabilities as a JSON-object map for wire transport on the
// resolved-credential response (chat-service reads these keys). Kept in lockstep with
// the struct fields — the wire contract chat-service depends on.
func (c ProviderCapabilities) AsMap() map[string]bool {
	return map[string]bool{
		"prompt_cache_control": c.PromptCacheControl,
		"responses_api":        c.ResponsesAPI,
		"auto_prefix_cache":    c.AutoPrefixCache,
	}
}
