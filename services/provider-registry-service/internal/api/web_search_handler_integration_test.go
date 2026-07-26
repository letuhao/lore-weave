package api

// S5 — DB-seeded resolution test for internalWebSearch (D-S5-WEBSEARCH-HANDLER-TEST).
// The adapter (provider.WebSearch) is unit-tested; this covers the HANDLER's BYOK
// RESOLUTION layer end-to-end against real Postgres:
//   - the KEYLESS path (the bug the S5 live-smoke fixed): a web_search credential with an
//     EMPTY secret_ciphertext (a self-hosted SearXNG-style backend) must resolve and call
//     the upstream WITHOUT an Authorization header — not 500 on a decrypt of "" ;
//   - the keyed path: a real secret decrypts and rides as `Authorization: Bearer …`, so an
//     empty ciphertext is genuinely the only thing that skips the header;
//   - the STRICT capability gate: web_search is never defaulted from '{}'/chat the way chat
//     is — a user whose only model is chat-capable gets 404, not a silent search.
// Requires TEST_PROVIDER_REGISTRY_DB_URL (see integrationServer); skips otherwise.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// wsUpstream captures what the Tavily-shaped upstream actually received, so the test can
// assert the resolved secret rode (or didn't) into the outward call.
type wsUpstream struct {
	path       string
	authHeader string
	apiKeyBody string
}

func newWebSearchUpstream(t *testing.T) (*httptest.Server, *wsUpstream) {
	t.Helper()
	cap := &wsUpstream{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.path = r.URL.Path
		cap.authHeader = r.Header.Get("Authorization")
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		cap.apiKeyBody, _ = body["api_key"].(string)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"answer":"ans","results":[
			{"title":"T1","url":"https://ex.com/1","content":"c1","score":0.9}
		]}`))
	}))
	t.Cleanup(srv.Close)
	return srv, cap
}

// seedWebSearchModel inserts a BYOK credential (endpoint + optional secret) + one
// user_model carrying the given capability_flags. plaintextSecret="" seeds the keyless
// case (an empty secret_ciphertext). Both rows are cleaned up.
func seedWebSearchModel(t *testing.T, srv *Server, pool *pgxpool.Pool, owner uuid.UUID, endpoint, plaintextSecret, capabilityFlags string) {
	t.Helper()
	ctx := context.Background()
	cipher := ""
	if plaintextSecret != "" {
		c, _, err := srv.encryptSecret(plaintextSecret)
		if err != nil {
			t.Fatalf("encryptSecret: %v", err)
		}
		cipher = c
	}
	var credID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO provider_credentials (owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, status)
VALUES ($1,'lm_studio','websearch-test',$2,$3,'active')
RETURNING provider_credential_id`, owner, endpoint, cipher).Scan(&credID); err != nil {
		t.Fatalf("seed provider_credentials: %v", err)
	}
	var modelID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO user_models (owner_user_id, provider_credential_id, provider_kind, provider_model_name, is_active, capability_flags)
VALUES ($1,$2,'lm_studio','searxng-default',true,$3::jsonb)
RETURNING user_model_id`, owner, credID, capabilityFlags).Scan(&modelID); err != nil {
		t.Fatalf("seed user_models: %v", err)
	}
	t.Cleanup(func() {
		bg := context.Background()
		_, _ = pool.Exec(bg, `DELETE FROM user_models WHERE user_model_id=$1`, modelID)
		_, _ = pool.Exec(bg, `DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credID)
	})
}

func callWebSearch(t *testing.T, srv *Server, owner uuid.UUID, query string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"query": query, "max_results": 3})
	req := httptest.NewRequest(http.MethodPost, "/internal/web-search?user_id="+owner.String(), bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	srv.internalWebSearch(rr, req)
	return rr
}

func TestInternalWebSearch_KeylessResolves(t *testing.T) {
	srv, pool := integrationServer(t)
	up, cap := newWebSearchUpstream(t)
	owner := uuid.New()
	// Keyless backend: empty secret_ciphertext + the web_search capability flag.
	seedWebSearchModel(t, srv, pool, owner, up.URL, "", `{"web_search": true}`)

	rr := callWebSearch(t, srv, owner, "Nezha")
	if rr.Code != http.StatusOK {
		t.Fatalf("keyless web search: want 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	var out struct {
		ProviderModel string `json:"provider_model"`
		Results       []struct {
			URL string `json:"url"`
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (%s)", err, rr.Body.String())
	}
	if out.ProviderModel != "searxng-default" || len(out.Results) != 1 || out.Results[0].URL != "https://ex.com/1" {
		t.Fatalf("unexpected result: %+v", out)
	}
	// The crux: a keyless credential must reach the upstream with NO Authorization header
	// (and an empty api_key body) — the handler must NOT 500 trying to decrypt "".
	if cap.path != "/search" {
		t.Errorf("upstream path = %q, want /search", cap.path)
	}
	if cap.authHeader != "" {
		t.Errorf("keyless call sent Authorization=%q, want none", cap.authHeader)
	}
	if cap.apiKeyBody != "" {
		t.Errorf("keyless call sent api_key=%q, want empty", cap.apiKeyBody)
	}
}

func TestInternalWebSearch_KeyedSendsBearer(t *testing.T) {
	srv, pool := integrationServer(t)
	up, cap := newWebSearchUpstream(t)
	owner := uuid.New()
	// Keyed backend: a real secret must decrypt and ride as Authorization: Bearer <secret>.
	seedWebSearchModel(t, srv, pool, owner, up.URL, "sk-live-123", `{"web_search": true}`)

	rr := callWebSearch(t, srv, owner, "Nezha")
	if rr.Code != http.StatusOK {
		t.Fatalf("keyed web search: want 200, got %d (%s)", rr.Code, rr.Body.String())
	}
	if cap.authHeader != "Bearer sk-live-123" {
		t.Errorf("keyed call Authorization = %q, want 'Bearer sk-live-123'", cap.authHeader)
	}
	if cap.apiKeyBody != "sk-live-123" {
		t.Errorf("keyed call api_key body = %q, want 'sk-live-123'", cap.apiKeyBody)
	}
}

func TestInternalWebSearch_StrictCapabilityGate(t *testing.T) {
	srv, pool := integrationServer(t)
	up, _ := newWebSearchUpstream(t)
	owner := uuid.New()
	// The user's only model is chat-capable — web_search must NOT be defaulted from it.
	seedWebSearchModel(t, srv, pool, owner, up.URL, "k", `{"chat": true}`)

	rr := callWebSearch(t, srv, owner, "Nezha")
	if rr.Code != http.StatusNotFound {
		t.Fatalf("chat-only user: want 404 (web_search not configured), got %d (%s)", rr.Code, rr.Body.String())
	}
}
