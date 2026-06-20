package api

// E0-5 — handler-level coverage for the email-invite resolve branches that the
// owner-only JWT-gate test can't reach. All four short-circuit BEFORE tx.Begin
// (the nil pool never panics): owner-self → 400, email-not-found → 404, auth
// error → 503, bad body → 400. The owner gate is stubbed (resolveBook → Owner)
// and auth-service is a fake httptest server, so no DB is needed. The actual
// upsert + audit is real-PG / live-smoke (D-E0-5-LIVE-SMOKE).

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

// inviteServer wires a Server whose caller is the book OWNER (resolveBook → Owner)
// and whose auth-service is `authHandler`. Returns the server + the owner's minted
// Bearer token (its subject == the owner uid the handler will compare against).
func inviteServer(t *testing.T, authHandler http.HandlerFunc) (*Server, string, uuid.UUID) {
	t.Helper()
	ts := httptest.NewServer(authHandler)
	t.Cleanup(ts.Close)
	s := NewServer(nil, &config.Config{
		JWTSecret:              grantMapSecret,
		InternalServiceToken:   "itok",
		AuthServiceInternalURL: ts.URL,
	})
	s.resolveBook = func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, userID, "active", nil // caller IS the owner
	}
	owner := uuid.New()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   owner.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(grantMapSecret))
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return s, signed, owner
}

func postInvite(t *testing.T, s *Server, token, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/books/"+uuid.NewString()+"/collaborators", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func jsonHandler(status int, body string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}
}

func TestInvite_OwnerSelf_400(t *testing.T) {
	t.Parallel()
	// auth resolves the invite email to the OWNER's own id → can't grant yourself.
	var owner uuid.UUID
	s, tok, ownerUID := inviteServer(t, func(w http.ResponseWriter, r *http.Request) {
		jsonHandler(http.StatusOK, `{"user_id":"`+owner.String()+`","email":"me@x.co","display_name":"Me"}`)(w, r)
	})
	owner = ownerUID // close over the real owner before the request fires
	rr := postInvite(t, s, tok, `{"email":"me@x.co","role":"edit"}`)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("owner-self: got %d want 400 (%s)", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "CANNOT_GRANT_OWNER") {
		t.Errorf("want CANNOT_GRANT_OWNER, got %s", rr.Body.String())
	}
}

func TestInvite_EmailNotFound_404(t *testing.T) {
	t.Parallel()
	// auth 404 → a clean "no user with that email", NOT a 500.
	s, tok, _ := inviteServer(t, jsonHandler(http.StatusNotFound, `{"error":{"code":"AUTH_USER_NOT_FOUND"}}`))
	rr := postInvite(t, s, tok, `{"email":"ghost@x.co","role":"view"}`)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("not-found: got %d want 404 (%s)", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), "USER_NOT_FOUND") {
		t.Errorf("want USER_NOT_FOUND, got %s", rr.Body.String())
	}
}

func TestInvite_AuthError_503(t *testing.T) {
	t.Parallel()
	// A 5xx from auth must NOT masquerade as "no such user" — fail the invite (503).
	s, tok, _ := inviteServer(t, jsonHandler(http.StatusInternalServerError, ``))
	rr := postInvite(t, s, tok, `{"email":"x@y.co","role":"manage"}`)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("auth-error: got %d want 503 (%s)", rr.Code, rr.Body.String())
	}
}

func TestInvite_BadBody_400(t *testing.T) {
	t.Parallel()
	// Missing email or an ungrantable role → 400 before auth is even called.
	s, tok, _ := inviteServer(t, jsonHandler(http.StatusInternalServerError, ``)) // would 503 if reached
	for _, body := range []string{`{"role":"edit"}`, `{"email":"a@b.co","role":"owner"}`, `{"email":"  ","role":"edit"}`} {
		rr := postInvite(t, s, tok, body)
		if rr.Code != http.StatusBadRequest {
			t.Errorf("bad body %q: got %d want 400", body, rr.Code)
		}
	}
}
