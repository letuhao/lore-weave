package jobs

// Phase 3b — per-operation result aggregator with multi-chunk support.
// Worker calls StartChunk/EndChunk around each adapter.Stream invocation
// when chunking is configured; for unchunked jobs neither hook fires
// and behavior is identical to Phase 2b.
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

// chunkSeparator joins per-chunk content in the final aggregated
// result. Two newlines so adjacent chunks read as separate paragraphs;
// callers wanting raw concatenation can post-process.
const chunkSeparator = "\n\n"

// Aggregator collapses per-chunk StreamChunk events into a single result
// payload. Each operation has its own aggregator type; we expose one
// constructor that selects by operation name.
//
// Phase 3b lifecycle for a chunked job:
//
//	NewAggregator(op)
//	for each chunk:
//	    StartChunk(idx)
//	    for each StreamChunk: Accept(...)
//	    EndChunk(idx)
//	Finalize() → result
//
// Unchunked job (Phase 2b path): no Start/End calls; Accept/Finalize
// behave identically to before.
type Aggregator interface {
	// StartChunk signals a new chunk's stream is about to begin.
	// Aggregators that need per-chunk state reset their per-chunk
	// buffers here. idx is 0-based.
	StartChunk(idx int)

	// EndChunk signals the chunk's stream has completed cleanly.
	// Aggregators that defer cross-chunk merging until between-chunk
	// boundaries flush per-chunk state into global state here.
	EndChunk(idx int)

	// Accept consumes one StreamChunk. Returns true if the consumer
	// (worker) should also forward the chunk to a downstream sink (FE
	// progress) — Phase 2b ignores this; Phase 2c uses it to emit
	// per-token callbacks.
	Accept(chunk provider.StreamChunk) bool

	// Finalize returns the canonical result payload + final usage
	// counters once all chunks have been processed. The map shape
	// matches the openapi `Job.result` documentation per operation.
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

// chatAggregator accumulates token deltas + reasoning + usage with
// multi-chunk awareness.
//
// Per-chunk state:
//   - chunkContent: tokens for the CURRENT chunk; flushed to globalTokens
//     on EndChunk with chunkSeparator between non-empty chunks.
//   - chunkReasoning: reasoning for the CURRENT chunk; the LAST chunk's
//     reasoning wins (typical thinking-model UX where the final answer's
//     synthesis is the value-add, not earlier draft thoughts).
//
// Global state (across chunks):
//   - globalTokens: final concatenated content.
//   - lastReasoning: most-recent finished chunk's reasoning.
//   - input/output/reasoningTokens: SUMMED across chunks for billing.
//   - finishReason: last chunk's finish reason wins (caller drives
//     order; the streamer emits done last).
type chatAggregator struct {
	// Global, cross-chunk
	globalTokens    strings.Builder
	lastReasoning   string
	inputTokens     int
	outputTokens    int
	reasoningTokens int
	finishReason    string
	chunkCount      int

	// Per-chunk (reset on StartChunk; flushed on EndChunk)
	chunkContent   strings.Builder
	chunkReasoning strings.Builder
	inChunk        bool
}

func (a *chatAggregator) StartChunk(_ int) {
	a.inChunk = true
	a.chunkContent.Reset()
	a.chunkReasoning.Reset()
}

func (a *chatAggregator) EndChunk(_ int) {
	if !a.inChunk {
		return
	}
	a.inChunk = false
	piece := a.chunkContent.String()
	if piece != "" {
		if a.chunkCount > 0 {
			a.globalTokens.WriteString(chunkSeparator)
		}
		a.globalTokens.WriteString(piece)
	}
	if a.chunkReasoning.Len() > 0 {
		a.lastReasoning = a.chunkReasoning.String()
	}
	a.chunkCount++
}

func (a *chatAggregator) Accept(chunk provider.StreamChunk) bool {
	switch chunk.Kind {
	case provider.StreamChunkToken:
		// Route into the per-chunk buffer when chunked, else straight
		// to the global builder so unchunked Phase 2b behavior is
		// preserved with no Start/End calls.
		if a.inChunk {
			a.chunkContent.WriteString(chunk.Delta)
		} else {
			a.globalTokens.WriteString(chunk.Delta)
		}
	case provider.StreamChunkReasoning:
		if a.inChunk {
			a.chunkReasoning.WriteString(chunk.Delta)
		} else {
			// Unchunked path keeps reasoning in lastReasoning so
			// Finalize() emits it as before.
			a.lastReasoning += chunk.Delta
		}
	case provider.StreamChunkUsage:
		// Sum across chunks. inputTokens for chunked jobs is the SUM
		// of each chunk's prompt tokens (each chunk re-pays the system
		// prompt + chunk content); outputTokens is the SUM of each
		// chunk's generated tokens.
		a.inputTokens += chunk.InputTokens
		a.outputTokens += chunk.OutputTokens
		if chunk.ReasoningTokens != nil {
			a.reasoningTokens += *chunk.ReasoningTokens
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
	// If we're still inside a chunk (caller forgot EndChunk), flush
	// defensively. Belt-and-braces.
	if a.inChunk {
		a.EndChunk(-1)
	}
	message := map[string]any{
		"role":    "assistant",
		"content": a.globalTokens.String(),
	}
	if a.lastReasoning != "" {
		message["reasoning_content"] = a.lastReasoning
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
