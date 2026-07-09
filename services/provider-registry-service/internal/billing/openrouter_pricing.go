package billing

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"sync"
	"time"
)

// D-PRICING-REFRESH — no LLM provider (OpenAI, Anthropic, Google) publishes a
// machine-readable pricing API; their rates exist only as human-readable web
// pages. OpenRouter (openrouter.ai), a third-party model-routing aggregator,
// DOES expose a public, unauthenticated live pricing catalog it keeps in sync
// because it resells those same models — the closest available "public
// pricing" source. This is best-effort by construction: a stale OpenRouter
// entry, a retired/unmapped model, or a network hiccup all resolve to
// "no suggestion" (OpenRouterSuggestion.Found=false), never an error the
// caller must handle specially, and the result is NEVER auto-applied — the
// caller (the pricing PATCH endpoint) only ever writes what the user
// explicitly confirms.

// openRouterNamespace maps our provider_kind to OpenRouter's model-id
// namespace prefix — best-effort, since OpenRouter's naming doesn't always
// match ours (e.g. they use "google" where we use "gemini"). A provider_kind
// absent from this map (every local BYOK kind, or an unrecognized cloud kind)
// has no OpenRouter equivalent to check.
var openRouterNamespace = map[string]string{
	"openai":    "openai",
	"anthropic": "anthropic",
	"gemini":    "google",
}

// OpenRouterModelsURL is a var (not const) so tests can point it at an
// httptest.Server; production always uses the default.
var OpenRouterModelsURL = "https://openrouter.ai/api/v1/models"

const openRouterTimeout = 8 * time.Second

// /review-impl MED#1 (2026-07-09): the full catalog is a few hundred KB and
// every "Check OpenRouter" click re-fetched it uncached — under real usage
// that's repeated unnecessary load on a third party we don't control, and a
// rate-limit/block on our egress IP would silently degrade the feature for
// EVERY user (every failure mode already resolves to Found:false by design).
// A short in-memory TTL cache removes the repeat-fetch cost entirely for the
// common case (checking a few models within a few minutes) while still
// picking up a genuine OpenRouter price change well within a session.
const openRouterCacheTTL = 10 * time.Minute

type openRouterCacheState struct {
	mu        sync.Mutex
	models    []openRouterModel
	fetchedAt time.Time
}

var openRouterCache openRouterCacheState

// fetchOpenRouterModels returns the cached catalog if still fresh, otherwise
// re-fetches and refreshes the cache. On a fetch/decode failure it serves a
// STALE-but-present cache rather than nothing (better than losing the feature
// entirely over a transient hiccup); only errors out when there's no cache at
// all yet. Every branch that degrades logs why (/review-impl MED#2) — the
// caller (FetchOpenRouterPricing) still only ever sees Found:false, never a
// hard error, but an operator can now tell "genuinely not on OpenRouter" apart
// from "OpenRouter's unreachable/changed shape" in the logs.
func fetchOpenRouterModels(ctx context.Context, httpClient *http.Client) ([]openRouterModel, error) {
	openRouterCache.mu.Lock()
	defer openRouterCache.mu.Unlock()

	if openRouterCache.models != nil && time.Since(openRouterCache.fetchedAt) < openRouterCacheTTL {
		return openRouterCache.models, nil
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, OpenRouterModelsURL, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		if openRouterCache.models != nil {
			slog.Warn("openrouter pricing: fetch failed, serving stale cache", "error", err, "cache_age", time.Since(openRouterCache.fetchedAt))
			return openRouterCache.models, nil
		}
		return nil, fmt.Errorf("fetch: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		if openRouterCache.models != nil {
			slog.Warn("openrouter pricing: non-200 response, serving stale cache", "status", resp.StatusCode)
			return openRouterCache.models, nil
		}
		return nil, fmt.Errorf("unexpected status %d", resp.StatusCode)
	}

	var parsed openRouterModelsResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		if openRouterCache.models != nil {
			slog.Warn("openrouter pricing: malformed response body, serving stale cache", "error", err)
			return openRouterCache.models, nil
		}
		return nil, fmt.Errorf("decode: %w", err)
	}

	openRouterCache.models = parsed.Data
	openRouterCache.fetchedAt = time.Now()
	return openRouterCache.models, nil
}

// openRouterModel is the subset of OpenRouter's `/api/v1/models` response
// entry we read. Pricing values are USD PER TOKEN, encoded as JSON STRINGS
// (e.g. `"0.0000025"`, confirmed live 2026-07-09) — not numbers, and not
// per-million — hence string fields decoded with strconv, not float64.
type openRouterModel struct {
	ID      string `json:"id"`
	Pricing struct {
		Prompt     string `json:"prompt"`
		Completion string `json:"completion"`
	} `json:"pricing"`
}

type openRouterModelsResponse struct {
	Data []openRouterModel `json:"data"`
}

// OpenRouterSuggestion is the best-effort live-pricing suggestion surfaced to
// the user for review — never authoritative, never persisted automatically.
type OpenRouterSuggestion struct {
	Found bool `json:"found"`
	// SourceModelID is the OpenRouter model id actually matched (e.g.
	// "openai/gpt-4o"), surfaced so the user can see exactly what was compared.
	SourceModelID string   `json:"source_model_id,omitempty"`
	Pricing       *Pricing `json:"pricing,omitempty"`
}

// FetchOpenRouterPricing best-effort looks up a (provider_kind, model_name)'s
// live per-token rate from OpenRouter's public catalog. Every failure mode —
// an unmapped provider_kind, a network error, a non-200 response, a malformed
// body, or simply no matching model id — resolves to `{Found: false}`; this
// must never hard-fail the caller (a missing/stale third-party catalog entry
// is not a reason to break the pricing-edit flow it's only assisting).
func FetchOpenRouterPricing(ctx context.Context, httpClient *http.Client, providerKind, modelName string) OpenRouterSuggestion {
	ns, ok := openRouterNamespace[providerKind]
	if !ok {
		return OpenRouterSuggestion{Found: false}
	}
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	ctx, cancel := context.WithTimeout(ctx, openRouterTimeout)
	defer cancel()

	models, err := fetchOpenRouterModels(ctx, httpClient)
	if err != nil {
		// /review-impl MED#2 — the only branch with no cache to fall back on
		// (first-ever call, or the cache was never populated). Every other
		// degrade path already logged inside fetchOpenRouterModels.
		slog.Warn("openrouter pricing: catalog unavailable", "provider_kind", providerKind, "model_name", modelName, "error", err)
		return OpenRouterSuggestion{Found: false}
	}

	wantID := ns + "/" + modelName
	for _, m := range models {
		if m.ID != wantID {
			continue
		}
		inTok, inOK := parsePerTokenToPerMTok(m.Pricing.Prompt)
		outTok, outOK := parsePerTokenToPerMTok(m.Pricing.Completion)
		if !inOK || !outOK {
			slog.Warn("openrouter pricing: matched model has unparseable price fields", "model_id", m.ID)
			return OpenRouterSuggestion{Found: false}
		}
		p := textPricing(inTok, outTok)
		return OpenRouterSuggestion{Found: true, SourceModelID: m.ID, Pricing: &p}
	}
	return OpenRouterSuggestion{Found: false}
}

// parsePerTokenToPerMTok converts an OpenRouter USD-per-TOKEN string to
// USD-per-MILLION-tokens — our stored unit, matching defaultPriceTable's
// convention (verified live: OpenAI gpt-4o's "0.0000025"/"0.00001" convert to
// 2.50/10.00, matching this table's own hand-curated defaults exactly).
func parsePerTokenToPerMTok(raw string) (float64, bool) {
	if raw == "" {
		return 0, false
	}
	v, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, false
	}
	return v * 1_000_000, true
}
