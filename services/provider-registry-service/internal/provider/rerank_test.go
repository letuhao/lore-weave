package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRerank_ParsesAndSortsDescending(t *testing.T) {
	var gotAuth, gotPath string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotPath = r.URL.Path
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		// return out-of-order to prove the helper sorts
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"results":[{"index":1,"relevance_score":0.10},{"index":0,"relevance_score":0.90}]}`))
	}))
	defer srv.Close()

	res, err := Rerank(context.Background(), srv.Client(), srv.URL, "tok", "bge", "q", []string{"a", "b"})
	if err != nil {
		t.Fatalf("Rerank err: %v", err)
	}
	if gotPath != "/v1/rerank" {
		t.Fatalf("path = %q, want /v1/rerank", gotPath)
	}
	if gotAuth != "Bearer tok" {
		t.Fatalf("auth = %q, want Bearer tok", gotAuth)
	}
	if gotBody["model"] != "bge" || gotBody["query"] != "q" {
		t.Fatalf("body model/query mismatch: %v", gotBody)
	}
	if len(res) != 2 || res[0].Index != 0 || res[0].Score != 0.90 {
		t.Fatalf("results not sorted desc: %+v", res)
	}
}

func TestRerank_TrimsTrailingV1(t *testing.T) {
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		_, _ = w.Write([]byte(`{"results":[{"index":0,"relevance_score":0.5}]}`))
	}))
	defer srv.Close()
	// base already ends in /v1 → must not become /v1/v1/rerank
	if _, err := Rerank(context.Background(), srv.Client(), srv.URL+"/v1", "", "m", "q", []string{"d"}); err != nil {
		t.Fatalf("err: %v", err)
	}
	if gotPath != "/v1/rerank" {
		t.Fatalf("path = %q, want /v1/rerank (no double /v1)", gotPath)
	}
}

func TestRerank_EmptyResultsErrors(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer srv.Close()
	if _, err := Rerank(context.Background(), srv.Client(), srv.URL, "", "m", "q", []string{"d"}); err == nil {
		t.Fatal("expected error on empty results")
	}
}
