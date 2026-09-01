package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// A cloud Ollama endpoint must be able to prove who it is.
//
// 🔴 EVERY METHOD ON ollamaAdapter TOOK THE SECRET AS `_` AND DISCARDED IT, so no
// Authorization header could ever be sent. The provider kind was already registerable
// ("ollama" maps to api_standard "ollama" in server.go) and already had its own
// context_length validation, so nothing about the outside surface hinted that the
// credential went nowhere — it only showed up as a 401 on the first authenticated call.
//
// BOTH HALVES ARE ASSERTED. Sending the header when a key exists is the fix; sending
// NOTHING when it does not is the part that keeps local Ollama working, and a change that
// broke it would be a regression on the far more common path.

func newOllamaTestAdapter() *ollamaAdapter {
	return &ollamaAdapter{client: &http.Client{}}
}

func TestOllamaListModelsSendsBearerWhenAKeyIsPresent(t *testing.T) {
	var got string
	var seen bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = true
		got = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"models":[{"name":"gemma4:latest"}]}`))
	}))
	defer srv.Close()

	a := newOllamaTestAdapter()
	if _, err := a.ListModels(context.Background(), srv.URL, "sk-test-key"); err != nil {
		t.Fatalf("ListModels: %v", err)
	}
	if !seen {
		t.Fatal("the adapter never reached the server — the assertion below would be vacuous")
	}
	if got != "Bearer sk-test-key" {
		t.Errorf("Authorization = %q, want %q. A cloud Ollama endpoint cannot authenticate "+
			"and every call 401s.", got, "Bearer sk-test-key")
	}
}

func TestOllamaListModelsSendsNoAuthHeaderForLocal(t *testing.T) {
	var present bool
	var seen bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = true
		_, present = r.Header["Authorization"]
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"models":[]}`))
	}))
	defer srv.Close()

	a := newOllamaTestAdapter()
	if _, err := a.ListModels(context.Background(), srv.URL, ""); err != nil {
		t.Fatalf("ListModels: %v", err)
	}
	if !seen {
		t.Fatal("the adapter never reached the server")
	}
	if present {
		t.Error("an empty secret produced an Authorization header — local Ollama takes no key, " +
			"and sending an empty bearer is a behaviour change on the common path")
	}
}

func TestOllamaInvokeSendsBearerWhenAKeyIsPresent(t *testing.T) {
	var got string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"message":{"content":"ok"},"prompt_eval_count":1,"eval_count":1}`))
	}))
	defer srv.Close()

	a := newOllamaTestAdapter()
	_, _, err := a.Invoke(context.Background(), srv.URL, "sk-test-key", "gemma4",
		map[string]any{"messages": []any{map[string]any{"role": "user", "content": "hi"}}})
	if err != nil {
		t.Fatalf("Invoke: %v", err)
	}
	if !strings.HasPrefix(got, "Bearer ") {
		t.Errorf("Invoke sent Authorization %q — the chat path is the one that actually "+
			"spends the credential", got)
	}
}

// HealthCheck must prove the KEY works, not merely that the host answers.
//
// 🔴 THE OLD CHECK CALLED Invoke WITH AN EMPTY MODEL NAME — tolerated locally, `404 model ''
// not found` on ollama.com, so a working cloud provider reported unhealthy.
//
// 🔴 AND THE OBVIOUS REPLACEMENT WOULD BE VACUOUS. Measured against the live endpoint:
// GET /api/tags and GET /v1/models both answer 200 to a BOGUS key, so a listing-based health
// check passes with a revoked credential. Only POST /api/chat discriminates (200 vs 401).

func TestOllamaHealthCheckProvesTheCredentialNotJustReachability(t *testing.T) {
	var paths []string
	var chatModel string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/tags":
			_, _ = w.Write([]byte(`{"models":[{"name":"nemotron-3-super"}]}`))
		case "/api/chat":
			var body map[string]any
			_ = json.NewDecoder(r.Body).Decode(&body)
			chatModel, _ = body["model"].(string)
			_, _ = w.Write([]byte(`{"message":{"content":"ok"},"prompt_eval_count":1,"eval_count":1}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	if err := newOllamaTestAdapter().HealthCheck(context.Background(), srv.URL, "sk-test"); err != nil {
		t.Fatalf("HealthCheck: %v", err)
	}
	if len(paths) < 2 || paths[len(paths)-1] != "/api/chat" {
		t.Errorf("paths = %v — a cloud health check that never posts a completion cannot "+
			"detect a revoked key, because both listing endpoints answer 200 to a bogus one", paths)
	}
	if chatModel == "" {
		t.Error("the completion was sent with an EMPTY model name — that is the original defect, " +
			"which ollama.com answers with 404 model '' not found")
	}
	if chatModel != "nemotron-3-super" {
		t.Errorf("model = %q, want the one the endpoint said it serves", chatModel)
	}
}

func TestOllamaHealthCheckFAILSWhenTheCredentialIsRejected(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/tags" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"models":[{"name":"nemotron-3-super"}]}`))
			return
		}
		w.WriteHeader(http.StatusUnauthorized) // what ollama.com returns for a bad key
		_, _ = w.Write([]byte(`{"error":"Unauthorized"}`))
	}))
	defer srv.Close()

	// 🔴 THE TEETH. Listing succeeds (as it does on the real endpoint even with a bogus key) and
	// only the completion fails. A check that passed here would be exactly the guard-that-cannot-
	// fail this fix exists to avoid.
	if err := newOllamaTestAdapter().HealthCheck(context.Background(), srv.URL, "bogus"); err == nil {
		t.Fatal("HealthCheck reported HEALTHY on a credential the endpoint rejected — the " +
			"listing passed and nothing checked the key")
	}
}

func TestOllamaHealthCheckSkipsTheCompletionForLocal(t *testing.T) {
	var paths []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"models":[{"name":"gemma4:latest"}]}`))
	}))
	defer srv.Close()

	if err := newOllamaTestAdapter().HealthCheck(context.Background(), srv.URL, ""); err != nil {
		t.Fatalf("HealthCheck (local): %v", err)
	}
	for _, p := range paths {
		if p == "/api/chat" {
			t.Error("local Ollama takes no key, so there is nothing to authenticate — spending a " +
				"completion on every health check is a cost the common path should not pay")
		}
	}
}
