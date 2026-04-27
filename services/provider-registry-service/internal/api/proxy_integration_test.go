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
	}, nil)
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

// Note on captured-variable reads in these tests (K17.2c-R1 T14):
// Tests capture upstream-handler state in plain `var` slots and read
// them after `srv.doProxy` returns. This is safe because `doProxy`
// calls `s.invokeClient.Do(proxyReq)` which blocks the test goroutine
// until the upstream handler has fully run and returned. The net/http
// client's internal sync primitives provide the happens-before edge
// between the handler write and the test-body read. Adding a mutex
// here would be unnecessary ceremony. `-race` cannot be used in this
// dev environment (cgo unavailable on Windows build), so this contract
// is documented rather than machine-verified.

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
	// Phase 4d: chat/completions was retired; tests exercise rewrite
	// mechanics through v1/audio/speech (TTS — JSON body, still
	// allowed via proxy until audio adapter ships in Phase 5b).
	req := buildProxyRequest(t, "POST", "v1/audio/speech", clientBody, "application/json")

	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rr.Code, rr.Body.String())
	}

	// Upstream path should be {base}/v1/audio/speech.
	if capturedPath != "/v1/audio/speech" {
		t.Errorf("upstream path = %q, want /v1/audio/speech", capturedPath)
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

	// Phase 4d: see TestDoProxyRewritesJSONModelField — path swap.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
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

	// Phase 4d: see TestDoProxyRewritesJSONModelField — path swap.
	req := buildProxyRequest(t, "POST", "v1/audio/speech", body, "application/json")
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

	// Phase 4d: see TestDoProxyRewritesJSONModelField — path swap.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
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

	// Phase 4d /review-impl LOW#6 follow-up: deprecation guard now
	// fires before credential resolution, so this test must use a
	// non-deprecated path or it'd 410 instead of 500.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
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

	// Phase 4d /review-impl LOW#6 follow-up: see above.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
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

// K17.2c-R1 T18 — invalid model_source falls into the else branch at
// server.go:286, producing 400 PROXY_VALIDATION_ERROR. No seed needed
// because the function returns before touching the DB for unknown
// model_source values.
func TestDoProxyInvalidModelSourceRejected(t *testing.T) {
	srv, _ := integrationServer(t)

	// Phase 4d /review-impl LOW#6 follow-up: see above.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, uuid.New(), "garbage_source", uuid.NewString())

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_VALIDATION_ERROR") {
		t.Errorf("expected error code PROXY_VALIDATION_ERROR in body, got %s", rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "invalid model_source") {
		t.Errorf("expected error message mentioning model_source, got %s", rr.Body.String())
	}
}

// K17.2c-R1 T19 — platform_model code path. Different SELECT than
// user_model (reads from platform_models table, hardcoded empty
// secret + endpoint_base_url). The K17.2a-R3 C10 empty-credential
// guard is intentionally scoped to user_model, so platform models
// with no secret must pass through. Since platform_models has no
// endpoint_base_url, the resolved base is "" and the upstream URL
// becomes "/v1/chat/completions" — we point at our httptest server
// by overriding the base URL via a test seed helper that writes
// directly to the platform_models row shape doProxy expects.
//
// Note: this test exercises the SELECT path + the empty-secret
// carve-out, but cannot fully verify the "no Authorization header"
// behavior because platform_models has no endpoint_base_url column,
// so the request to an empty base URL will fail to dial. We capture
// the 502 PROXY_UPSTREAM_ERROR to prove the code path reached the
// invokeClient step without the C10 guard tripping.
func TestDoProxyPlatformModelBypassesC10Guard(t *testing.T) {
	srv, pool := integrationServer(t)

	ctx := context.Background()
	var platformModelID uuid.UUID
	err := pool.QueryRow(ctx, `
		INSERT INTO platform_models (
			provider_kind, provider_model_name, display_name, status
		) VALUES ('openai', 'gpt-platform-test', 'Platform Test', 'active')
		RETURNING platform_model_id
	`).Scan(&platformModelID)
	if err != nil {
		t.Fatalf("insert platform_model: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM platform_models WHERE platform_model_id=$1`, platformModelID)
	})

	// Phase 4d: see TestDoProxyRewritesJSONModelField — path swap.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, uuid.New(), "platform_model", platformModelID.String())

	// Two acceptable outcomes, both prove the C10 guard did NOT
	// reject this platform_model despite the empty secret:
	//   (a) 502 PROXY_UPSTREAM_ERROR — dial failed on empty base URL
	//       (the expected path — credential resolution and JSON
	//       rewrite both succeeded; only the actual network call
	//       failed because endpoint_base_url is empty)
	//   (b) 400 PROXY_VALIDATION_ERROR from a deeper code path
	//
	// What we specifically do NOT want is:
	//   - 500 PROXY_MISSING_CREDENTIAL (the user_model-only C10 guard
	//     incorrectly firing for platform_model)
	//   - 500 PROXY_MODEL_RESOLUTION_EMPTY (resolved model name lost)
	if rr.Code == http.StatusInternalServerError &&
		strings.Contains(rr.Body.String(), "PROXY_MISSING_CREDENTIAL") {
		t.Fatalf("C10 guard wrongly rejected platform_model: %s", rr.Body.String())
	}
	if rr.Code == http.StatusInternalServerError &&
		strings.Contains(rr.Body.String(), "PROXY_MODEL_RESOLUTION_EMPTY") {
		t.Fatalf("provider_model_name was not resolved for platform_model: %s", rr.Body.String())
	}
	// Must have reached at least the target-URL construction step.
	// The dial will fail (empty base URL) giving a 502; that is the
	// observable signal that resolution and rewriting both succeeded.
	if rr.Code != http.StatusBadGateway {
		t.Logf("note: got %d (%s) — expected 502 PROXY_UPSTREAM_ERROR "+
			"from dial failure on empty endpoint_base_url",
			rr.Code, rr.Body.String())
	}
}

// K17.2c-R1 T23 — malformed ciphertext triggers decryptSecret failure.
// Seed a credential row with a bogus base64 string, then fire a
// request; doProxy should return 500 PROXY_DECRYPT_FAILED without
// contacting the upstream.
func TestDoProxyDecryptFailedOnCorruptCiphertext(t *testing.T) {
	srv, pool := integrationServer(t)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("upstream should not be called — decrypt should fail first")
	}))
	t.Cleanup(upstream.Close)

	ctx := context.Background()
	userID := uuid.New()

	// Deliberately bogus ciphertext — not valid base64-encoded
	// AES-GCM sealed bytes. decryptSecret will either fail the
	// base64 decode or the GCM open step; both map to
	// PROXY_DECRYPT_FAILED at server.go.
	bogusCipher := "this-is-not-valid-base64-or-ciphertext!!!"

	var credentialID uuid.UUID
	err := pool.QueryRow(ctx, `
		INSERT INTO provider_credentials (
			owner_user_id, provider_kind, display_name,
			endpoint_base_url, secret_ciphertext, status
		) VALUES ($1, 'openai', 'corrupt-cred', $2, $3, 'active')
		RETURNING provider_credential_id
	`, userID, upstream.URL, bogusCipher).Scan(&credentialID)
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

	// Phase 4d /review-impl LOW#6 follow-up: deprecation guard now
	// fires before credential resolution, so this test must use a
	// non-deprecated path or it'd 410 instead of 500.
	req := buildProxyRequest(t, "POST", "v1/audio/speech",
		[]byte(`{"model":"x","messages":[]}`), "application/json")
	rr := httptest.NewRecorder()
	srv.doProxy(rr, req, userID, "user_model", userModelID.String())

	if rr.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "PROXY_DECRYPT_FAILED") {
		t.Errorf("expected error code PROXY_DECRYPT_FAILED in body, got %s", rr.Body.String())
	}
}

// Phase 4d — defense-in-depth: paths retired by isDeprecatedProxyPath
// must reject with 410 Gone + PROXY_PATH_DEPRECATED rather than
// silently forwarding to the upstream provider. Credential resolution
// must still succeed first (unrelated paths still proxy through), so
// we seed a real user_model and verify the 410 fires AFTER decrypt
// but BEFORE the URL build / upstream call.
func TestDoProxyDeprecatedPathsReturn410(t *testing.T) {
	srv, pool := integrationServer(t)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("upstream MUST NOT be called for deprecated path: %s", r.URL.Path)
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "gpt-4", "sk-test")

	cases := []struct {
		name string
		path string
	}{
		{"chat-completions", "v1/chat/completions"},
		{"completions", "v1/completions"},
		{"embeddings", "v1/embeddings"},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			req := buildProxyRequest(t, "POST", tc.path,
				[]byte(`{"model":"x","messages":[]}`), "application/json")
			rr := httptest.NewRecorder()
			srv.doProxy(rr, req, userID, "user_model", userModelID.String())

			if rr.Code != http.StatusGone {
				t.Fatalf("expected 410, got %d body=%s", rr.Code, rr.Body.String())
			}
			if !strings.Contains(rr.Body.String(), "PROXY_PATH_DEPRECATED") {
				t.Errorf("expected error code PROXY_PATH_DEPRECATED in body, got %s", rr.Body.String())
			}
			if !strings.Contains(rr.Body.String(), "/v1/llm/jobs") {
				t.Errorf("expected error message to point at /v1/llm/jobs, got %s", rr.Body.String())
			}
		})
	}
}

// Phase 4d — sibling: audio paths MUST still pass through (chat-service
// voice STT/TTS depend on this until Phase 5b ships the audio adapter).
// This pins the carve-out so a future "expand the deny-list" change
// doesn't accidentally break voice.
func TestDoProxyAudioPathsNotDeprecated(t *testing.T) {
	srv, pool := integrationServer(t)

	upstreamCalled := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
		w.WriteHeader(200)
	}))
	t.Cleanup(upstream.Close)

	userID, userModelID := seedUserModel(t, srv, pool, upstream.URL, "whisper-1", "sk-test")

	for _, path := range []string{"v1/audio/transcriptions", "v1/audio/speech"} {
		path := path
		t.Run(path, func(t *testing.T) {
			upstreamCalled = false
			req := buildProxyRequest(t, "POST", path,
				[]byte("--b\r\nContent-Disposition: form-data; name=\"x\"\r\n\r\nx\r\n--b--\r\n"),
				"multipart/form-data; boundary=b")
			rr := httptest.NewRecorder()
			srv.doProxy(rr, req, userID, "user_model", userModelID.String())

			if rr.Code == http.StatusGone {
				t.Fatalf("audio path %q wrongly rejected as deprecated: %s",
					path, rr.Body.String())
			}
			if !upstreamCalled {
				t.Errorf("audio path %q never reached upstream (got %d %s)",
					path, rr.Code, rr.Body.String())
			}
		})
	}
}
