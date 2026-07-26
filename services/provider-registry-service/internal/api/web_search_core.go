package api

// Track D · WS-D0 Wave 2 (S-WEB) — the ONE web-search pipeline.
//
// `web_search` now has two transports: the `/internal/web-search` HTTP route (called by
// glossary-Go and composition-Py) and the universal `web_search` MCP tool registered on
// this service's own MCP server. Both go through runWebSearch, which owns the whole
// pipeline: resolve the caller's BYOK web_search model → decrypt (or not, for a keyless
// backend) → provider.WebSearch (the sole outward HTTP call, already INV-6 neutralized)
// → recordSyncUsage audit.
//
// A third consumer MUST reuse this, never re-derive it. The triplicated neutralization
// this wave deleted (glossary-Go / composition-Py / here) is exactly what happens when a
// consumer copies the pipeline instead of calling it: three copies, three different holes.

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// Sentinel errors — each transport maps these to its own idiom (HTTP status vs MCP
// error string) without either one owning the failure taxonomy.
var (
	errWebSearchNoModel    = errors.New("no active web_search model configured")
	errWebSearchModelQuery = errors.New("failed to resolve web_search model")
	errWebSearchSecret     = errors.New("failed to decrypt web_search secret")
	errWebSearchUpstream   = errors.New("web search provider error")
)

// webSearchOutcome is the successful result of a web search, identical for both transports.
type webSearchOutcome struct {
	ProviderModel string
	Answer        string
	Results       []provider.WebSearchResult
}

// runWebSearch resolves the user's preferred active web_search model (BYOK), runs the
// search, and audits the call. owner_user_id=$1 guarantees tenant isolation. The
// web_search capability is STRICT: the model must be explicitly flagged (boolean
// {"web_search":true} or legacy _capability), never defaulted from '{}' the way chat is.
//
// Results come back already neutralized (INV-6) — provider.WebSearch caps + folds control
// and whitespace runes and drops SSRF-y / non-http(s) URLs — so a consumer that does
// nothing is still safe.
func (s *Server) runWebSearch(
	ctx context.Context, userID uuid.UUID, query string, maxResults int, searchDepth string,
) (webSearchOutcome, error) {
	var providerModelName, endpointBaseURL, secretCipher string
	var modelRef uuid.UUID // resolved model id — carried into the usage audit row (P0-2 B4)
	err := s.pool.QueryRow(ctx, `
SELECT um.user_model_id, um.provider_model_name, COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.owner_user_id=$1 AND um.is_active=true AND pc.status='active'
  AND (um.capability_flags @> '{"web_search": true}'::jsonb
       OR um.capability_flags->>'_capability' = 'web_search')
ORDER BY um.is_favorite DESC, um.created_at ASC
LIMIT 1
`, userID).Scan(&modelRef, &providerModelName, &endpointBaseURL, &secretCipher)
	if errors.Is(err, pgx.ErrNoRows) {
		return webSearchOutcome{}, errWebSearchNoModel
	}
	if err != nil {
		return webSearchOutcome{}, errWebSearchModelQuery
	}

	// A KEYLESS local web-search backend (e.g. self-hosted SearXNG) legitimately has NO
	// secret — the §8 contract explicitly supports an empty credential ("Authorization
	// ignored"). So unlike rerank/embed (platform services that require a token), an empty
	// ciphertext is valid here: pass an empty secret (the adapter omits the Authorization
	// header). Decrypt only when a secret is actually set.
	secret := ""
	if secretCipher != "" {
		decrypted, derr := s.decryptSecret(secretCipher)
		if derr != nil {
			return webSearchOutcome{}, errWebSearchSecret
		}
		secret = decrypted
	}

	results, answer, err := provider.WebSearch(ctx, s.invokeClient, endpointBaseURL, secret, query,
		provider.WebSearchOptions{MaxResults: maxResults, SearchDepth: searchDepth})

	// P0-2 (B4) — audit BOTH outcomes: query + options in, answer + results out. Web search
	// carries no token usage → tokens 0. MED-1: the failed call is audited too.
	auditIn := map[string]any{"query": query, "max_results": maxResults, "search_depth": searchDepth}
	if err != nil {
		s.recordSyncUsage(ctx, userID, modelRef, "web_search", "provider_error", 0, 0, nil,
			auditIn, map[string]any{"error": err.Error()})
		return webSearchOutcome{}, errWebSearchUpstream
	}
	s.recordSyncUsage(ctx, userID, modelRef, "web_search", "success", 0, 0, nil,
		auditIn, map[string]any{"answer": answer, "results": results})

	return webSearchOutcome{ProviderModel: providerModelName, Answer: answer, Results: results}, nil
}
