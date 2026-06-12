package provider

// Phase 1a unit tests for the OpenAI-compat SSE streamer. Pure helper
// tests — no live HTTP call, no provider connection. Tests feed a
// reconstructed SSE wire stream into streamOpenAICompat() and assert
// the canonical StreamChunk emissions.

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"
)

func collectChunks(t *testing.T, body string) []StreamChunk {
	t.Helper()
	var chunks []StreamChunk
	emit := func(c StreamChunk) error {
		chunks = append(chunks, c)
		return nil
	}
	if err := streamOpenAICompat(context.Background(), strings.NewReader(body), emit); err != nil {
		t.Fatalf("streamOpenAICompat: %v", err)
	}
	return chunks
}

func TestStreamOpenAICompat_BasicTokens(t *testing.T) {
	body := `data: {"choices":[{"delta":{"content":"Hello"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":" world"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Expect: token Hello, token " world", done
	if len(chunks) != 3 {
		t.Fatalf("expected 3 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToken || chunks[0].Delta != "Hello" || chunks[0].Index != 0 {
		t.Errorf("chunk[0] = %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkToken || chunks[1].Delta != " world" || chunks[1].Index != 1 {
		t.Errorf("chunk[1] = %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkDone || chunks[2].FinishReason != "stop" {
		t.Errorf("chunk[2] = %+v", chunks[2])
	}
}

func TestStreamOpenAICompat_UsageEvent(t *testing.T) {
	body := `data: {"choices":[{"delta":{"content":"hi"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Expect: token hi, usage, done
	if len(chunks) != 3 {
		t.Fatalf("expected 3 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0].Kind != StreamChunkToken {
		t.Errorf("chunk[0] should be token, got %+v", chunks[0])
	}
	if chunks[1].Kind != StreamChunkUsage {
		t.Errorf("chunk[1] should be usage, got %+v", chunks[1])
	}
	if chunks[1].InputTokens != 10 || chunks[1].OutputTokens != 2 {
		t.Errorf("usage tokens wrong: %+v", chunks[1])
	}
	if chunks[2].Kind != StreamChunkDone {
		t.Errorf("chunk[2] should be done, got %+v", chunks[2])
	}
}

func TestStreamOpenAICompat_ReasoningTokens(t *testing.T) {
	// LM Studio thinking-model usage payload (qwen3.x format).
	body := `data: {"choices":[{"delta":{"content":"answer"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}],"usage":{"prompt_tokens":24,"completion_tokens":575,"total_tokens":599,"completion_tokens_details":{"reasoning_tokens":567}}}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var usage *StreamChunk
	for i := range chunks {
		if chunks[i].Kind == StreamChunkUsage {
			usage = &chunks[i]
			break
		}
	}
	if usage == nil {
		t.Fatalf("no usage chunk: %#v", chunks)
	}
	if usage.ReasoningTokens == nil || *usage.ReasoningTokens != 567 {
		t.Errorf("reasoning_tokens not propagated: %+v", usage.ReasoningTokens)
	}
}

func TestStreamOpenAICompat_FinishReasonOnly(t *testing.T) {
	// Some providers send finish_reason in a chunk but no usage.
	// We should still emit a `done` event with the finish_reason.
	body := `data: {"choices":[{"delta":{"content":"hi"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"length"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	last := chunks[len(chunks)-1]
	if last.Kind != StreamChunkDone || last.FinishReason != "length" {
		t.Errorf("expected done with finish_reason=length, got %+v", last)
	}
}

func TestStreamOpenAICompat_MalformedChunkEmitsError(t *testing.T) {
	body := `data: not-valid-json

data: [DONE]

`
	chunks := collectChunks(t, body)
	// Should see error chunk + done (the parser stops on error but the
	// outer wrapper still emits a terminal done).
	hasError := false
	for _, c := range chunks {
		if c.Kind == StreamChunkError && c.Code == "LLM_DECODE_ERROR" {
			hasError = true
		}
	}
	if !hasError {
		t.Errorf("expected LLM_DECODE_ERROR chunk on malformed JSON: %#v", chunks)
	}
}

func TestStreamOpenAICompat_EmptyDeltaSkipped(t *testing.T) {
	// Some providers send keepalive chunks with empty delta.content.
	// We should NOT emit a token chunk for those.
	body := `data: {"choices":[{"delta":{"content":""},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"real"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var tokens []string
	for _, c := range chunks {
		if c.Kind == StreamChunkToken {
			tokens = append(tokens, c.Delta)
		}
	}
	if len(tokens) != 1 || tokens[0] != "real" {
		t.Errorf("expected exactly one non-empty token, got %v", tokens)
	}
}

func TestStreamOpenAICompat_SSECommentsIgnored(t *testing.T) {
	body := `: keep-alive comment

data: {"choices":[{"delta":{"content":"x"},"index":0,"finish_reason":null}]}

: another keep-alive

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	if len(chunks) != 2 || chunks[0].Delta != "x" {
		t.Errorf("comments must be ignored; got %#v", chunks)
	}
}

func TestStreamOpenAICompat_EmitErrorStopsStreaming(t *testing.T) {
	// If emit returns an error (caller disconnected), the streamer must
	// stop and propagate the error up.
	body := `data: {"choices":[{"delta":{"content":"a"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"b"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"c"},"index":0,"finish_reason":null}]}

data: [DONE]

`
	count := 0
	emit := func(c StreamChunk) error {
		count++
		if count >= 2 {
			return context.Canceled
		}
		return nil
	}
	err := streamOpenAICompat(context.Background(), strings.NewReader(body), emit)
	if err != context.Canceled {
		t.Errorf("expected context.Canceled, got %v", err)
	}
	// We stop after the 2nd emit (token "b"); the third token "c" should
	// not be processed. The streamer also tries to emit a final `done`
	// which counts as the (failing) emit, so we expect count >= 2.
	if count < 2 {
		t.Errorf("expected at least 2 emits before cancel, got %d", count)
	}
}

func TestStreamOpenAICompat_ReasoningContentEmitsReasoningChunks(t *testing.T) {
	// LM Studio thinking models (qwen3.x) stream reasoning_content
	// per-token in delta. Each reasoning delta must produce a
	// StreamChunkReasoning event distinct from token events.
	body := `data: {"choices":[{"delta":{"role":"assistant","reasoning_content":"Let"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"reasoning_content":" me"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"reasoning_content":" think"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"Answer"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var reasoning []string
	var tokens []string
	for _, c := range chunks {
		switch c.Kind {
		case StreamChunkReasoning:
			reasoning = append(reasoning, c.Delta)
		case StreamChunkToken:
			tokens = append(tokens, c.Delta)
		}
	}
	if len(reasoning) != 3 || reasoning[0] != "Let" || reasoning[2] != " think" {
		t.Errorf("reasoning chunks not emitted as expected: %v", reasoning)
	}
	if len(tokens) != 1 || tokens[0] != "Answer" {
		t.Errorf("token chunks wrong: %v", tokens)
	}
	// Reasoning indexes should be independent of token indexes.
	var reasoningIdxs, tokenIdxs []int
	for _, c := range chunks {
		if c.Kind == StreamChunkReasoning {
			reasoningIdxs = append(reasoningIdxs, c.Index)
		}
		if c.Kind == StreamChunkToken {
			tokenIdxs = append(tokenIdxs, c.Index)
		}
	}
	for i, idx := range reasoningIdxs {
		if idx != i {
			t.Errorf("reasoning index %d expected %d, got %d", i, i, idx)
		}
	}
	for i, idx := range tokenIdxs {
		if idx != i {
			t.Errorf("token index %d expected %d, got %d", i, i, idx)
		}
	}
}

func TestStreamOpenAICompat_ReasoningAndContentInSameDelta(t *testing.T) {
	// Some chunks may carry BOTH reasoning_content and content (rare but
	// not forbidden by the spec). Both must produce events.
	body := `data: {"choices":[{"delta":{"reasoning_content":"thinking","content":"answer"},"index":0,"finish_reason":null}]}

data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}

data: [DONE]

`
	chunks := collectChunks(t, body)
	var hasReasoning, hasToken bool
	for _, c := range chunks {
		if c.Kind == StreamChunkReasoning && c.Delta == "thinking" {
			hasReasoning = true
		}
		if c.Kind == StreamChunkToken && c.Delta == "answer" {
			hasToken = true
		}
	}
	if !hasReasoning {
		t.Errorf("reasoning chunk missing: %#v", chunks)
	}
	if !hasToken {
		t.Errorf("token chunk missing: %#v", chunks)
	}
}

func TestReadSSELines_HandlesEventNamePrefix(t *testing.T) {
	// Anthropic-style SSE has event: lines that we don't use yet but
	// shouldn't crash on.
	body := `event: content_block_delta
data: {"hello":"world"}

`
	var seenEvents []string
	var seenData []string
	err := readSSELines(context.Background(), strings.NewReader(body), func(eventName, data string) error {
		seenEvents = append(seenEvents, eventName)
		seenData = append(seenData, data)
		return nil
	})
	if err != nil {
		t.Fatalf("readSSELines: %v", err)
	}
	if len(seenEvents) != 1 || seenEvents[0] != "content_block_delta" {
		t.Errorf("event name not parsed: %v", seenEvents)
	}
	if len(seenData) != 1 || seenData[0] != `{"hello":"world"}` {
		t.Errorf("data not parsed: %v", seenData)
	}
}

// blockingReadCloser is a test ReadCloser whose Read blocks until either
// (a) Close is called (Read returns io.ErrClosedPipe) or (b) the test
// pushes bytes via Send. Used to simulate an upstream that goes idle —
// the failure mode that bit `sherlock_speckled_band` extraction when LM
// Studio auto-evicted the model mid-stream and the streamer waited
// forever (no `done`, no `err` ever arrived).
type blockingReadCloser struct {
	in     chan []byte
	closed chan struct{}
	once   sync.Once
}

func newBlockingReadCloser() *blockingReadCloser {
	return &blockingReadCloser{
		in:     make(chan []byte, 4),
		closed: make(chan struct{}),
	}
}

func (b *blockingReadCloser) Read(p []byte) (int, error) {
	// Drain any already-buffered data FIRST. A bare select over {in, closed}
	// picks randomly when BOTH are ready (data buffered AND body closed),
	// which made TestIdleTimeoutReader_ZeroTimeoutDisables flaky: a Send
	// followed by Close left both channels ready, so Read sometimes returned
	// io.ErrClosedPipe before delivering the buffered "hello". Real pipes
	// deliver buffered bytes before reporting close, so model that here.
	select {
	case data, ok := <-b.in:
		if !ok {
			return 0, io.EOF
		}
		n := copy(p, data)
		return n, nil
	default:
	}
	select {
	case data, ok := <-b.in:
		if !ok {
			return 0, io.EOF
		}
		n := copy(p, data)
		return n, nil
	case <-b.closed:
		return 0, io.ErrClosedPipe
	}
}

func (b *blockingReadCloser) Close() error {
	b.once.Do(func() { close(b.closed) })
	return nil
}

func (b *blockingReadCloser) Send(data []byte) { b.in <- data }

func TestIdleTimeoutReader_FiresWhenNoData(t *testing.T) {
	// Upstream goes idle: no data, no close. Timer must fire and
	// translate the close-induced Read error into ErrUpstreamTimeout so
	// the worker classifies the chunk as upstream-stuck instead of seeing
	// a generic transport error. Regression-lock for the
	// sherlock_speckled_band stall.
	body := newBlockingReadCloser()
	r := newIdleTimeoutReader(body, 100*time.Millisecond)
	buf := make([]byte, 16)
	start := time.Now()
	n, err := r.Read(buf)
	elapsed := time.Since(start)
	if n != 0 {
		t.Errorf("expected 0 bytes, got %d", n)
	}
	var ute *ErrUpstreamTimeout
	if !errors.As(err, &ute) {
		t.Fatalf("expected *ErrUpstreamTimeout, got %T: %v", err, err)
	}
	if elapsed < 80*time.Millisecond || elapsed > 400*time.Millisecond {
		t.Errorf("timer fired at the wrong time: %s", elapsed)
	}
}

func TestIdleTimeoutReader_PassThroughWhenDataFlows(t *testing.T) {
	// Per-Read timer is Stopped on every successful Read. As long as data
	// keeps arriving (within the window), the timer never fires.
	body := newBlockingReadCloser()
	r := newIdleTimeoutReader(body, 200*time.Millisecond)
	go func() {
		for i := 0; i < 3; i++ {
			time.Sleep(50 * time.Millisecond)
			body.Send([]byte("chunk"))
		}
		body.Close()
	}()
	buf := make([]byte, 16)
	totalReads := 0
	for {
		_, err := r.Read(buf)
		if err == io.EOF || errors.Is(err, io.ErrClosedPipe) {
			break
		}
		var ute *ErrUpstreamTimeout
		if errors.As(err, &ute) {
			t.Fatalf("idle timeout fired despite flowing data: %v", err)
		}
		if err != nil {
			t.Fatalf("unexpected err: %v", err)
		}
		totalReads++
		if totalReads > 5 {
			t.Fatalf("loop runaway")
		}
	}
	if totalReads != 3 {
		t.Errorf("expected 3 successful reads, got %d", totalReads)
	}
}

func TestIdleTimeoutReader_ZeroTimeoutDisables(t *testing.T) {
	// timeout <= 0 must be a transparent pass-through (preserves the
	// historical "No wall-clock timeout" behavior when the env var is
	// unset in deployment).
	body := newBlockingReadCloser()
	body.Send([]byte("hello"))
	body.Close()
	r := newIdleTimeoutReader(body, 0)
	buf := make([]byte, 16)
	n, err := r.Read(buf)
	if err != nil {
		t.Fatalf("first read err: %v", err)
	}
	if string(buf[:n]) != "hello" {
		t.Errorf("payload wrong: %q", buf[:n])
	}
	if _, err := r.Read(buf); err != io.ErrClosedPipe && err != io.EOF {
		t.Errorf("expected EOF/ErrClosedPipe on closed body, got %v", err)
	}
}

func TestWrapStreamBody_SkipsWhenTimeoutDisabled(t *testing.T) {
	// wrapStreamBody must be a no-op when streamIdleTimeout == 0 so the
	// callers don't add overhead in the default-off configuration.
	prev := streamIdleTimeout
	streamIdleTimeout = 0
	defer func() { streamIdleTimeout = prev }()

	body := io.NopCloser(strings.NewReader("payload"))
	resp := &http.Response{Body: body}
	out := wrapStreamBody(resp)
	if out.Body != body {
		t.Errorf("wrap should be a no-op when timeout disabled; body was swapped")
	}
}

func TestWrapStreamBody_AppliesWhenEnabled(t *testing.T) {
	prev := streamIdleTimeout
	streamIdleTimeout = 50 * time.Millisecond
	defer func() { streamIdleTimeout = prev }()

	body := io.NopCloser(strings.NewReader("payload"))
	resp := &http.Response{Body: body}
	out := wrapStreamBody(resp)
	if _, ok := out.Body.(*idleTimeoutReader); !ok {
		t.Errorf("body not wrapped: %T", out.Body)
	}
}
