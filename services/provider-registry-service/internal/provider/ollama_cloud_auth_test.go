package provider

import (
	"context"
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
