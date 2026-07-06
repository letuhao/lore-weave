package provider

import (
	"encoding/json"
	"os"
	"strings"
)

// prompt_cache.go — D-PROMPT-CACHING (2026-07-06). Prefix caching reuses the
// stable tools+system prefix across an agent loop's many calls — the exact
// re-send that inflated context cost (docs/eval/context-budget/
// context-explosion-investigation-2026-07-06.md). This lives in the provider
// adapter (not chat-service) because WHETHER caching is possible, and HOW to
// request it, is a provider-kind fact — the caller builds a normal OpenAI-shaped
// request and each adapter does the right thing.
//
// Per-provider mechanism (web-researched 2026-07-06 — they genuinely differ):
//
//	Anthropic / Bedrock-Claude : EXPLICIT `cache_control:{ephemeral}` breakpoints
//	                             (max 4). We mark the last tool + system → the
//	                             tools+system prefix is cached. 90% cheaper reads.
//	OpenAI                     : AUTOMATIC for any ≥1024-tok prefix. No field to
//	                             send; caching is already on by default server-side.
//	Gemini 2.5+ / DeepSeek     : AUTOMATIC (implicit). Nothing to send.
//	vLLM (local)               : AUTOMATIC (--enable-prefix-caching, on by default)
//	                             AND rejects unknown request fields with HTTP 400 —
//	                             so we must NOT send `cache_prompt` to it.
//	llama.cpp / LM Studio       : honor `cache_prompt:true` (a llama.cpp extension).
//
// ⇒ Anthropic needs an explicit request change (default ON). OpenAI / Gemini /
// DeepSeek / vLLM cache automatically (already "on by default" — sending anything
// would at best no-op and at worst 400 vLLM, so their adapter sends NOTHING).
// LM Studio's llama.cpp `cache_prompt` is applied in its OWN dedicated adapter
// (also default ON) — safe there because that adapter is reached only for
// lm_studio credentials, so there is no vLLM/OpenAI on the path to 400. The
// provider IDENTITY (which adapter) is the gate, not a fragile base_url guess.

// promptCacheEnabled — deploy kill-switch for the Anthropic path (default ON).
// Disable platform-wide with LLM_PROMPT_CACHE=0 (or false/off).
func promptCacheEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("LLM_PROMPT_CACHE")))
	return v != "0" && v != "false" && v != "off"
}

// anthropicCacheMinChars — a defensive lower bound on the marked prefix. Claude's
// cache minimum is 1024 tokens (older) to 4096 (Opus/Sonnet/Haiku 4.5); a block
// below it is silently NOT cached (no error). We only mark cache_control once the
// tools JSON is plausibly worth caching (~1024 tok ≈ 4KB chars) so we never spend
// a breakpoint on a trivially small tool set. (Newer 4096-min models therefore
// only cache once the prefix is ~16KB+ — a reduced-benefit, not a break.)
const anthropicCacheMinChars = 4096

// applyAnthropicPromptCache marks the stable prefix (tools + system) with
// cache_control:{type:ephemeral} so Anthropic caches it across the turn's
// tool-loop and the session's turns (5-min TTL). Call AFTER tools + system are
// set on the body.
//
// Only acts when tools are present AND the tools JSON clears the cache-minimum
// guard: an agentic request is where the prefix is actually reused, and the guard
// keeps us from spending a breakpoint on a below-minimum prefix that wouldn't
// cache anyway. Idempotent and mutation-in-place on the Anthropic-shaped body.
func applyAnthropicPromptCache(body map[string]any) {
	if !promptCacheEnabled() {
		return
	}
	tools, ok := body["tools"].([]map[string]any)
	if !ok || len(tools) == 0 {
		return // no reusable tool prefix → nothing worth a cache write
	}
	if b, err := json.Marshal(tools); err != nil || len(b) < anthropicCacheMinChars {
		return // below the cache minimum → marking would be a no-op breakpoint
	}
	cc := map[string]any{"type": "ephemeral"}
	// Breakpoint 1: the last tool caches the ENTIRE tools array.
	tools[len(tools)-1]["cache_control"] = cc
	// Breakpoint 2: system caches the tools+system prefix (cumulative). Convert a
	// plain-string system into a single text block so cache_control has a home.
	switch sys := body["system"].(type) {
	case string:
		if sys != "" {
			body["system"] = []map[string]any{
				{"type": "text", "text": sys, "cache_control": cc},
			}
		}
	case []map[string]any:
		if len(sys) > 0 {
			sys[len(sys)-1]["cache_control"] = cc
		}
	case []any:
		if len(sys) > 0 {
			if last, ok := sys[len(sys)-1].(map[string]any); ok {
				last["cache_control"] = cc
			}
		}
	}
}

// applyLmStudioPromptCache sets cache_prompt=true for LM Studio, whose llama.cpp
// backend honors the field (prefix KV reuse). Default ON via the LLM_PROMPT_CACHE
// kill-switch. Unlike the shared openai adapter (which also serves vLLM / real
// OpenAI — both 400 on unknown fields), this runs ONLY on the dedicated
// lmStudioAdapter, so the provider identity is the gate: there is no vLLM/OpenAI
// on this path to break, so it's safe to default-on with no base_url guard.
func applyLmStudioPromptCache(body map[string]any) {
	if !promptCacheEnabled() {
		return
	}
	body["cache_prompt"] = true
}
