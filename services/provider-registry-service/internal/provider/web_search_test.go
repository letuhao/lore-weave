package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// S5 — the web_search adapter is Tavily-shaped (POST {base}/search). These tests prove
// the wire shape + parsing WITHOUT a live key (the outward call is the only place an SDK
// would live; here it's a plain JSON POST so an httptest server is a faithful stand-in).

func TestWebSearch_ParsesTavilyResponse(t *testing.T) {
	var gotPath, gotAuth string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"answer":"Nezha is a protection deity.","results":[
			{"title":"Nezha","url":"https://ex.com/nezha","content":"A protection deity.","score":0.95},
			{"title":"Investiture","url":"https://ex.com/fsyy","content":"Appears in the novel.","score":0.8}
		]}`))
	}))
	defer srv.Close()

	results, answer, err := WebSearch(context.Background(), srv.Client(), srv.URL, "sk-test", "Nezha", WebSearchOptions{MaxResults: 5})
	if err != nil {
		t.Fatalf("WebSearch: %v", err)
	}
	if gotPath != "/search" {
		t.Errorf("path = %q, want /search", gotPath)
	}
	if gotAuth != "Bearer sk-test" {
		t.Errorf("auth = %q, want Bearer sk-test", gotAuth)
	}
	if gotBody["api_key"] != "sk-test" {
		t.Errorf("api_key not in body: %v", gotBody["api_key"])
	}
	if gotBody["query"] != "Nezha" {
		t.Errorf("query = %v", gotBody["query"])
	}
	if answer != "Nezha is a protection deity." {
		t.Errorf("answer = %q", answer)
	}
	if len(results) != 2 {
		t.Fatalf("want 2 results, got %d", len(results))
	}
	if results[0].URL != "https://ex.com/nezha" || results[0].Score != 0.95 || results[0].Title != "Nezha" {
		t.Errorf("result[0] = %+v", results[0])
	}
}

func TestWebSearch_ClampsAndDefaults(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&gotBody)
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer srv.Close()

	// MaxResults 0 → default 5; SearchDepth "" → "basic".
	if _, _, err := WebSearch(context.Background(), srv.Client(), srv.URL, "k", "q", WebSearchOptions{}); err != nil {
		t.Fatalf("err: %v", err)
	}
	if int(toFloat(gotBody["max_results"])) != 5 {
		t.Errorf("default max_results = %v, want 5", gotBody["max_results"])
	}
	if gotBody["search_depth"] != "basic" {
		t.Errorf("default depth = %v, want basic", gotBody["search_depth"])
	}

	// Over-cap clamps to 5; "advanced" respected.
	if _, _, err := WebSearch(context.Background(), srv.Client(), srv.URL, "k", "q", WebSearchOptions{MaxResults: 99, SearchDepth: "advanced"}); err != nil {
		t.Fatalf("err: %v", err)
	}
	if int(toFloat(gotBody["max_results"])) != 5 {
		t.Errorf("over-cap not clamped: %v", gotBody["max_results"])
	}
	if gotBody["search_depth"] != "advanced" {
		t.Errorf("advanced depth not respected: %v", gotBody["search_depth"])
	}
}

func TestWebSearch_TrimsTrailingSearchInBase(t *testing.T) {
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer srv.Close()
	// A base stored WITH a trailing /search must not become /search/search.
	if _, _, err := WebSearch(context.Background(), srv.Client(), srv.URL+"/search", "k", "q", WebSearchOptions{}); err != nil {
		t.Fatalf("err: %v", err)
	}
	if gotPath != "/search" {
		t.Errorf("path = %q, want /search (no double-search)", gotPath)
	}
}
