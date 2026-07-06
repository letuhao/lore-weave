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
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

// streamIdleTimeout — per-Read idle timeout applied to streaming response
// bodies via wrapStreamBody. 0 means "disabled" — the historical default,
// preserving the "No wall-clock timeout anywhere on this path" philosophy
// documented at the top of this file. The env var allows operators to opt
// in to defense-in-depth against an upstream provider (notably LM Studio
// under model auto-eviction) that drops a streaming connection without
// emitting `done` or `err`. A non-idle timeout is fundamentally different
// from a wall-clock timeout — it only fires when NO bytes have arrived in
// the window, so a legitimately slow but progressing model never trips it.
//
// Default 300s in deployment (compose) — real models stream tokens within
// seconds; 300s of no upstream activity ≈ certainly dead.
var streamIdleTimeout time.Duration

func init() {
	if s := os.Getenv("LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 {
			streamIdleTimeout = time.Duration(n) * time.Second
		}
	}
}

// idleTimeoutReader wraps an io.ReadCloser with a per-Read idle timer.
// When no Read returns within `timeout`, the timer closes the underlying
// body which unblocks the pending Read with a "use of closed" error; the
// next Read call (or this one's err handling) sees `closed.Load() == true`
// and returns ErrUpstreamTimeout so callers can classify the failure mode
// instead of seeing a generic transport error.
//
// timeout <= 0 makes Read a transparent pass-through. The check is at the
// top of every Read so callers can swap the timeout at runtime if needed.
type idleTimeoutReader struct {
	body    io.ReadCloser
	timeout time.Duration
	closed  atomic.Bool // set true when our timer closed body (vs caller-driven close)
}

func newIdleTimeoutReader(body io.ReadCloser, timeout time.Duration) *idleTimeoutReader {
	return &idleTimeoutReader{body: body, timeout: timeout}
}

func (r *idleTimeoutReader) Read(p []byte) (int, error) {
	if r.timeout <= 0 {
		return r.body.Read(p)
	}
	// Per-Read timer: as long as Read returns within the window, the timer
	// is Stopped and never fires. If Read blocks past the window, the timer
	// closes the body, the pending Read returns an error, and we translate
	// to ErrUpstreamTimeout below.
	timer := time.AfterFunc(r.timeout, func() {
		r.closed.Store(true)
		_ = r.body.Close()
	})
	n, err := r.body.Read(p)
	timer.Stop()
	if err != nil && r.closed.Load() {
		// Body was closed by OUR timer mid-read → upstream went idle.
		// Surface as the canonical upstream-timeout error so caller code
		// (worker.go retry/permanent classification) treats it correctly.
		return n, &ErrUpstreamTimeout{
			Underlying: fmt.Errorf("no upstream data for %s", r.timeout),
		}
	}
	return n, err
}

func (r *idleTimeoutReader) Close() error {
	return r.body.Close()
}

// wrapStreamBody installs the idle-timeout reader on a streaming response's
// Body when streamIdleTimeout is enabled. Called by openCompletionStream
// (OpenAI / LM Studio / Ollama path) and doStreamPOST (Anthropic path) so
// every streaming upstream goes through the same defense.
func wrapStreamBody(resp *http.Response) *http.Response {
	if resp == nil || resp.Body == nil || streamIdleTimeout <= 0 {
		return resp
	}
	resp.Body = newIdleTimeoutReader(resp.Body, streamIdleTimeout)
	return resp
}

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
	// StreamChunkToolCall — one incremental fragment of a tool call the
	// model is emitting. Re-framed from OpenAI `delta.tool_calls[]` /
	// Anthropic `input_json_delta` without buffering; consumers reassemble
	// by Index. See contracts/api/llm-gateway/v1/openapi.yaml ToolCallEvent.
	StreamChunkToolCall StreamChunkKind = "tool_call"
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
	//
	// Index is ALSO reused by Kind == StreamChunkToolCall — but with
	// different semantics: for token/reasoning it is a monotonic event
	// counter; for tool_call it is the provider's own tool-call index (a
	// semantic call identifier, set verbatim, never incremented here).
	Delta string `json:"delta,omitempty"`
	Index int    `json:"index,omitempty"`

	// Usage fields (Kind == StreamChunkUsage)
	InputTokens     int  `json:"input_tokens,omitempty"`
	OutputTokens    int  `json:"output_tokens,omitempty"`
	ReasoningTokens *int `json:"reasoning_tokens,omitempty"`

	// Cache-token split (Provider Context Strategy §7 monitoring). Populated on a
	// usage chunk when the provider reports cache activity; nil when it reports none
	// (or the provider doesn't cache). Provider-NORMALIZED to one concept each:
	//   CacheCreationTokens — tokens WRITTEN to cache this turn (premium-billed;
	//                         Anthropic cache_creation_input_tokens; 0/absent elsewhere).
	//   CacheReadTokens     — tokens SERVED FROM cache this turn (cheap/free;
	//                         Anthropic cache_read_input_tokens, OpenAI/Responses
	//                         *_tokens_details.cached_tokens — same concept, one name).
	// InputTokens stays the FULL billed input volume (Anthropic folds creation+read
	// back in; OpenAI's prompt_tokens already includes cached), so uncached input is
	// derived downstream as InputTokens − creation − read. Pointers so an omitted
	// field is distinguishable from a real 0 and never emits a misleading `:0`.
	CacheCreationTokens *int `json:"cache_creation_tok,omitempty"`
	CacheReadTokens     *int `json:"cache_read_tok,omitempty"`

	// Done fields (Kind == StreamChunkDone)
	FinishReason string `json:"finish_reason,omitempty"`

	// Error fields (Kind == StreamChunkError)
	Code    string `json:"code,omitempty"`
	Message string `json:"message,omitempty"`

	// Tool-call fields (Kind == StreamChunkToolCall). Index above carries
	// the tool-call index. ID + ToolName appear on the FIRST fragment for
	// an index; that first fragment may carry an empty ArgumentsDelta.
	// All three are `omitempty` — this is the SHARED StreamChunk struct, so
	// a non-omitempty tag would emit `arguments_delta:""` on every token /
	// usage / done event too. omitempty does NOT lose the tool-call event:
	// the `event:tool_call` SSE frame + ID + ToolName still serialize; only
	// an information-free empty string is dropped. Consumers default an
	// absent `arguments_delta` to "" — see openapi ToolCallEvent (optional).
	ToolCallID     string `json:"id,omitempty"`
	ToolName       string `json:"name,omitempty"`
	ArgumentsDelta string `json:"arguments_delta,omitempty"`
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
					// OpenAI streams tool calls as incremental fragments: the
					// first fragment for an index carries id + function.name
					// (arguments usually ""), later fragments carry only
					// function.arguments fragments.
					ToolCalls []struct {
						Index    int    `json:"index"`
						ID       string `json:"id"`
						Function struct {
							Name      string `json:"name"`
							Arguments string `json:"arguments"`
						} `json:"function"`
					} `json:"tool_calls"`
				} `json:"delta"`
				FinishReason string `json:"finish_reason"`
			} `json:"choices"`
			Usage *struct {
				PromptTokens            int `json:"prompt_tokens"`
				CompletionTokens        int `json:"completion_tokens"`
				CompletionTokensDetails *struct {
					ReasoningTokens int `json:"reasoning_tokens"`
				} `json:"completion_tokens_details"`
				// OpenAI + LM-Studio + vLLM report automatic prefix-cache hits here
				// (prompt_tokens already INCLUDES these). §7 caching monitor reads it.
				PromptTokensDetails *struct {
					CachedTokens int `json:"cached_tokens"`
				} `json:"prompt_tokens_details"`
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
			// Tool-call fragments. Index comes verbatim from the provider
			// (a semantic call identifier — NOT a local counter). Emit when
			// the fragment carries id, name, OR non-empty arguments; skip a
			// fully-empty fragment. The first fragment for an index carries
			// id+name with empty arguments — it MUST still be emitted.
			for _, tc := range choice.Delta.ToolCalls {
				if tc.ID == "" && tc.Function.Name == "" && tc.Function.Arguments == "" {
					continue
				}
				if err := emit(StreamChunk{
					Kind:           StreamChunkToolCall,
					Index:          tc.Index,
					ToolCallID:     tc.ID,
					ToolName:       tc.Function.Name,
					ArgumentsDelta: tc.Function.Arguments,
				}); err != nil {
					return err
				}
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
			// Automatic prefix-cache hits (server-side). These are READ hits (no
			// separate write charge on OpenAI-compat), so map to CacheReadTokens —
			// the same normalized concept as Anthropic's cache_read_input_tokens.
			if d := parsed.Usage.PromptTokensDetails; d != nil && d.CachedTokens > 0 {
				ct := d.CachedTokens
				chunk.CacheReadTokens = &ct
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

	// Request a trailing usage chunk. OpenAI-compatible servers (incl. LM
	// Studio) omit token usage from streaming responses UNLESS this is set —
	// without it the canonical `usage` SSE event never fires for streamed
	// chat. The streamer already handles the usage-only final chunk (empty
	// `choices` + `usage`). OVERWRITES any caller value.
	body["stream_options"] = map[string]any{"include_usage": true}

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
	return wrapStreamBody(resp), nil
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
