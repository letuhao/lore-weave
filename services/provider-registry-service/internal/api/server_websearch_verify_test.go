package api

// web_search-aware verify (the /review-impl deferral, now built). Unit-level
// (like server_rerank_verify_test.go): proves the capability routes to web_search
// and that verifyWebSearch does a real /search "ping" — verified on reach,
// not-verified (with an error) when the endpoint resolves to nothing. The latter
// is the live bug this feature surfaces: a `localhost` endpoint from inside a
// container hits the container's own loopback and fails.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDetectPrimaryCapability_WebSearch(t *testing.T) {
	if got := detectPrimaryCapability(map[string]any{"web_search": true}); got != "web_search" {
		t.Errorf("boolean flag: got %q, want web_search", got)
	}
	if got := detectPrimaryCapability(map[string]any{"_capability": "web_search"}); got != "web_search" {
		t.Errorf("_capability form: got %q, want web_search", got)
	}
	// A chat model must NOT route to web_search.
	if got := detectPrimaryCapability(map[string]any{"chat": true}); got == "web_search" {
		t.Errorf("chat must not route to web_search, got %q", got)
	}
}

func TestVerifyWebSearch_ReachableKeyless(t *testing.T) {
	var gotPath, gotAuth string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"answer":"ok","results":[{"title":"T","url":"https://ex.com/1","content":"c","score":1}]}`))
	}))
	defer up.Close()

	srv := &Server{invokeClient: &http.Client{}}
	res := srv.verifyWebSearch(context.Background(), up.URL, "") // keyless: empty secret

	if res["verified"] != true {
		t.Fatalf("verified = %v, want true (res=%+v)", res["verified"], res)
	}
	if res["result_count"] != 1 {
		t.Errorf("result_count = %v, want 1", res["result_count"])
	}
	if gotPath != "/search" {
		t.Errorf("upstream path = %q, want /search", gotPath)
	}
	// Keyless must NOT send an Authorization header (the bug verify must tolerate).
	if gotAuth != "" {
		t.Errorf("keyless verify sent Authorization=%q, want none", gotAuth)
	}
}

func TestVerifyWebSearch_KeyedSendsBearer(t *testing.T) {
	var gotAuth string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer up.Close()

	srv := &Server{invokeClient: &http.Client{}}
	res := srv.verifyWebSearch(context.Background(), up.URL, "sk-test-1")
	if res["verified"] != true {
		t.Fatalf("verified = %v, want true", res["verified"])
	}
	if gotAuth != "Bearer sk-test-1" {
		t.Errorf("keyed verify Authorization = %q, want 'Bearer sk-test-1'", gotAuth)
	}
}

func TestVerifyWebSearch_UnreachableEndpoint(t *testing.T) {
	srv := &Server{invokeClient: &http.Client{}}
	// 127.0.0.1:1 — nothing listens (mirrors a misconfigured `localhost` endpoint
	// that resolves to a dead loopback from inside the provider-registry container).
	res := srv.verifyWebSearch(context.Background(), "http://127.0.0.1:1", "")
	if res["verified"] != false {
		t.Fatalf("verified = %v, want false for an unreachable endpoint", res["verified"])
	}
	if res["error"] == nil || res["error"] == "" {
		t.Errorf("expected a non-empty error explaining the failure, got %v", res["error"])
	}
}
