package api

// Guards the E0-1 grant need-mapping at the ROUTER level. The DB-gated handler
// tests all run as the book OWNER, who satisfies every tier — so a destructive
// op mis-mapped to a lower grant would pass every one of them. These tests run a
// view-only / non-grantee through each mutating route and assert 403. Because
// requireGrant fires BEFORE any DB access, the nil pool is never reached.

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/config"
)

const grantMapSecret = "grant_map_test_secret_at_least_32_chars_long!!"

// denyServer builds a Server (nil pool) whose grant authority always reports the
// given level on an active book.
func denyServer(t *testing.T, level string) *Server {
	t.Helper()
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"grant_level":"` + level + `","lifecycle_state":"active"}`))
	}))
	t.Cleanup(ts.Close)
	return &Server{
		cfg:         &config.Config{JWTSecret: grantMapSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok"},
		secret:      []byte(grantMapSecret),
		grantClient: buildGrantClient(ts.URL, "tok"),
	}
}

func grantMapJWT(t *testing.T, userID uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   userID.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(grantMapSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signed
}

func TestGrantMapping_MutatingRoutesRejectViewGrantee(t *testing.T) {
	s := denyServer(t, "view")
	jwtStr := grantMapJWT(t, uuid.New())
	b, e, a, rev := uuid.New(), uuid.New(), uuid.New(), uuid.New()
	pre := "/v1/glossary/books/" + b.String()

	cases := []struct{ name, method, path string }{
		{"createEntity", http.MethodPost, pre + "/entities"},
		{"patchEntity", http.MethodPatch, pre + "/entities/" + e.String()},
		{"deleteEntity", http.MethodDelete, pre + "/entities/" + e.String()},
		{"applyEntityEdit", http.MethodPost, pre + "/entities/" + e.String() + "/apply-edit"},
		{"pinEntity", http.MethodPost, pre + "/entities/" + e.String() + "/pin"},
		{"mergeEntities", http.MethodPost, pre + "/entities/" + e.String() + "/merge"},
		{"reassignEntityKind", http.MethodPost, pre + "/entities/" + e.String() + "/reassign-kind"},
		{"restoreEntityRevision", http.MethodPost, pre + "/entities/" + e.String() + "/revisions/" + rev.String() + "/restore"},
		{"createChapterLink", http.MethodPost, pre + "/entities/" + e.String() + "/chapter-links"},
		{"restoreEntity", http.MethodPost, pre + "/recycle-bin/" + e.String() + "/restore"},
		{"purgeEntity", http.MethodDelete, pre + "/recycle-bin/" + e.String()},
		{"createWikiArticle", http.MethodPost, pre + "/wiki"},
		{"deleteWikiArticle", http.MethodDelete, pre + "/wiki/" + a.String()},
	}
	for _, c := range cases {
		req := httptest.NewRequest(c.method, c.path, bytes.NewReader([]byte(`{}`)))
		req.Header.Set("Authorization", "Bearer "+jwtStr)
		req.Header.Set("Content-Type", "application/json")
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusForbidden {
			t.Errorf("%s (%s %s): view-grantee want 403, got %d (%s)",
				c.name, c.method, c.path, rr.Code, rr.Body.String())
		}
	}
}

func TestGrantMapping_ReadRoutesRejectNonGrantee(t *testing.T) {
	s := denyServer(t, "none")
	jwtStr := grantMapJWT(t, uuid.New())
	pre := "/v1/glossary/books/" + uuid.New().String()
	// view routes — a non-grantee must 403 before any DB access.
	for _, path := range []string{pre + "/entities", pre + "/extraction-profile", pre + "/unknown-entities"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("Authorization", "Bearer "+jwtStr)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusForbidden {
			t.Errorf("non-grantee on %s want 403, got %d (%s)", path, rr.Code, rr.Body.String())
		}
	}
}
