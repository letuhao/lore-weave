package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

const compareSecret = "12345678901234567890123456789012"

// addChi injects a chi route context so a directly-invoked handler can read
// URLParams (book_id / chapter_id) without going through the full mux.
func addChi(req *http.Request, rctx *chi.Context) context.Context {
	return context.WithValue(req.Context(), chi.RouteCtxKey, rctx)
}

func mintToken(t *testing.T, uid uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   uid.String(),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
		},
	})
	signed, err := tok.SignedString([]byte(compareSecret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}
	return signed
}

// compareURL builds the compare path with optional left/right query.
func compareURL(book, chapter, left, right string) string {
	u := "/v1/books/" + book + "/chapters/" + chapter + "/revisions/compare"
	q := ""
	if left != "" {
		q = "left=" + left
	}
	if right != "" {
		if q != "" {
			q += "&"
		}
		q += "right=" + right
	}
	if q != "" {
		u += "?" + q
	}
	return u
}

func TestCompareRevisions_Unauthorized(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(compareSecret)}
	req := httptest.NewRequest(http.MethodGet, compareURL("b", "c", "x", "y"), nil)
	// chi params so parseUUIDParam doesn't matter — auth fails first.
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", uuid.New().String())
	rctx.URLParams.Add("chapter_id", uuid.New().String())
	req = req.WithContext(addChi(req, rctx))
	w := httptest.NewRecorder()
	s.compareRevisions(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("no token → want 401, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestCompareRevisions_MissingOrBadParams_400(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(compareSecret)}
	uid := uuid.New()
	book, chapter := uuid.New().String(), uuid.New().String()

	cases := []struct{ name, left, right string }{
		{"missing both", "", ""},
		{"missing right", uuid.New().String(), ""},
		{"invalid left", "not-a-uuid", uuid.New().String()},
		{"invalid right", uuid.New().String(), "nope"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, compareURL(book, chapter, tc.left, tc.right), nil)
			req.Header.Set("Authorization", "Bearer "+mintToken(t, uid))
			rctx := chi.NewRouteContext()
			rctx.URLParams.Add("book_id", book)
			rctx.URLParams.Add("chapter_id", chapter)
			req = req.WithContext(addChi(req, rctx))
			w := httptest.NewRecorder()
			// nil pool: the handler must 400 on params BEFORE any DB use.
			s.compareRevisions(w, req)
			if w.Code != http.StatusBadRequest {
				t.Fatalf("%s → want 400, got %d body=%s", tc.name, w.Code, w.Body.String())
			}
			if !strings.Contains(w.Body.String(), "COMPARE_BAD_PARAM") {
				t.Fatalf("%s → want COMPARE_BAD_PARAM, got %s", tc.name, w.Body.String())
			}
		})
	}
}

// TestCompareRevisions_RoutedNotGetRevision proves chi sends /revisions/compare
// to compareRevisions (static), NOT getRevision with revision_id="compare". A
// valid token + no left/right returns COMPARE_BAD_PARAM (before any DB), which
// getRevision would never emit.
func TestCompareRevisions_RoutedNotGetRevision(t *testing.T) {
	t.Parallel()
	s := NewServer(nil, &config.Config{JWTSecret: compareSecret})
	book, chapter := uuid.New().String(), uuid.New().String()
	req := httptest.NewRequest(http.MethodGet, compareURL(book, chapter, "", ""), nil)
	req.Header.Set("Authorization", "Bearer "+mintToken(t, uuid.New()))
	w := httptest.NewRecorder()
	s.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest || !strings.Contains(w.Body.String(), "COMPARE_BAD_PARAM") {
		t.Fatalf("compare must own /revisions/compare; got %d body=%s", w.Code, w.Body.String())
	}
}
