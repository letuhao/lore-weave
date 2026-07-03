package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

// mintJWT builds an HS256 user token signed with the test config secret.
func mintJWT(t *testing.T, sub, role string) string {
	t.Helper()
	claims := accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   sub,
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		Role: role,
	}
	tok, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(testCfg().JWTSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return tok
}

func newMockServer(t *testing.T) (*Server, pgxmock.PgxPoolIface) {
	t.Helper()
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	return NewServer(mock, testCfg()), mock
}

func doJSON(s *Server, method, path, token, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	s.Router().ServeHTTP(rec, req)
	return rec
}

func TestCreatePlugin_Unauthenticated(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", "", `{"name":"io.x/y"}`)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestCreatePlugin_InvalidName(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "")
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"NOT VALID"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d (%s)", rec.Code, rec.Body.String())
	}
	var e errorBody
	_ = json.Unmarshal(rec.Body.Bytes(), &e)
	if e.Code != "VALIDATION_ERROR" {
		t.Fatalf("want VALIDATION_ERROR, got %q", e.Code)
	}
}

func TestCreatePlugin_SystemTierRequiresAdmin(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "") // regular user
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"io.x/y","tier":"system"}`)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("want 403, got %d (%s)", rec.Code, rec.Body.String())
	}
	// no DB expectations were set — the handler must reject before querying.
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unexpected DB calls: %v", err)
	}
}

// With no BOOK_SERVICE_INTERNAL_URL (grants==nil), a book-tier write is refused
// 501 — book-tier requires the grant client (D-REG-BOOK-GRANT, fail-closed). The
// grant-wired path (404/503) is covered by the live governance smoke.
func TestCreatePlugin_BookTierRequiresGrantClient(t *testing.T) {
	s, mock := newMockServer(t) // testCfg has no BookServiceInternalURL → grants nil
	defer mock.Close()
	tok := mintJWT(t, uuid.NewString(), "")
	rec := doJSON(s, http.MethodPost, "/v1/agent-registry/plugins", tok, `{"name":"io.x/y","tier":"book","book_id":"`+uuid.NewString()+`"}`)
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("want 501 (no grant client), got %d", rec.Code)
	}
}

func TestEffectiveCatalog_RequiresInternalToken(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	req := httptest.NewRequest(http.MethodGet, "/internal/effective-catalog?user_id="+uuid.NewString(), nil)
	rec := httptest.NewRecorder()
	s.Router().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401 without internal token, got %d", rec.Code)
	}
}
