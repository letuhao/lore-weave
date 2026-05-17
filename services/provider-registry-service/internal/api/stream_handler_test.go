package api

// stream_handler_test.go — Phase 5a router-level coverage for the
// operation-branch logic in doLlmStream. The deeper integration paths
// (credential resolution + adapter dispatch + actual SSE streaming) need
// a live DB pool and a fake adapter wired into ResolveAdapter — those
// land in a follow-up integration suite OR are exercised by live smoke
// post-merge. See deferred D-PHASE5A-STREAM-INTEGRATION-TESTS.
//
// These tests fire requests through the chi router and assert HTTP-level
// behavior: validation rejections (no DB needed) + the
// "operation defaults to chat" backward-compat regression-lock.

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// TestDoLlmStream_OperationDefaultIsChat — Phase 5a backward-compat
// regression-lock. Existing chat callers omit `operation`; the gateway
// MUST treat missing-or-"chat" identically. We assert this by sending a
// request with NO operation field but no messages either — if the
// default applied, the handler reaches the chat branch and rejects with
// "messages required". If the default broke (e.g. someone made operation
// strictly required), we'd get an "unsupported stream operation" error
// instead.
func TestDoLlmStream_OperationDefaultIsChat(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`"
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 (chat-branch validation), got %d body=%s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if !strings.Contains(body, "messages required") {
		t.Errorf("expected 'messages required' (chat path was taken); got %s", body)
	}
	if strings.Contains(body, "unsupported stream operation") {
		t.Errorf("operation default broke — got %s", body)
	}
}

// TestDoLlmStream_OperationChatExplicit — same as above but with
// explicit operation=chat. Locks that explicit and omitted produce
// identical behavior.
func TestDoLlmStream_OperationChatExplicit(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "chat",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`"
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "messages required") {
		t.Errorf("expected 'messages required'; got %s", w.Body.String())
	}
}

func TestDoLlmStream_TtsRequiresInput(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "tts",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`"
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "input required for tts") {
		t.Errorf("expected 'input required for tts'; got %s", w.Body.String())
	}
}

func TestDoLlmStream_TtsRequiresInputText(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "tts",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"voice": "alloy"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "input.text required for tts") {
		t.Errorf("expected 'input.text required for tts'; got %s", w.Body.String())
	}
}

// /review-impl MED#3 — Phase 5a: stream-handler SSE error frame
// classifies typed upstream errors into canonical LLM_* codes.
// Pure function, tested directly.
func TestClassifySpeakErrorCode_RateLimited(t *testing.T) {
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow down"}
	if got := classifySpeakErrorCode(rl); got != "LLM_RATE_LIMITED" {
		t.Errorf("got %q, want LLM_RATE_LIMITED", got)
	}
}

func TestClassifySpeakErrorCode_AuthFailed(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 401, Body: "bad key"}
	if got := classifySpeakErrorCode(perm); got != "LLM_AUTH_FAILED" {
		t.Errorf("got %q, want LLM_AUTH_FAILED", got)
	}
	perm = &provider.ErrUpstreamPermanent{StatusCode: 403, Body: "forbidden"}
	if got := classifySpeakErrorCode(perm); got != "LLM_AUTH_FAILED" {
		t.Errorf("got %q, want LLM_AUTH_FAILED (403)", got)
	}
}

func TestClassifySpeakErrorCode_Permanent4xxIsUpstreamError(t *testing.T) {
	// 400 (not 401/403) maps to generic upstream error
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad voice"}
	if got := classifySpeakErrorCode(perm); got != "LLM_UPSTREAM_ERROR" {
		t.Errorf("got %q, want LLM_UPSTREAM_ERROR", got)
	}
}

func TestClassifySpeakErrorCode_NotSupported(t *testing.T) {
	if got := classifySpeakErrorCode(provider.ErrOperationNotSupported); got != "LLM_OPERATION_NOT_SUPPORTED" {
		t.Errorf("got %q, want LLM_OPERATION_NOT_SUPPORTED", got)
	}
}

func TestClassifySpeakErrorCode_GenericMapsToUpstream(t *testing.T) {
	if got := classifySpeakErrorCode(errors.New("something else")); got != "LLM_UPSTREAM_ERROR" {
		t.Errorf("got %q, want LLM_UPSTREAM_ERROR", got)
	}
}

func TestDoLlmStream_UnknownOperationRejected(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "embedding",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"texts": ["x"]}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if !strings.Contains(body, "unsupported stream operation") {
		t.Errorf("expected 'unsupported stream operation'; got %s", body)
	}
	if !strings.Contains(body, "chat, tts") {
		t.Errorf("expected hint listing 'chat, tts'; got %s", body)
	}
}

// TestHasToolDefinitions — Phase 0b D8 guard helper. The JSON `tools` field
// decodes to `any`: absent ⇒ nil, `[]` ⇒ non-nil empty slice (asks for
// nothing — must NOT trip the guard), `[{...}]` ⇒ has tools.
func TestHasToolDefinitions(t *testing.T) {
	cases := []struct {
		name  string
		tools any
		want  bool
	}{
		{"nil (field absent)", nil, false},
		{"empty array", []any{}, false},
		{"one tool", []any{map[string]any{"type": "function"}}, true},
		{"two tools", []any{map[string]any{}, map[string]any{}}, true},
		{"non-array junk", "auto", false},
	}
	for _, c := range cases {
		if got := hasToolDefinitions(c.tools); got != c.want {
			t.Errorf("%s: hasToolDefinitions(%#v) = %v, want %v", c.name, c.tools, got, c.want)
		}
	}
}
