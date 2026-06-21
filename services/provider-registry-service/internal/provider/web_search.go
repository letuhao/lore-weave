package provider

import (
	"context"
	"fmt"
	"net/http"
	"strings"
)

// WebSearchResult is one ranked web result from a BYOK web-search provider.
type WebSearchResult struct {
	Title   string  `json:"title"`
	URL     string  `json:"url"`
	Content string  `json:"content"`
	Score   float64 `json:"score"`
}

// WebSearchOptions tunes a search call.
type WebSearchOptions struct {
	MaxResults  int    // clamped to 1..20 (default 5)
	SearchDepth string // "basic" (default) | "advanced"
}

// WebSearch runs a web search via a Tavily-compatible API (POST {base}/search).
// Like Rerank it receives a RESOLVED endpointBaseURL + secret (BYOK) — no SDK, no
// config. This is the ONLY place the outward web-search HTTP call lives
// (provider-gateway invariant). Returns the ranked results + the provider's optional
// synthesized answer. The result `Content` is UNTRUSTED external text — the caller
// MUST neutralize it before it touches a prompt or lands as evidence (INV-6 / S24).
func WebSearch(ctx context.Context, client *http.Client, endpointBaseURL, secret, query string, opts WebSearchOptions) ([]WebSearchResult, string, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = "https://api.tavily.com"
	}
	// Tolerate a base stored with a trailing /search so we don't post to /search/search.
	base = strings.TrimSuffix(base, "/search")

	maxResults := opts.MaxResults
	if maxResults <= 0 || maxResults > 20 {
		maxResults = 5
	}
	depth := opts.SearchDepth
	if depth != "advanced" {
		depth = "basic"
	}

	headers := map[string]string{}
	if secret != "" {
		// Modern Tavily accepts a Bearer token; the api_key body field below keeps
		// older / self-hosted Tavily-compatible endpoints working too.
		headers["Authorization"] = "Bearer " + secret
	}
	payload := map[string]any{
		"api_key":        secret,
		"query":          query,
		"max_results":    maxResults,
		"search_depth":   depth,
		"include_answer": true,
	}
	out, err := postJSON(ctx, client, base+"/search", headers, payload)
	if err != nil {
		return nil, "", fmt.Errorf("web search call failed: %w", err)
	}
	answer, _ := out["answer"].(string)
	raw, _ := out["results"].([]any)
	results := make([]WebSearchResult, 0, len(raw))
	for _, item := range raw {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		results = append(results, WebSearchResult{
			Title:   wsString(entry["title"]),
			URL:     wsString(entry["url"]),
			Content: wsString(entry["content"]),
			Score:   toFloat(entry["score"]),
		})
	}
	return results, answer, nil
}

func wsString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
