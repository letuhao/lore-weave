package billing

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
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

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, OpenRouterModelsURL, nil)
	if err != nil {
		return OpenRouterSuggestion{Found: false}
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return OpenRouterSuggestion{Found: false}
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return OpenRouterSuggestion{Found: false}
	}

	var parsed openRouterModelsResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return OpenRouterSuggestion{Found: false}
	}

	wantID := ns + "/" + modelName
	for _, m := range parsed.Data {
		if m.ID != wantID {
			continue
		}
		inTok, inOK := parsePerTokenToPerMTok(m.Pricing.Prompt)
		outTok, outOK := parsePerTokenToPerMTok(m.Pricing.Completion)
		if !inOK || !outOK {
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
