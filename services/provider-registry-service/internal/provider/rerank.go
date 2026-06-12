package provider

import (
	"context"
	"fmt"
	"net/http"
	"sort"
	"strings"
)

// RerankResult is one scored document, by index into the request `documents`.
type RerankResult struct {
	Index int     `json:"index"`
	Score float64 `json:"relevance_score"`
}

// Rerank scores `documents` against `query` via a Cohere-compatible rerank
// service (see docs/integrations/2026-06-08-rerank-service-integration.md).
// Unlike Embed it is NOT adapter-dispatched: the rerank service has a single
// known API shape, and it's a platform service (URL+token from config), not a
// per-user BYOK provider. Results are returned sorted by Score descending.
func Rerank(ctx context.Context, client *http.Client, baseURL, token, model, query string, documents []string) ([]RerankResult, error) {
	// Strip a trailing /v1 so a base stored as "http://host:port/v1" doesn't
	// produce /v1/v1/rerank (mirrors embedOpenAI).
	base := strings.TrimRight(baseURL, "/")
	base = strings.TrimSuffix(base, "/v1")
	headers := map[string]string{}
	if token != "" {
		headers["Authorization"] = "Bearer " + token
	}
	payload := map[string]any{
		"model":     model,
		"query":     query,
		"documents": documents,
	}
	out, err := postJSON(ctx, client, base+"/v1/rerank", headers, payload)
	if err != nil {
		return nil, fmt.Errorf("rerank call failed: %w", err)
	}
	raw, ok := out["results"].([]any)
	if !ok {
		return nil, fmt.Errorf("no results in rerank response")
	}
	results := make([]RerankResult, 0, len(raw))
	for _, item := range raw {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		results = append(results, RerankResult{
			Index: int(toFloat(entry["index"])),
			Score: toFloat(entry["relevance_score"]),
		})
	}
	if len(results) == 0 {
		return nil, fmt.Errorf("no valid rerank results parsed")
	}
	// Defensive: guarantee descending order regardless of upstream ordering.
	sort.SliceStable(results, func(i, j int) bool { return results[i].Score > results[j].Score })
	return results, nil
}
