package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/config"
)

// testSecret is the shared JWT secret used across all change-password tests.
const testSecret = "01234567890123456789012345678901"

// newTestServer returns a Server with no DB pool (nil). Tests that exercise
// validation paths that never reach the DB are safe to use it directly.
func newTestServer() *Server {
	return &Server{
		cfg:    &config.Config{PasswordMinLength: 8},
		secret: []byte(testSecret),
	}
}

// validToken mints a real JWT for the given user+session pair.
func validToken(t *testing.T, userID, sessionID uuid.UUID) string {
	t.Helper()
	tok, err := authjwt.SignAccess([]byte(testSecret), userID, sessionID, time.Hour)
	if err != nil {
		t.Fatalf("mint token: %v", err)
	}
	return tok
}

func doChangePassword(t *testing.T, s *Server, token string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if err := json.NewEncoder(&buf).Encode(body); err != nil {
		t.Fatalf("encode body: %v", err)
	}
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/change-password", &buf)
	r.Header.Set("Content-Type", "application/json")
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	s.changePassword(w, r)
	return w
}

// ── Auth / pre-validation tests (no DB required) ──────────────────────────────

func TestChangePassword_MissingBearer(t *testing.T) {
	s := newTestServer()
	w := doChangePassword(t, s, "", map[string]string{
		"current_password": "OldPass1",
		"new_password":     "NewPass1",
	})
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_TOKEN_INVALID")
}

func TestChangePassword_MalformedJWT(t *testing.T) {
	s := newTestServer()
	w := doChangePassword(t, s, "not.a.token", map[string]string{
		"current_password": "OldPass1",
		"new_password":     "NewPass1",
	})
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d: %s", w.Code, w.Body.String())
	}
}

func TestChangePassword_ExpiredJWT(t *testing.T) {
	s := newTestServer()
	tok, err := authjwt.SignAccess([]byte(testSecret), uuid.New(), uuid.New(), -time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	w := doChangePassword(t, s, tok, map[string]string{
		"current_password": "OldPass1",
		"new_password":     "NewPass1",
	})
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_TOKEN_EXPIRED")
}

func TestChangePassword_InvalidJSON(t *testing.T) {
	s := newTestServer()
	tok := validToken(t, uuid.New(), uuid.New())

	r := httptest.NewRequest(http.MethodPost, "/v1/auth/change-password", bytes.NewBufferString("{bad json"))
	r.Header.Set("Authorization", "Bearer "+tok)
	w := httptest.NewRecorder()
	s.changePassword(w, r)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_VALIDATION_ERROR")
}

func TestChangePassword_EmptyCurrentPassword(t *testing.T) {
	s := newTestServer()
	tok := validToken(t, uuid.New(), uuid.New())
	w := doChangePassword(t, s, tok, map[string]string{
		"current_password": "",
		"new_password":     "NewPass1",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_VALIDATION_ERROR")
}

func TestChangePassword_NewPasswordTooShort(t *testing.T) {
	s := newTestServer()
	tok := validToken(t, uuid.New(), uuid.New())
	w := doChangePassword(t, s, tok, map[string]string{
		"current_password": "OldPass1",
		"new_password":     "sh0rt",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_VALIDATION_ERROR")
}

func TestChangePassword_NewPasswordNoDigit(t *testing.T) {
	s := newTestServer()
	tok := validToken(t, uuid.New(), uuid.New())
	w := doChangePassword(t, s, tok, map[string]string{
		"current_password": "OldPass1",
		"new_password":     "alllowercase",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_VALIDATION_ERROR")
}

func TestChangePassword_NewPasswordNoLetter(t *testing.T) {
	s := newTestServer()
	tok := validToken(t, uuid.New(), uuid.New())
	w := doChangePassword(t, s, tok, map[string]string{
		"current_password": "OldPass1",
		"new_password":     "12345678",
	})
	if w.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d: %s", w.Code, w.Body.String())
	}
	assertErrorCode(t, w, "AUTH_VALIDATION_ERROR")
}

// ── Helper ────────────────────────────────────────────────────────────────────

func assertErrorCode(t *testing.T, w *httptest.ResponseRecorder, wantCode string) {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.NewDecoder(w.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Code != wantCode {
		t.Fatalf("want error code %q, got %q", wantCode, body.Code)
	}
}
