package jobs

// Phase 2b — per-operation result aggregator. The worker streams one or
// more chunks (only one chunk in Phase 2b — chunking lands in Phase 3),
// and the aggregator turns those chunks into the final `result` JSONB
// payload that GET /v1/llm/jobs/{id} returns.
//
// One Aggregator instance is created per job invocation. It owns
// mutable counter + accumulator state so the worker doesn't need to.
//
// Per-operation result schemas are documented (informally) in
// contracts/api/llm-gateway/v1/openapi.yaml under `Job.result`.

import (
	"strings"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// Aggregator collapses per-chunk StreamChunk events into a single result
// payload. Each operation has its own aggregator type; we expose one
// constructor that selects by operation name.
type Aggregator interface {
	// Accept consumes one StreamChunk. Returns true if the consumer
	// (worker) should also forward the chunk to a downstream sink (FE
	// progress) — Phase 2b ignores this; Phase 2c uses it to emit
	// per-token callbacks.
	Accept(chunk provider.StreamChunk) bool

	// Finalize returns the canonical result payload + final usage
	// counters once Stream() returns. The map shape matches the openapi
	// `Job.result` documentation per operation.
	Finalize() (result map[string]any, inputTokens int, outputTokens int)
}

// NewAggregator picks the right Aggregator implementation for the
// operation. Unknown operations get a generic accumulator that just
// concatenates token deltas into a single content string.
func NewAggregator(operation string) Aggregator {
	switch operation {
	case "chat", "completion":
		return &chatAggregator{}
	default:
		return &chatAggregator{} // default to text-concat
	}
}

// chatAggregator accumulates token deltas + usage.
//   result = {messages: [{role: "assistant", content: "..."}], usage: {...}}
type chatAggregator struct {
	tokens          strings.Builder
	reasoning       strings.Builder
	inputTokens     int
	outputTokens    int
	reasoningTokens int
	finishReason    string
}

func (a *chatAggregator) Accept(chunk provider.StreamChunk) bool {
	switch chunk.Kind {
	case provider.StreamChunkToken:
		a.tokens.WriteString(chunk.Delta)
	case provider.StreamChunkReasoning:
		a.reasoning.WriteString(chunk.Delta)
	case provider.StreamChunkUsage:
		a.inputTokens = chunk.InputTokens
		a.outputTokens = chunk.OutputTokens
		if chunk.ReasoningTokens != nil {
			a.reasoningTokens = *chunk.ReasoningTokens
		}
	case provider.StreamChunkDone:
		a.finishReason = chunk.FinishReason
	case provider.StreamChunkError:
		// Errors are surfaced via Finalize → worker → repo.Finalize();
		// nothing to accumulate here.
	}
	return true
}

func (a *chatAggregator) Finalize() (map[string]any, int, int) {
	message := map[string]any{
		"role":    "assistant",
		"content": a.tokens.String(),
	}
	if a.reasoning.Len() > 0 {
		message["reasoning_content"] = a.reasoning.String()
	}
	usage := map[string]any{
		"input_tokens":  a.inputTokens,
		"output_tokens": a.outputTokens,
	}
	if a.reasoningTokens > 0 {
		usage["reasoning_tokens"] = a.reasoningTokens
	}
	result := map[string]any{
		"messages": []any{message},
		"usage":    usage,
	}
	if a.finishReason != "" {
		result["finish_reason"] = a.finishReason
	}
	return result, a.inputTokens, a.outputTokens
}
