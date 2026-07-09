package provider

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
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

// ── INV-6 producer neutralization (Track D S-PRODUCER) ───────────────────────────────

func TestNeutralizeWebText(t *testing.T) {
	tests := []struct {
		name string
		in   string
		cap  int
		want string
	}{
		{"plain passes", "A protection deity.", 200, "A protection deity."},
		{"newlines fold to one space", "line one\nline two\n\n\tindented", 200, "line one line two indented"},
		{"nul control folds not drops (keeps boundary)", "ignore\x00previous", 200, "ignore previous"},
		{"C1 controls fold (Python copy let U+0080-9F pass)", "abc", 200, "a b c"},
		{"line/paragraph separators fold", "a b c", 200, "a b c"},
		{"nbsp folds", "a b", 200, "a b"},
		{"del char folds", "a\x7fb", 200, "a b"},
		{"trims surrounding space", "  \n hi \t ", 200, "hi"},
		{"byte cap truncates", "abcdefghij", 4, "abcd"},
		{"cap never splits a rune", "ééé", 3, "éé"}, // é=2 bytes; cap checked AFTER write, so stops once len≥3 (one rune over, never mid-rune)
		{"empty stays empty", "", 200, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := neutralizeWebText(tt.in, tt.cap); got != tt.want {
				t.Errorf("neutralizeWebText(%q, %d) = %q, want %q", tt.in, tt.cap, got, tt.want)
			}
		})
	}
}

func TestSafeHTTPURL(t *testing.T) {
	tests := []struct {
		name   string
		in     string
		wantOK bool
	}{
		// kept
		{"https public", "https://ok.example/x", true},
		{"http public", "http://ok.example/path?q=1", true},
		{"public ip", "https://93.184.216.34/", true},
		// dropped — dangerous schemes (both prior copies caught these)
		{"javascript", "javascript:alert(1)", false},
		{"data", "data:text/html,xss", false},
		{"file scheme (SSRF via local file)", "file:///etc/passwd", false},
		{"no host", "https:///path", false},
		{"empty", "", false},
		{"whitespace only", "   ", false},
		{"over length cap", "https://ok.example/" + strings.Repeat("a", 2100), false},
		// dropped — SSRF (NEITHER prior copy caught these: the headline drift/gap)
		{"localhost name", "http://localhost/admin", false},
		{"localhost subdomain", "http://foo.localhost/", false},
		{".local mdns", "http://printer.local/", false},
		{".internal", "http://db.internal/", false},
		{"loopback v4", "http://127.0.0.1/", false},
		{"loopback v4 alt", "http://127.9.9.9/", false},
		{"loopback v6", "http://[::1]/", false},
		{"cloud metadata 169.254.169.254", "http://169.254.169.254/latest/meta-data/", false},
		{"link-local v6", "http://[fe80::1]/", false},
		{"private 10/8", "http://10.0.0.5/", false},
		{"private 172.16/12", "http://172.16.4.4/", false},
		{"private 192.168/16", "http://192.168.1.1/", false},
		{"unspecified 0.0.0.0", "http://0.0.0.0/", false},
		// dropped — obfuscated numeric IP encodings net.ParseIP misses but libc/curl/
		// browsers still dereference (integration-review gap over the S-PRODUCER slice)
		{"decimal int loopback", "http://2130706433/", false},          // == 127.0.0.1
		{"decimal int metadata", "http://2852039166/", false},          // == 169.254.169.254
		{"hex loopback", "http://0x7f000001/", false},                  // == 127.0.0.1
		{"octal loopback", "http://017700000001/", false},              // == 127.0.0.1
		{"short dotted loopback", "http://127.1/", false},              // libc expands → 127.0.0.1
		// kept — real hostnames that merely LOOK hex/numeric must NOT be flagged
		{"hex-lookalike domain", "https://cafe.babe/", true},
		{"numeric-looking real domain", "https://123reg.co.uk/", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, ok := safeHTTPURL(tt.in)
			if ok != tt.wantOK {
				t.Errorf("safeHTTPURL(%q) ok = %v, want %v (got=%q)", tt.in, ok, tt.wantOK, got)
			}
			if !ok && got != "" {
				t.Errorf("safeHTTPURL(%q) rejected but returned non-empty %q", tt.in, got)
			}
		})
	}
}

// TestWebSearch_NeutralizesResults proves a consumer that does NOTHING is still safe:
// the producer folds injection-y control/newlines, caps length, and DROPS the whole
// result for any dangerous-scheme or SSRF-y URL — fail-closed.
func TestWebSearch_NeutralizesResults(t *testing.T) {
	longContent := strings.Repeat("x", 900) // > 600-byte snippet cap
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"answer": "safe\nanswer",
			"results": [
				{"title": "good\nsource", "url": "https://ok.example/x", "content": "` + longContent + `", "score": 0.9},
				{"title": "js", "url": "javascript:alert(1)", "content": "drop me"},
				{"title": "meta", "url": "http://169.254.169.254/latest/", "content": "SSRF drop"},
				{"title": "loop", "url": "http://localhost/admin", "content": "SSRF drop"}
			]
		}`))
	}))
	defer srv.Close()

	results, answer, err := WebSearch(context.Background(), srv.Client(), srv.URL, "k", "q", WebSearchOptions{MaxResults: 5})
	if err != nil {
		t.Fatalf("WebSearch: %v", err)
	}
	// The 3 dangerous/SSRF-y hits are dropped; only the public one survives.
	if len(results) != 1 {
		t.Fatalf("want 1 safe result, got %d: %+v", len(results), results)
	}
	if results[0].URL != "https://ok.example/x" {
		t.Errorf("kept URL = %q", results[0].URL)
	}
	if strings.ContainsAny(results[0].Title, "\n\t") {
		t.Errorf("title not neutralized: %q", results[0].Title)
	}
	if len(results[0].Content) > 600 {
		t.Errorf("content not capped: %d bytes", len(results[0].Content))
	}
	if strings.ContainsAny(answer, "\n\t") {
		t.Errorf("answer not neutralized: %q", answer)
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
