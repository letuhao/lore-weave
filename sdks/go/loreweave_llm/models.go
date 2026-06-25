// Package loreweave_llm is the Go client for the LoreWeave LLM gateway
// (contracts/api/llm-gateway/v1/openapi.yaml) — the Go twin of the Python
// (sdks/python/loreweave_llm) and Rust (sdks/rust/loreweave_llm) SDKs.
//
// It exists so a Go domain service can call an LLM through the provider-gateway
// (provider-gateway invariant: no service imports a provider SDK — every LLM call
// goes through provider-registry / the gateway). The first consumer is the
// glossary planner (glossary_plan), which needs a capable completion to turn a
// goal into a typed plan.
//
// Alignment (COMPOSE-A, same rule as loreweave_mcp): aligned with the Python/Rust
// kits at the API + wire-schema level (same /internal/llm/stream endpoint, same
// StreamRequest fields, same SSE event shapes), NOT byte-level cross-language
// interop. Each call is made within one service in one language.
package loreweave_llm

// ModelSource selects which credential table the gateway resolves model_ref from.
type ModelSource string

const (
	// ModelSourceUser — model_ref is a user_models.user_model_id (BYOK). The common case.
	ModelSourceUser ModelSource = "user_model"
	// ModelSourcePlatform — model_ref is a platform_models id (platform-funded).
	ModelSourcePlatform ModelSource = "platform_model"
)

// ReasoningEffort is the cross-provider reasoning-budget knob, forwarded as-is.
// Set ReasoningNone to DISABLE hidden thinking on reasoning models (Qwen3.x,
// DeepSeek-R1, abliterated variants) so reasoning_tokens don't silently burn the
// output budget and return empty prose/JSON — the documented footgun. OpenAI
// o-series accept low/medium/high only (see the gateway's forwarding allowlist).
type ReasoningEffort string

const (
	ReasoningNone   ReasoningEffort = "none"
	ReasoningLow    ReasoningEffort = "low"
	ReasoningMedium ReasoningEffort = "medium"
	ReasoningHigh   ReasoningEffort = "high"
)

// Message is one chat message. Content is a plain string (the chat case); the
// gateway also accepts richer content, not needed by the first consumers.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// StreamRequest mirrors the openapi `StreamRequest`. model_ref is the stringified
// UUID of the resolved model (user_model_id for ModelSourceUser).
type StreamRequest struct {
	ModelSource ModelSource `json:"model_source"`
	ModelRef    string      `json:"model_ref"`
	Messages    []Message   `json:"messages"`

	Tools       []map[string]any `json:"tools,omitempty"`
	ToolChoice  any              `json:"tool_choice,omitempty"`
	Temperature float64          `json:"temperature"`
	// MaxTokens is omitted from the wire when 0 (omitempty) — "let the model
	// decide". Sending max_tokens=0 to most providers caps output at 0 tokens,
	// which is never intended (the Python SDK drops 0 for the same reason).
	MaxTokens int `json:"max_tokens,omitempty"`

	ReasoningEffort    ReasoningEffort `json:"reasoning_effort,omitempty"`
	ChatTemplateKwargs map[string]any  `json:"chat_template_kwargs,omitempty"`
	// StreamFormat defaults to "openai" when empty (set by Complete/Stream).
	StreamFormat string `json:"stream_format,omitempty"`
	TraceID      string `json:"trace_id,omitempty"`
}

// Usage is the token accounting reported by the gateway's `usage` event.
type Usage struct {
	InputTokens     int `json:"input_tokens"`
	OutputTokens    int `json:"output_tokens"`
	ReasoningTokens int `json:"reasoning_tokens"`
}

// Result is the accumulated outcome of a non-streaming Complete call: the full
// assistant text, any reasoning trace, token usage, and the finish reason.
type Result struct {
	Text         string
	Reasoning    string
	Usage        Usage
	FinishReason string
}

// ── SSE event payloads (decoded from each `data:` line by event type) ─────────

type tokenData struct {
	Delta string `json:"delta"`
	Index int    `json:"index"`
}

type usageData struct {
	InputTokens     int `json:"input_tokens"`
	OutputTokens    int `json:"output_tokens"`
	ReasoningTokens int `json:"reasoning_tokens"`
}

type doneData struct {
	FinishReason string `json:"finish_reason"`
}

type errorData struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}
