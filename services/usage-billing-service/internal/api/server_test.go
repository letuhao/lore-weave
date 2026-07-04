package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/usage-billing-service/internal/config"
)

func testServer(secret string) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret: secret,
	})
}

// signedToken mints a platform-USER HS256 token (exp + UUID sub — the shape the
// shared platformjwt verifier requires). The `role` arg is vestigial: the user
// token carries no role (D-JWT-ROLE-GATE) — admin authority is the RS256 admin
// token's job (see newAdminTestServer). Kept in the signature so existing callers
// compile unchanged.
func signedToken(t *testing.T, secret string, userID uuid.UUID, _ string) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
	})
	signed, err := token.SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// newAdminTestServer builds a Server with RS256 admin verification enabled against
// a freshly generated key, plus a mint() that signs admin tokens with the matching
// private key (the same RS256/iss/aud/kid contract auth-service emits). Mirrors
// provider-registry / glossary's newAdminTestServer.
func newAdminTestServer(t *testing.T, secret string) (*Server, func(scopes []string) string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal pub: %v", err)
	}
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	srv := NewServer(nil, &config.Config{
		JWTSecret:            secret,
		AdminJWTPublicKeyPEM: string(pubPEM),
	})
	if srv.adminPub == nil {
		t.Fatal("admin verification not enabled on the test server")
	}
	kid, err := adminjwt.KeyFingerprint(&priv.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	mint := func(scopes []string) string {
		claims := adminjwt.AdminClaims{
			Role:   "admin",
			Scopes: scopes,
			RegisteredClaims: jwt.RegisteredClaims{
				Issuer:    adminjwt.Issuer,
				Audience:  jwt.ClaimStrings{adminjwt.Audience},
				Subject:   uuid.NewString(),
				ID:        uuid.NewString(),
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
		tok.Header["kid"] = kid
		signed, err := tok.SignedString(priv)
		if err != nil {
			t.Fatalf("sign admin token: %v", err)
		}
		return signed
	}
	return srv, mint
}

func withRouteParam(req *http.Request, key, value string) *http.Request {
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add(key, value)
	return req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
}

func TestAuthSuccessAndFailure(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	userID := uuid.New()
	srv := testServer(secret)

	okReq := httptest.NewRequest(http.MethodGet, "/", nil)
	okReq.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	gotID, ok := srv.auth(okReq)
	if !ok || gotID != userID {
		t.Fatalf("expected auth success, got id=%v ok=%v", gotID, ok)
	}

	badReq := httptest.NewRequest(http.MethodGet, "/", nil)
	badReq.Header.Set("Authorization", "Bearer invalid")
	if _, ok := srv.auth(badReq); ok {
		t.Fatal("expected auth failure")
	}
}

func TestParseIntDefault(t *testing.T) {
	t.Parallel()

	if got := parseIntDefault("", 20, 1, 100); got != 20 {
		t.Fatalf("expected default 20, got %d", got)
	}
	if got := parseIntDefault("5", 20, 1, 100); got != 5 {
		t.Fatalf("expected parsed 5, got %d", got)
	}
	if got := parseIntDefault("-1", 20, 1, 100); got != 1 {
		t.Fatalf("expected min clamp 1, got %d", got)
	}
	if got := parseIntDefault("200", 20, 1, 100); got != 100 {
		t.Fatalf("expected max clamp 100, got %d", got)
	}
}

type fakeScanner struct {
	values []any
	err    error
}

func (f fakeScanner) Scan(dest ...any) error {
	if f.err != nil {
		return f.err
	}
	for i := range dest {
		switch d := dest[i].(type) {
		case *uuid.UUID:
			*d = f.values[i].(uuid.UUID)
		case *string:
			*d = f.values[i].(string)
		case *int:
			*d = f.values[i].(int)
		case *float64:
			*d = f.values[i].(float64)
		case *time.Time:
			*d = f.values[i].(time.Time)
		default:
			return errors.New("unsupported dest type")
		}
	}
	return nil
}

func TestScanUsageLogRow(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	vals := []any{
		uuid.New(), uuid.New(), uuid.New(), "openai", "user_model", uuid.New(),
		1, 2, 3, 0.1, "quota", "success", "m03-v1", "in", "out", "kref", "AES-256-GCM", 1, "translation", now,
	}
	row, err := scanUsageLogRow(fakeScanner{values: vals})
	if err != nil {
		t.Fatalf("scanUsageLogRow failed: %v", err)
	}
	if row["billing_decision"] != "quota" {
		t.Fatalf("unexpected billing_decision: %v", row["billing_decision"])
	}
	if row["total_tokens"] != 3 {
		t.Fatalf("unexpected total_tokens: %v", row["total_tokens"])
	}
}

func TestRecordCostUSD(t *testing.T) {
	t.Parallel()
	// nil override → flat per-token fallback (legacy / unpriced).
	if got, want := recordCostUSD(1000, nil), float64(1000)*flatCostPerToken; got != want {
		t.Fatalf("nil override: got %v want %v", got, want)
	}
	// authoritative per-model cost (e.g. gpt-4o 2.5/10 on 58777 in + 20457 out)
	// is used verbatim, NOT the flat rate (which would under-bill ~55%).
	cost := 0.3515
	if got := recordCostUSD(79234, &cost); got != 0.3515 {
		t.Fatalf("override: got %v want 0.3515", got)
	}
	// a local/free model sends 0 — honored verbatim, NOT replaced by the flat rate.
	zero := 0.0
	if got := recordCostUSD(5000, &zero); got != 0 {
		t.Fatalf("free model must bill 0, got %v", got)
	}
	// a stray negative override is rejected → flat fallback (defensive).
	neg := -1.0
	if got, want := recordCostUSD(100, &neg), float64(100)*flatCostPerToken; got != want {
		t.Fatalf("negative override must fall back to flat, got %v want %v", got, want)
	}
}

func TestRecordInvocationValidation(t *testing.T) {
	t.Parallel()

	srv := testServer("12345678901234567890123456789012")
	req := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewBufferString(`{"request_id":"bad"}`))
	rr := httptest.NewRecorder()
	srv.recordInvocation(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}

	req2 := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewBufferString(`{"request_id":"`+uuid.NewString()+`","owner_user_id":"`+uuid.NewString()+`","model_ref":"00000000-0000-0000-0000-000000000000"}`))
	rr2 := httptest.NewRecorder()
	srv.recordInvocation(rr2, req2)
	if rr2.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for nil model_ref, got %d", rr2.Code)
	}
}

func TestUsageHandlersUnauthorized(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)

	listReq := httptest.NewRequest(http.MethodGet, "/v1/model-billing/usage-logs", nil)
	listRR := httptest.NewRecorder()
	srv.listUsageLogs(listRR, listReq)
	if listRR.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", listRR.Code)
	}
}

// TestAdminEndpointsGuard proves the D-JWT-ROLE-GATE fix: the admin usage +
// reconciliation endpoints are gated by the RS256 admin token (contracts/adminjwt),
// not the dead HS256 `role` claim. Both endpoints share requireAdminScope, so the
// pre-gate states (503/401/403) are asserted on both; the gate-PASS is proven on
// createReconciliation (its bad-body path returns 400 AFTER the gate — a nil-pool
// test server would panic on adminListUsage's INSERT-less pool.Query, so the
// gate-pass is not asserted there).
func TestAdminEndpointsGuard(t *testing.T) {
	t.Parallel()
	secret := "12345678901234567890123456789012"
	userID := uuid.New()

	callAdminUsage := func(srv *Server, authz string) int {
		req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/admin/usage", nil)
		if authz != "" {
			req.Header.Set("Authorization", authz)
		}
		rr := httptest.NewRecorder()
		srv.adminListUsage(rr, req)
		return rr.Code
	}
	callRecon := func(srv *Server, authz, body string) int {
		req := httptest.NewRequest(http.MethodPost, "/v1/model-billing/admin/reconciliation", bytes.NewBufferString(body))
		if authz != "" {
			req.Header.Set("Authorization", authz)
		}
		rr := httptest.NewRecorder()
		srv.createReconciliation(rr, req)
		return rr.Code
	}

	// Admin NOT configured → fail closed (503) on BOTH endpoints, unreachable by any token.
	unconfigured := testServer(secret)
	if code := callAdminUsage(unconfigured, "Bearer "+signedToken(t, secret, userID, "")); code != http.StatusServiceUnavailable {
		t.Fatalf("admin/usage unconfigured: expected 503, got %d", code)
	}
	if code := callRecon(unconfigured, "Bearer "+signedToken(t, secret, userID, ""), `{}`); code != http.StatusServiceUnavailable {
		t.Fatalf("admin/reconciliation unconfigured: expected 503, got %d", code)
	}

	// Admin configured:
	srv, mintAdmin := newAdminTestServer(t, secret)

	// A regular HS256 user token is rejected by the RS256 admin gate → 401.
	if code := callAdminUsage(srv, "Bearer "+signedToken(t, secret, userID, "")); code != http.StatusUnauthorized {
		t.Fatalf("admin/usage user token: expected 401, got %d", code)
	}
	if code := callRecon(srv, "Bearer "+signedToken(t, secret, userID, ""), `{}`); code != http.StatusUnauthorized {
		t.Fatalf("admin/reconciliation user token: expected 401, got %d", code)
	}

	// No token → 401.
	if code := callAdminUsage(srv, ""); code != http.StatusUnauthorized {
		t.Fatalf("admin/usage no token: expected 401, got %d", code)
	}

	// A valid admin token WITHOUT the required scope → 403.
	if code := callAdminUsage(srv, "Bearer "+mintAdmin([]string{"admin:read"})); code != http.StatusForbidden {
		t.Fatalf("admin/usage wrong-scope: expected 403, got %d", code)
	}
	if code := callRecon(srv, "Bearer "+mintAdmin([]string{"admin:read"}), `{}`); code != http.StatusForbidden {
		t.Fatalf("admin/reconciliation wrong-scope: expected 403, got %d", code)
	}

	// A valid admin token WITH admin:write PASSES the gate: send an INVALID body so
	// createReconciliation stops at the 400 body-decode AFTER the gate (a nil-pool
	// test server would panic on the INSERT). A 400 proves the gate was passed.
	if code := callRecon(srv, "Bearer "+mintAdmin([]string{scopeAdminWrite}), `not-json`); code != http.StatusBadRequest {
		t.Fatalf("valid admin:write must pass the gate → 400 on bad body, got %d", code)
	}
}

func TestGetUsageLogDetailValidation(t *testing.T) {
	t.Parallel()

	secret := "12345678901234567890123456789012"
	srv := testServer(secret)
	userID := uuid.New()

	req := httptest.NewRequest(http.MethodGet, "/v1/model-billing/usage-logs/bad", nil)
	req = withRouteParam(req, "usage_log_id", "bad")
	req.Header.Set("Authorization", "Bearer "+signedToken(t, secret, userID, ""))
	rr := httptest.NewRecorder()
	srv.getUsageLogDetail(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}

// payloadServer builds a Server wired with a dedicated payload KEK (distinct
// from the JWT secret) so the round-trip envelope exercises the real key paths.
func payloadServer() *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:               "12345678901234567890123456789012",
		LLMPayloadEncryptionKey: "PAYLOAD-KEK-distinct-from-jwt-3232",
	})
}

// envelope mirrors writeUsageLog's encrypt side using the given master key:
// random session key → encrypt payload with it → wrap the session key.
func envelope(t *testing.T, masterKey, plain []byte) (payloadCipher, keyCipher string) {
	t.Helper()
	sessionKey := make([]byte, 32)
	for i := range sessionKey {
		sessionKey[i] = byte(i + 1)
	}
	pc, err := encryptWithKey(sessionKey, plain)
	if err != nil {
		t.Fatalf("encrypt payload: %v", err)
	}
	kc, err := encryptWithKey(masterKey, sessionKey)
	if err != nil {
		t.Fatalf("wrap session key: %v", err)
	}
	return pc, kc
}

// readBack mirrors getUsageLogDetail's decrypt side: unwrap (dedicated→legacy),
// decrypt, and decode into the stored shape.
func readBack(t *testing.T, s *Server, payloadCipher, keyCipher string) any {
	t.Helper()
	sessionKey, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, s.retiredKeys, keyCipher)
	if err != nil {
		t.Fatalf("unwrap session key: %v", err)
	}
	plain, err := decryptWithKey(sessionKey, payloadCipher)
	if err != nil {
		t.Fatalf("decrypt payload: %v", err)
	}
	return decodePayloadBytes(plain)
}

// TestPayloadRoundTrip_Object is the P0-1 guard (LOG-4): an object payload
// written through the marshal side reads back as the SAME object, not empty {}.
func TestPayloadRoundTrip_Object(t *testing.T) {
	t.Parallel()
	s := payloadServer()
	obj := map[string]any{
		"model":    "gpt-4o",
		"messages": []any{map[string]any{"role": "user", "content": "hello"}},
	}
	pc, kc := envelope(t, s.secretKey, marshalPayload(obj))
	got := readBack(t, s, pc, kc)

	gotJSON, _ := json.Marshal(got)
	wantJSON, _ := json.Marshal(obj)
	if string(gotJSON) != string(wantJSON) {
		t.Fatalf("object round-trip mismatch:\n got=%s\nwant=%s", gotJSON, wantJSON)
	}
	if m, ok := got.(map[string]any); !ok || len(m) == 0 {
		t.Fatalf("expected non-empty object, got %#v", got)
	}
}

// TestPayloadRoundTrip_String is the exact P0-1 defect shape: the jobs path
// stores the truncated payload as a JSON *string*. The old read unmarshalled
// into map[string]any → failed → empty {}. It must now read back as its content.
func TestPayloadRoundTrip_String(t *testing.T) {
	t.Parallel()
	s := payloadServer()
	str := `{"truncated":"request json as a string"}`
	pc, kc := envelope(t, s.secretKey, marshalPayload(str))
	got := readBack(t, s, pc, kc)
	if got != str {
		t.Fatalf("string round-trip mismatch: got %#v want %q", got, str)
	}
}

// TestDecodePayloadBytes covers the three stored shapes symmetrically.
func TestDecodePayloadBytes(t *testing.T) {
	t.Parallel()
	// object
	if got := decodePayloadBytes([]byte(`{"a":"b"}`)); !reflect.DeepEqual(got, map[string]any{"a": "b"}) {
		t.Fatalf("object decode: got %#v", got)
	}
	// JSON string
	if got := decodePayloadBytes([]byte(`"hi"`)); got != "hi" {
		t.Fatalf("json-string decode: got %#v", got)
	}
	// legacy raw non-JSON bytes → raw string (never a decode error)
	if got := decodePayloadBytes([]byte(`not json at all`)); got != "not json at all" {
		t.Fatalf("legacy raw decode: got %#v", got)
	}
	// empty → nil
	if got := decodePayloadBytes(nil); got != nil {
		t.Fatalf("empty decode: got %#v", got)
	}
}

// TestUnwrapSessionKey_LegacyFallback proves a row wrapped with the OLD
// JWT-derived KEK is still decryptable after the dedicated-key migration
// (P0-3 back-compat), while a fresh row uses the dedicated key.
func TestUnwrapSessionKey_LegacyFallback(t *testing.T) {
	t.Parallel()
	s := payloadServer()
	sessionKey := []byte("session-key-32-bytes-xxxxxxxxxxxx")

	// Row wrapped with the LEGACY (JWT-derived) key.
	legacyWrap, err := encryptWithKey(s.legacySecretKey, sessionKey)
	if err != nil {
		t.Fatalf("legacy wrap: %v", err)
	}
	got, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, nil, legacyWrap)
	if err != nil {
		t.Fatalf("legacy unwrap failed: %v", err)
	}
	if string(got) != string(sessionKey) {
		t.Fatalf("legacy unwrap mismatch")
	}

	// Row wrapped with the DEDICATED key still works.
	freshWrap, _ := encryptWithKey(s.secretKey, sessionKey)
	if got, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, nil, freshWrap); err != nil || string(got) != string(sessionKey) {
		t.Fatalf("dedicated unwrap failed: err=%v", err)
	}
}

// TestUnwrapSessionKey_RetiredKeyRotation proves B-MED-1: after rotating the
// dedicated KEK (old value moved into LLM_PAYLOAD_ENCRYPTION_KEYS_RETIRED), a row
// wrapped under the OLD key still decrypts, while new rows use the new key — so a
// rotation no longer orphans prior payloads.
func TestUnwrapSessionKey_RetiredKeyRotation(t *testing.T) {
	t.Parallel()
	oldKEK := "OLD-payload-kek-32-chars-exactly!!"
	newKEK := "NEW-payload-kek-distinct-32-chars!"
	// The server AFTER rotation: new key is active, old key is retired.
	s := NewServer(nil, &config.Config{
		JWTSecret:                       "12345678901234567890123456789012",
		LLMPayloadEncryptionKey:         newKEK,
		LLMPayloadEncryptionKeysRetired: []string{oldKEK},
	})
	sessionKey := []byte("session-key-32-bytes-xxxxxxxxxxxx")

	// A row written BEFORE rotation (wrapped with the old, now-retired KEK).
	oldWrap, err := encryptWithKey(normalizeAESKey(oldKEK), sessionKey)
	if err != nil {
		t.Fatalf("old wrap: %v", err)
	}
	got, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, s.retiredKeys, oldWrap)
	if err != nil || string(got) != string(sessionKey) {
		t.Fatalf("retired-key unwrap failed (rotation orphaned the row): err=%v", err)
	}

	// A row written AFTER rotation (wrapped with the new active KEK) still works.
	newWrap, _ := encryptWithKey(s.secretKey, sessionKey)
	if got, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, s.retiredKeys, newWrap); err != nil || string(got) != string(sessionKey) {
		t.Fatalf("active-key unwrap failed: err=%v", err)
	}

	// A key that was NEVER registered (neither active nor retired) must still fail.
	strangerWrap, _ := encryptWithKey(normalizeAESKey("STRANGER-kek-never-registered-32c"), sessionKey)
	if _, err := unwrapSessionKey(s.secretKey, s.legacySecretKey, s.retiredKeys, strangerWrap); err == nil {
		t.Fatal("an unregistered key must NOT decrypt")
	}
}

// TestPayloadKeyRef_NamesRealKey: the key ref is a stable fingerprint of the
// active KEK (rotatable), NOT a random per-row UUID (the P0-3 defect).
func TestPayloadKeyRef_NamesRealKey(t *testing.T) {
	t.Parallel()
	s := payloadServer()
	ref1 := s.payloadKeyRef()
	ref2 := s.payloadKeyRef()
	if ref1 != ref2 {
		t.Fatalf("key ref must be stable across calls: %q vs %q", ref1, ref2)
	}
	if !strings.HasPrefix(ref1, "llm-payload-key-v1:") {
		t.Fatalf("key ref must name a versioned key, got %q", ref1)
	}
	// A different KEK yields a different ref (rotation is observable).
	other := NewServer(nil, &config.Config{
		JWTSecret:               "12345678901234567890123456789012",
		LLMPayloadEncryptionKey: "A-DIFFERENT-payload-kek-32-chars!!",
	})
	if other.payloadKeyRef() == ref1 {
		t.Fatalf("distinct KEKs must produce distinct refs")
	}
	// Not a UUID (the old random ref).
	if _, err := uuid.Parse(ref1); err == nil {
		t.Fatalf("key ref must not be a bare UUID, got %q", ref1)
	}
}
