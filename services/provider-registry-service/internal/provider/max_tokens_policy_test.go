package provider

// Phase 3c-followup tests for the policy: caller max_tokens=0 (or
// omitted) means "let the model decide" — adapters must NOT include
// max_tokens in the upstream payload. Anthropic is the documented
// exception (its API requires max_tokens; we keep the 8192 default).

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

// recordingServer captures the last request body for assertion.
type recordingServer struct {
	*httptest.Server
	lastBody []byte
}

func newRecordingServer(t *testing.T, response string) *recordingServer {
	t.Helper()
	rs := &recordingServer{}
	rs.Server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		rs.lastBody = body
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(response))
	}))
	t.Cleanup(rs.Close)
	return rs
}

func parseBody(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("parse body: %v", err)
	}
	return out
}

const fakeChatResponse = `{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}`

func TestOpenAIInvoke_MaxTokensOmittedWhenCallerOmits(t *testing.T) {
	srv := newRecordingServer(t, fakeChatResponse)
	a := &openaiAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"sk-test",
		"gpt-4o-mini",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "hi"}}},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	if _, has := body["max_tokens"]; has {
		t.Errorf("max_tokens should NOT appear when caller omits; body=%v", body)
	}
}

func TestOpenAIInvoke_MaxTokensOmittedWhenCallerPassesZero(t *testing.T) {
	srv := newRecordingServer(t, fakeChatResponse)
	a := &openaiAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"sk-test",
		"gpt-4o-mini",
		map[string]any{
			"messages":   []map[string]any{{"role": "user", "content": "hi"}},
			"max_tokens": 0,
		},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	if _, has := body["max_tokens"]; has {
		t.Errorf("max_tokens=0 should be omitted; body=%v", body)
	}
}

func TestOpenAIInvoke_MaxTokensIncludedWhenPositive(t *testing.T) {
	srv := newRecordingServer(t, fakeChatResponse)
	a := &openaiAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"sk-test",
		"gpt-4o-mini",
		map[string]any{
			"messages":   []map[string]any{{"role": "user", "content": "hi"}},
			"max_tokens": 512,
		},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	got, has := body["max_tokens"]
	if !has {
		t.Fatalf("max_tokens=512 should appear; body=%v", body)
	}
	if int(got.(float64)) != 512 {
		t.Errorf("max_tokens = %v, want 512", got)
	}
}

func TestLmStudioInvoke_MaxTokensOmittedWhenCallerOmits(t *testing.T) {
	srv := newRecordingServer(t, fakeChatResponse)
	a := &lmStudioAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"",
		"local-model",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "hi"}}},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	if _, has := body["max_tokens"]; has {
		t.Errorf("max_tokens should NOT appear when caller omits; body=%v", body)
	}
}

func TestLmStudioInvoke_MaxTokensOmittedWhenZero(t *testing.T) {
	srv := newRecordingServer(t, fakeChatResponse)
	a := &lmStudioAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"",
		"local-model",
		map[string]any{
			"messages":   []map[string]any{{"role": "user", "content": "hi"}},
			"max_tokens": 0,
		},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	if _, has := body["max_tokens"]; has {
		t.Errorf("max_tokens=0 should be omitted; body=%v", body)
	}
}

func TestAnthropicInvoke_MaxTokensDefaultedWhenOmitted(t *testing.T) {
	// Anthropic API requires max_tokens; the adapter MUST always send
	// one. Caller-omitted → 8192 default. This test pins that contract
	// so a future "omit when missing" refactor doesn't accidentally
	// break Anthropic.
	srv := newRecordingServer(t, `{"content":[{"type":"text","text":"ok"}],"usage":{"input_tokens":1,"output_tokens":1}}`)
	a := &anthropicAdapter{client: http.DefaultClient}
	_, _, err := a.Invoke(
		context.Background(),
		srv.URL,
		"sk-ant-test",
		"claude-3-5-sonnet-20241022",
		map[string]any{"messages": []map[string]any{{"role": "user", "content": "hi"}}},
	)
	if err != nil {
		t.Fatalf("invoke: %v", err)
	}
	body := parseBody(t, srv.lastBody)
	got, has := body["max_tokens"]
	if !has {
		t.Errorf("Anthropic requires max_tokens; default must be present")
	}
	if int(got.(float64)) != 8192 {
		t.Errorf("Anthropic default max_tokens = %v, want 8192", got)
	}
}
