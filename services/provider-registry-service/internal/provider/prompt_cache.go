package provider

import (
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
// ⇒ Only Anthropic needs an explicit request change (default ON). Every other
// provider caches automatically (i.e. already "on by default" — sending anything
// would at best no-op and at worst 400 vLLM). The one exception is the llama.cpp
// `cache_prompt` hint, kept OPT-IN precisely because base_url can't distinguish
// llama.cpp from a strict vLLM, and vLLM 400s on the field.

// promptCacheEnabled — deploy kill-switch for the Anthropic path (default ON).
// Disable platform-wide with LLM_PROMPT_CACHE=0 (or false/off).
func promptCacheEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("LLM_PROMPT_CACHE")))
	return v != "0" && v != "false" && v != "off"
}

// localPromptCacheEnabled — OPT-IN for local OpenAI-compatible servers (default
// OFF). Unlike Anthropic's documented `cache_control`, the `cache_prompt` body
// field is a llama.cpp/LM-Studio extension: some strict local servers (e.g.
// certain vLLM builds with extra=forbid) 400 on unknown fields, and vLLM
// auto-caches prefixes anyway. So an operator running llama.cpp/LM Studio turns
// it on explicitly with LOCAL_PROMPT_CACHE=1.
func localPromptCacheEnabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("LOCAL_PROMPT_CACHE")))
	return v == "1" || v == "true" || v == "on"
}

// applyAnthropicPromptCache marks the stable prefix (tools + system) with
// cache_control:{type:ephemeral} so Anthropic caches it across the turn's
// tool-loop and the session's turns (5-min TTL). Call AFTER tools + system are
// set on the body.
//
// Only acts when tools are present: an agentic request is where the prefix is
// actually reused, and tools alone exceed the 1024-token cache minimum, so both
// the tools-only breakpoint (last tool) and the tools+system breakpoint (system)
// sit on prefixes above the minimum — no wasted/invalid breakpoints. Idempotent
// and mutation-in-place on the already-Anthropic-shaped body.
func applyAnthropicPromptCache(body map[string]any) {
	if !promptCacheEnabled() {
		return
	}
	tools, ok := body["tools"].([]map[string]any)
	if !ok || len(tools) == 0 {
		return // no reusable tool prefix → nothing worth a cache write
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

// applyLocalPromptCache sets cache_prompt=true for a LOCAL OpenAI-compatible
// server (non-empty base_url: LM Studio / Ollama / llama.cpp). It NEVER touches
// the real OpenAI cloud path (empty base_url → OpenAI 400s on unknown fields).
// Opt-in (LOCAL_PROMPT_CACHE=1) because server tolerance of the field varies.
func applyLocalPromptCache(body map[string]any, endpointBaseURL string) {
	if !localPromptCacheEnabled() {
		return
	}
	if strings.TrimRight(endpointBaseURL, "/") == "" {
		return // default endpoint = real OpenAI cloud — must not send cache_prompt
	}
	body["cache_prompt"] = true
}
