package api

// Public MCP P3 (PUB-12 — BYOK-only) router tests. A job that originated at the
// public MCP edge carries job_meta.mcp_key_id; such a key may spend ONLY through
// the owner's own BYOK credentials, so a platform_model draw is rejected with 402
// LLM_BYOK_ONLY BEFORE the guardrail reservation (and before the subsystem-nil 503,
// matching the handler's caller-input-first validation order). First-party traffic
// (no mcp_key_id) is unaffected.

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestInternalSubmitLlmJob_BYOK_PlatformModelWithMcpKeyRejected(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "chat",
			"model_source": "platform_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"messages": []},
			"job_meta": {"mcp_key_id": "`+uuid.NewString()+`"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402 LLM_BYOK_ONLY, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "LLM_BYOK_ONLY") {
		t.Errorf("expected LLM_BYOK_ONLY in body, got %s", w.Body.String())
	}
}

func TestInternalSubmitLlmJob_BYOK_UserModelWithMcpKeyAllowed(t *testing.T) {
	// A public key on its OWN BYOK model is fine — passes the PUB-12 gate and
	// proceeds (router-only server has no subsystem → 503, NOT 402).
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "chat",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"messages": []},
			"job_meta": {"mcp_key_id": "`+uuid.NewString()+`"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code == http.StatusPaymentRequired {
		t.Fatalf("user_model + mcp_key_id must NOT be rejected by PUB-12, got 402 body=%s", w.Body.String())
	}
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (no subsystem) after passing the BYOK gate, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestInternalSubmitLlmJob_BYOK_PlatformModelWithHeaderRejected(t *testing.T) {
	// The X-Mcp-Key-Id header is also a valid public-key carrier at submit time
	// (present before the job is queued) — platform_model + header → 402.
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{"operation":"chat","model_source":"platform_model","model_ref":"`+uuid.NewString()+`","input":{"messages":[]}}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("X-Mcp-Key-Id", uuid.NewString())
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusPaymentRequired {
		t.Fatalf("platform_model + X-Mcp-Key-Id header: expected 402, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "LLM_BYOK_ONLY") {
		t.Errorf("expected LLM_BYOK_ONLY, got %s", w.Body.String())
	}
}

func TestInternalLlmStream_BYOK_PlatformModelWithHeaderRejected(t *testing.T) {
	// PUB-12 wired on the synchronous streaming path too. platform_model + the
	// X-Mcp-Key-Id header → 402, before any credential resolution (nil pool).
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/stream?user_id="+uuid.NewString(),
		strings.NewReader(`{"operation":"chat","model_source":"platform_model","model_ref":"`+uuid.NewString()+`","messages":[]}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("X-Mcp-Key-Id", uuid.NewString())
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusPaymentRequired {
		t.Fatalf("stream platform_model + header: expected 402, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "LLM_BYOK_ONLY") {
		t.Errorf("expected LLM_BYOK_ONLY, got %s", w.Body.String())
	}
}

func TestInternalProxy_BYOK_PlatformModelWithHeaderRejected(t *testing.T) {
	// PUB-12 wired on the transparent proxy path too. A non-deprecated target +
	// platform_model + X-Mcp-Key-Id header → 402, before credential resolution.
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/proxy/v1/models?user_id="+uuid.NewString()+"&model_source=platform_model&model_ref="+uuid.NewString(),
		strings.NewReader(`{}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("X-Mcp-Key-Id", uuid.NewString())
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusPaymentRequired {
		t.Fatalf("proxy platform_model + header: expected 402, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "LLM_BYOK_ONLY") {
		t.Errorf("expected LLM_BYOK_ONLY, got %s", w.Body.String())
	}
}

func TestInternalSubmitLlmJob_BYOK_PlatformModelNoMcpKeyAllowed(t *testing.T) {
	// First-party traffic (no mcp_key_id) on a platform_model is unaffected by
	// PUB-12 — passes the gate and proceeds (503, NOT 402).
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "chat",
			"model_source": "platform_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"messages": []}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code == http.StatusPaymentRequired {
		t.Fatalf("platform_model WITHOUT mcp_key_id must NOT be rejected by PUB-12, got 402 body=%s", w.Body.String())
	}
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (no subsystem), got %d body=%s", w.Code, w.Body.String())
	}
}
