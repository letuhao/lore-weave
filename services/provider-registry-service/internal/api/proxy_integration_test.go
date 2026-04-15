package api

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/migrate"
)

// K17.2c — live-pool integration tests for doProxy (the HTTP wiring
// around rewriteJSONBodyModel). These tests seed provider_credentials
// and user_models rows against a real Postgres and fire real HTTP
// through doProxy against an httptest upstream. They are skipped when
// TEST_PROVIDER_REGISTRY_DB_URL is unset so a laptop workflow without
// compose running still passes.
//
// The tests use the compose Postgres (see infra/docker-compose.yml)
// via the DSN in TEST_PROVIDER_REGISTRY_DB_URL, e.g.
//   postgres://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry?sslmode=disable
//
// Each test scopes its seed rows to a fresh uuid user_id and DELETEs
// them in a t.Cleanup — this lets tests run in parallel against the
// same DB without stepping on each other.

const integrationJWTSecret = "integration-test-secret-32-chars-01"

func integrationServer(t *testing.T) (*Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("TEST_PROVIDER_REGISTRY_DB_URL")
	if dsn == "" {
		t.Skip("TEST_PROVIDER_REGISTRY_DB_URL unset — skipping integration test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	if err := migrate.Up(ctx, pool); err != nil {
		pool.Close()
		t.Fatalf("migrate.Up: %v", err)
	}
	srv := NewServer(pool, &config.Config{
		JWTSecret:              integrationJWTSecret,
		UsageBillingServiceURL: "http://localhost:8086",
		InternalServiceToken:   "integration-internal-token",
	})
	t.Cleanup(func() { pool.Close() })
	return srv, pool
}

// seedUserModel creates a provider_credentials row pointing at
// endpointBaseURL (the httptest upstream), then a user_models row
// linked to it. Returns the user_id and user_model_id to use in the
// request params. Both rows are deleted in t.Cleanup.
func seedUserModel(
	t *testing.T,
	srv *Server,
	pool *pgxpool.Pool,
	endpointBaseURL, providerModelName, plaintextSecret string,
) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	userID := uuid.New()

	cipher, _, err := srv.encryptSecret(plaintextSecret)
	if err != nil {
		t.Fatalf("encryptSecret: %v", err)
	}

	var credentialID uuid.UUID
	err = pool.QueryRow(ctx, `
		INSERT INTO provider_credentials (
			owner_user_id, provider_kind, display_name,
			endpoint_base_url, secret_ciphertext, status
		) VALUES ($1, 'openai', 'test-cred', $2, $3, 'active')
		RETURNING provider_credential_id
	`, userID, endpointBaseURL, cipher).Scan(&credentialID)
	if err != nil {
		t.Fatalf("insert credential: %v", err)
	}

	var userModelID uuid.UUID
	err = pool.QueryRow(ctx, `
		INSERT INTO user_models (
			owner_user_id, provider_credential_id,
			provider_kind, provider_model_name, is_active
		) VALUES ($1, $2, 'openai', $3, true)
		RETURNING user_model_id
	`, userID, credentialID, providerModelName).Scan(&userModelID)
	if err != nil {
		t.Fatalf("insert user_model: %v", err)
	}

	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM user_models WHERE user_model_id=$1`, userModelID)
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credentialID)
	})

	return userID, userModelID
}

// buildProxyRequest constructs an http.Request shaped like an
// internalProxy call, with the chi URLParam "*" set to targetPath.
func buildProxyRequest(t *testing.T, method, targetPath string, body []byte, contentType string) *http.Request {
	t.Helper()
	var bodyReader io.Reader
	if body != nil {
		bodyReader = bytes.NewReader(body)
	}
	req := httptest.NewRequest(method, "/internal/proxy/"+targetPath, bodyReader)
	if body != nil {
		req.ContentLength = int64(len(body))
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	// Wire the chi URLParam for "*" so chi.URLParam(r, "*") returns targetPath.
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("*", targetPath)
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
	return req
}

// ── Tests ────────────────────────────────────────────────────────────

func TestDoProxyRewritesJSONModelField(t *testing.T) {
	srv, pool := integrationServer(t)

	// Capture what the upstream sees so we can assert the rewrite happened.
	var capturedBody []byte
	var capturedPath string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedBody, _ = io.ReadAll(r.Body)
		capturedPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "gpt-4-real", "sk-test")

	clientBody := []byte(`{"model":"client-sent-this","messages":[{"role":"user","content":"hi"}],"temperature":0.3}`)
	req := buildProxyRequest(t, "POST", "v1/chat/completions", clientBody, "application/json")

	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}

	// Upstream path should be {base}/v1/chat/completions.
	if capturedPath != "/v1/chat/completions" {
		t.Errorf("upstream path = %q, want /v1/chat/completions", capturedPath)
	}

	// The rewritten body should have model="gpt-4-real", not "client-sent-this".
	var forwarded map[string]any
	if err := json.Unmarshal(capturedBody, &forwarded); err != nil {
		t.Fatalf("upstream body not JSON: %v body=%s", err, capturedBody)
	}
	if forwarded["model"] != "gpt-4-real" {
		t.Errorf("forwarded model = %v, want gpt-4-real", forwarded["model"])
	}
	if _, ok := forwarded["messages"]; !ok {
		t.Errorf("forwarded body lost messages: %v", forwarded)
	}
	if forwarded["temperature"] != 0.3 {
		t.Errorf("forwarded body lost temperature: %v", forwarded["temperature"])
	}
}

func TestDoProxyForwardsAuthorizationHeader(t *testing.T) {
	srv, pool := integrationServer(t)

	var capturedAuth string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "gpt-4", "sk-secret-123")

	req := buildProxyRequest(t, "POST", "v1/chat/completions",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rr.Code)
	}
	if capturedAuth != "Bearer sk-secret-123" {
		t.Errorf("upstream Authorization = %q, want Bearer sk-secret-123", capturedAuth)
	}
}

func TestDoProxyBodyTooLargeRejected(t *testing.T) {
	srv, pool := integrationServer(t)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("upstream should not be called — request should be rejected at the 4MiB cap")
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "gpt-4", "sk-test")

	// Build a > 4MiB JSON body.
	big := make([]byte, 4*1024*1024+100)
	for i := range big {
		big[i] = 'a'
	}
	body := []byte(`{"model":"x","messages":[{"role":"user","content":"`)
	body = append(body, big...)
	body = append(body, []byte(`"}]}`)...)

	req := buildProxyRequest(t, "POST", "v1/chat/completions", body, "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("expected 413, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_BODY_TOO_LARGE") {
		t.Errorf("expected error code PROXY_BODY_TOO_LARGE in body, got %s", rr.Body.String())
	}
}

func TestDoProxyInvalidJSONRejected(t *testing.T) {
	srv, pool := integrationServer(t)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("upstream should not be called — invalid JSON should be rejected before forwarding")
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "gpt-4", "sk-test")

	req := buildProxyRequest(t, "POST", "v1/chat/completions",
		[]byte(`not valid json at all`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_INVALID_JSON_BODY") {
		t.Errorf("expected error code PROXY_INVALID_JSON_BODY in body, got %s", rr.Body.String())
	}
}

func TestDoProxyNonJSONPassthrough(t *testing.T) {
	srv, pool := integrationServer(t)

	var capturedBody []byte
	var capturedCT string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedBody, _ = io.ReadAll(r.Body)
		capturedCT = r.Header.Get("Content-Type")
		w.WriteHeader(200)
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "whisper-1", "sk-test")

	// Simulate a multipart audio body — our rewrite code MUST NOT
	// touch this. We use a simple non-JSON payload for the assertion.
	raw := []byte("--boundary\r\nContent-Disposition: form-data; name=\"x\"\r\n\r\nhello\r\n--boundary--\r\n")
	req := buildProxyRequest(t, "POST", "v1/audio/transcriptions", raw,
		"multipart/form-data; boundary=boundary")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != 200 {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !bytes.Equal(capturedBody, raw) {
		t.Errorf("non-JSON body was mutated:\ngot  %q\nwant %q", capturedBody, raw)
	}
	if !strings.HasPrefix(capturedCT, "multipart/form-data") {
		t.Errorf("upstream Content-Type = %q, want multipart/form-data*", capturedCT)
	}
}

func TestDoProxyUserModelWithEmptyCredentialRejected(t *testing.T) {
	// K17.2a-R3 (C10): user_model referencing a credential with an
	// empty secret_ciphertext should fail fast with
	// PROXY_MISSING_CREDENTIAL rather than silently forwarding an
	// anonymous request upstream.
	srv, pool := integrationServer(t)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("upstream should not be called — credential is empty")
	}))
	t.Cleanup(upstream.Close)

	// Seed manually with an empty ciphertext.
	ctx := context.Background()
	userID := uuid.New()
	var credentialID uuid.UUID
	err := pool.QueryRow(ctx, `
		INSERT INTO provider_credentials (
			owner_user_id, provider_kind, display_name,
			endpoint_base_url, secret_ciphertext, status
		) VALUES ($1, 'openai', 'empty-cred', $2, '', 'active')
		RETURNING provider_credential_id
	`, userID, upstream.URL).Scan(&credentialID)
	if err != nil {
		t.Fatalf("insert credential: %v", err)
	}
	var userModelID uuid.UUID
	err = pool.QueryRow(ctx, `
		INSERT INTO user_models (
			owner_user_id, provider_credential_id,
			provider_kind, provider_model_name, is_active
		) VALUES ($1, $2, 'openai', 'gpt-4', true)
		RETURNING user_model_id
	`, userID, credentialID).Scan(&userModelID)
	if err != nil {
		t.Fatalf("insert user_model: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM user_models WHERE user_model_id=$1`, userModelID)
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM provider_credentials WHERE provider_credential_id=$1`, credentialID)
	})

	req := buildProxyRequest(t, "POST", "v1/chat/completions",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_MISSING_CREDENTIAL") {
		t.Errorf("expected error code PROXY_MISSING_CREDENTIAL in body, got %s", rr.Body.String())
	}
}

func TestDoProxyModelNotFound(t *testing.T) {
	srv, _ := integrationServer(t)

	// No seed — a random UUID won't resolve.
	userID := uuid.New()
	randomModelID := uuid.New()

	req := buildProxyRequest(t, "POST", "v1/chat/completions",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", randomModelID.String())

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_MODEL_NOT_FOUND") {
		t.Errorf("expected error code PROXY_MODEL_NOT_FOUND in body, got %s", rr.Body.String())
	}
}
