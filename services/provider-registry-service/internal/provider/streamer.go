package provider

// streamer.go — Phase 1a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN) — adapter
// streaming primitives.
//
// Each adapter that supports streaming implements `Stream()` which opens
// an upstream provider connection, parses the provider's native SSE/NDJSON
// frames, and emits canonical `StreamChunk` events via the supplied
// EmitFn. The route handler in api/server.go owns the HTTP-level concerns
// (writing the SSE wire format, flushing, client-disconnect detection).
//
// **No wall-clock timeout** anywhere on this path. The stream lives until:
//   - upstream emits `done` (chunk with Done=true)
//   - upstream errors (chunk with Err non-nil)
//   - caller disconnects (ctx canceled — propagated through HTTP request)

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// StreamChunkKind enumerates the canonical event types emitted to callers.
// These map 1:1 to the StreamEventEnvelope discriminator in
// contracts/api/llm-gateway/v1/openapi.yaml.
type StreamChunkKind string

const (
	StreamChunkToken     StreamChunkKind = "token"
	StreamChunkReasoning StreamChunkKind = "reasoning"
	StreamChunkUsage     StreamChunkKind = "usage"
	StreamChunkDone      StreamChunkKind = "done"
	StreamChunkError     StreamChunkKind = "error"
)

// StreamChunk is one canonical event emitted by an adapter's Stream() impl.
// Adapter code does NOT format SSE; it just calls EmitFn(StreamChunk) and
// the route handler serializes to the wire.
type StreamChunk struct {
	Kind StreamChunkKind `json:"event"`

	// Token + Reasoning fields share Delta + Index (different Kind discriminator).
	// Reasoning carries thinking-model intermediate output (separate from
	// the user-visible answer); chat consumers typically display this in a
	// distinct UI surface.
	Delta string `json:"delta,omitempty"`
	Index int    `json:"index,omitempty"`

	// Usage fields (Kind == StreamChunkUsage)
	InputTokens     int  `json:"input_tokens,omitempty"`
	OutputTokens    int  `json:"output_tokens,omitempty"`
	ReasoningTokens *int `json:"reasoning_tokens,omitempty"`

	// Done fields (Kind == StreamChunkDone)
	FinishReason string `json:"finish_reason,omitempty"`

	// Error fields (Kind == StreamChunkError)
	Code    string `json:"code,omitempty"`
	Message string `json:"message,omitempty"`
}

// EmitFn is invoked by adapter Stream() implementations once per canonical
// chunk. The route handler wires this to the HTTP ResponseWriter +
// http.Flusher; tests wire it to an in-memory slice.
//
// EmitFn returning an error signals "downstream caller is gone, stop
// streaming" — adapters MUST short-circuit on that signal and propagate
// the error up.
type EmitFn func(StreamChunk) error

// readSSELines reads an SSE stream (text/event-stream) line-by-line from
// reader, invoking dataHandler for each "data: <JSON>" payload (one per
// SSE event). Returns when the stream closes, ctx is canceled, dataHandler
// returns ErrStreamDone, or any I/O error.
//
// Pure helper — no provider-specific knowledge. Both OpenAI-compat and
// Anthropic SSE formats use `data: <JSON>` payload lines; only the JSON
// shape differs.
func readSSELines(ctx context.Context, body io.Reader, dataHandler func(eventName, data string) error) error {
	scanner := bufio.NewScanner(body)
	// Default buffer is 64KiB; chat completion lines can exceed that for
	// tool-call payloads. Bump to 1 MiB.
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	currentEvent := "" // SSE `event: <name>` lines (Anthropic uses these; OpenAI doesn't)

	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		line := scanner.Text()
		if line == "" {
			// SSE event boundary — reset
			currentEvent = ""
			continue
		}
		if strings.HasPrefix(line, ":") {
			// SSE comment (used for keep-alive); ignore
			continue
		}
		if after, ok := strings.CutPrefix(line, "event:"); ok {
			currentEvent = strings.TrimSpace(after)
			continue
		}
		if after, ok := strings.CutPrefix(line, "data:"); ok {
			data := strings.TrimSpace(after)
			if data == "" {
				continue
			}
			if err := dataHandler(currentEvent, data); err != nil {
				if err == errStreamDone {
					return nil
				}
				return err
			}
		}
	}
	return scanner.Err()
}

// errStreamDone is a sentinel returned by data handlers to signal the
// SSE reader should stop without raising an error (e.g., received OpenAI's
// `data: [DONE]` line).
var errStreamDone = fmt.Errorf("stream done")

// streamOpenAICompat handles OpenAI-shaped SSE chat completion streams.
// Used by openaiAdapter, lmStudioAdapter, and ollamaAdapter (when configured
// to use Ollama's OpenAI-compat /v1/chat/completions endpoint).
//
// Wire format (one event per `data:` line):
//
//	data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0,"finish_reason":null}]}
//	data: {"id":"...","choices":[{"delta":{"content":" world"},"index":0,"finish_reason":null}]}
//	data: {"id":"...","choices":[{"delta":{},"index":0,"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":2,"total_tokens":14}}
//	data: [DONE]
//
// Some providers (OpenAI itself) only include usage in the LAST chunk
// before [DONE]; LM Studio includes it in the chunk with finish_reason set.
// We emit usage when we see it and emit done when we see finish_reason or
// [DONE].
func streamOpenAICompat(ctx context.Context, body io.Reader, emit EmitFn) error {
	tokenIdx := 0
	reasoningIdx := 0
	finishReason := ""
	usageEmitted := false

	err := readSSELines(ctx, body, func(_event, data string) error {
		if data == "[DONE]" {
			return errStreamDone
		}
		var parsed struct {
			Choices []struct {
				Delta struct {
					Content          string `json:"content"`
					ReasoningContent string `json:"reasoning_content"`
				} `json:"delta"`
				FinishReason string `json:"finish_reason"`
			} `json:"choices"`
			Usage *struct {
				PromptTokens             int  `json:"prompt_tokens"`
				CompletionTokens         int  `json:"completion_tokens"`
				CompletionTokensDetails *struct {
					ReasoningTokens int `json:"reasoning_tokens"`
				} `json:"completion_tokens_details"`
			} `json:"usage"`
		}
		if err := json.Unmarshal([]byte(data), &parsed); err != nil {
			// Malformed chunk — emit error and stop. We don't try to
			// recover because the upstream protocol is broken.
			_ = emit(StreamChunk{
				Kind:    StreamChunkError,
				Code:    "LLM_DECODE_ERROR",
				Message: fmt.Sprintf("malformed stream chunk: %v", err),
			})
			return errStreamDone
		}
		for _, choice := range parsed.Choices {
			// Thinking-model reasoning chunks (Qwen3.x, DeepSeek-R1, etc.).
			// Emit BEFORE content so consumers see thought stream first
			// in the same wire-order LM Studio sends.
			if choice.Delta.ReasoningContent != "" {
				if err := emit(StreamChunk{
					Kind:  StreamChunkReasoning,
					Delta: choice.Delta.ReasoningContent,
					Index: reasoningIdx,
				}); err != nil {
					return err
				}
				reasoningIdx++
			}
			if choice.Delta.Content != "" {
				if err := emit(StreamChunk{
					Kind:  StreamChunkToken,
					Delta: choice.Delta.Content,
					Index: tokenIdx,
				}); err != nil {
					return err
				}
				tokenIdx++
			}
			if choice.FinishReason != "" {
				finishReason = choice.FinishReason
			}
		}
		if parsed.Usage != nil && !usageEmitted {
			chunk := StreamChunk{
				Kind:         StreamChunkUsage,
				InputTokens:  parsed.Usage.PromptTokens,
				OutputTokens: parsed.Usage.CompletionTokens,
			}
			if parsed.Usage.CompletionTokensDetails != nil {
				rt := parsed.Usage.CompletionTokensDetails.ReasoningTokens
				chunk.ReasoningTokens = &rt
			}
			if err := emit(chunk); err != nil {
				return err
			}
			usageEmitted = true
		}
		return nil
	})
	if err != nil && err != context.Canceled {
		return err
	}
	// Emit terminal `done` event after upstream closes cleanly. If ctx was
	// canceled, the caller is gone and writing further is a no-op (the
	// emit fn returns an error which we ignore).
	_ = emit(StreamChunk{
		Kind:         StreamChunkDone,
		FinishReason: finishReason,
	})
	return err
}

// openCompletionStream issues a chat-completion HTTP POST to the provider
// with `stream: true` set in the body. Returns a *http.Response whose Body
// the caller is responsible for closing. The caller-supplied bodyOverrides
// is merged into the request body BEFORE the stream:true override (so
// callers can't disable streaming).
func openCompletionStream(
	ctx context.Context,
	client *http.Client,
	url string,
	headers map[string]string,
	body map[string]any,
) (*http.Response, error) {
	// Force stream:true (the entire point of this function). This OVERWRITES
	// any caller value — we do NOT honor stream:false here.
	body["stream"] = true

	raw, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(string(raw)))
	if err != nil {
		return nil, fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		// Phase 4a-α Step 0b — classify network errors. net.Error.Timeout()
		// is the canonical signal for transport-level timeouts (httpx's
		// equivalent of TimeoutException). Anything else (DNS, connection
		// refused, TLS handshake) is treated as transient too — they're
		// just-as-likely caused by transient infra issues.
		var netErr interface{ Timeout() bool }
		if errors.As(err, &netErr) && netErr.Timeout() {
			return nil, &ErrUpstreamTimeout{Underlying: err}
		}
		return nil, &ErrUpstreamTransient{StatusCode: 0, Body: err.Error()}
	}
	if resp.StatusCode >= 400 {
		// Drain a small sample for the error message, then close.
		buf := make([]byte, 512)
		n, _ := resp.Body.Read(buf)
		_ = resp.Body.Close()
		body := string(buf[:n])
		retryAfter := parseRetryAfter(resp.Header.Get("Retry-After"))
		return nil, ClassifyUpstreamHTTP(resp.StatusCode, body, retryAfter)
	}
	return resp, nil
}

// parseRetryAfter parses the "Retry-After: N" header (delta-seconds form
// only). Returns nil when the header is absent or unparseable. HTTP-date
// form (RFC 7231) is intentionally ignored — rare in LLM providers and
// the worker falls back to fixed backoff when this is nil.
func parseRetryAfter(raw string) *float64 {
	if raw == "" {
		return nil
	}
	v, err := strconv.ParseFloat(strings.TrimSpace(raw), 64)
	if err != nil || v < 0 {
		return nil
	}
	return &v
}
