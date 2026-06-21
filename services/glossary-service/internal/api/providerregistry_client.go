package api

// S5 — glossary → provider-registry internal client for the BYOK web-search capability.
// The outward web-search HTTP call lives ONLY in provider-registry (provider-gateway
// invariant); glossary reaches it service-to-service via X-Internal-Token, exactly like
// it calls book-service. The user's web_search model/key is resolved BY provider-registry
// from the passed user_id — glossary never holds a search key.

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/observability"
)

// Web search can take a few seconds (advanced depth fetches pages) — a longer timeout
// than the 5s book client, still bounded to prevent goroutine leaks.
var providerRegistryHTTPClient = &http.Client{Timeout: 20 * time.Second, Transport: observability.HTTPTransport(nil)}

type webSearchResult struct {
	Title   string  `json:"title"`
	URL     string  `json:"url"`
	Content string  `json:"content"`
	Score   float64 `json:"score"`
}

// errWebSearchNotConfigured — provider-registry has no web_search model for the user, OR
// glossary has no PROVIDER_REGISTRY_URL. Surfaced to the agent as a clear "add a
// web-search credential / not configured" message (not a generic 500).
var errWebSearchNotConfigured = errors.New("web search is not configured")

// webSearch runs one BYOK web search for `userID` via provider-registry. Returns the
// ranked results + the provider's optional synthesized answer. The result `Content` is
// UNTRUSTED external text — the CALLER neutralizes it before it lands as evidence or is
// returned to the agent (INV-6).
func (s *Server) webSearch(ctx context.Context, userID uuid.UUID, query string, maxResults int) ([]webSearchResult, string, error) {
	base := strings.TrimRight(s.cfg.ProviderRegistryURL, "/")
	if base == "" {
		return nil, "", errWebSearchNotConfigured
	}
	endpoint := fmt.Sprintf("%s/internal/web-search?user_id=%s", base, url.QueryEscape(userID.String()))
	body, _ := json.Marshal(map[string]any{"query": query, "max_results": maxResults})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := providerRegistryHTTPClient.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("web search unreachable: %w", err)
	}
	defer res.Body.Close()
	// 404 = the user has no web_search model configured — a clear, actionable state, not
	// an internal error.
	if res.StatusCode == http.StatusNotFound {
		return nil, "", errWebSearchNotConfigured
	}
	if res.StatusCode != http.StatusOK {
		return nil, "", fmt.Errorf("web search provider error (status %d)", res.StatusCode)
	}
	var out struct {
		Answer  string            `json:"answer"`
		Results []webSearchResult `json:"results"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, "", fmt.Errorf("web search bad response: %w", err)
	}
	return out.Results, out.Answer, nil
}
