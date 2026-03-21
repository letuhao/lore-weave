package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/sharing-service/internal/config"
)

func TestTokenFormat(t *testing.T) {
	t.Parallel()
	got := token()
	if len(got) != 32 {
		t.Fatalf("expected 32 char token, got %d", len(got))
	}
	if strings.Contains(got, "-") {
		t.Fatal("token must not include hyphen")
	}
}

func TestRequireUserID(t *testing.T) {
	t.Parallel()
	uid := uuid.New()
	secret := "12345678901234567890123456789012"
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   uid.String(),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
		},
	})
	signed, err := tok.SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}

	srv := &Server{secret: []byte(secret)}
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	got, ok := srv.requireUserID(req)
	if !ok || got != uid {
		t.Fatalf("expected uid=%v, got=%v ok=%v", uid, got, ok)
	}
}

func TestParseBookID(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	req := httptest.NewRequest(http.MethodGet, "/v1/sharing/books/"+id.String(), nil)
	rr := httptest.NewRecorder()
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", id.String())
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))

	got, ok := parseBookID(rr, req)
	if !ok || got != id {
		t.Fatalf("expected parsed id, got=%v ok=%v", got, ok)
	}
}

func TestFetchBookProjection(t *testing.T) {
	t.Parallel()
	bookID := uuid.New()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/internal/books/") {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":         bookID,
			"owner_user_id":   uuid.New(),
			"title":           "Book A",
			"lifecycle_state": "active",
			"created_at":      time.Now().UTC(),
		})
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{BookServiceInternalURL: upstream.URL}}
	proj, status := srv.fetchBookProjection(bookID)
	if status != http.StatusOK || proj == nil {
		t.Fatalf("expected status 200 and projection, got status=%d", status)
	}
	if proj.BookID != bookID {
		t.Fatalf("book id mismatch: %v", proj.BookID)
	}
}

func TestFetchBookProjectionHandlesBadJSON(t *testing.T) {
	t.Parallel()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("{bad"))
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{BookServiceInternalURL: upstream.URL}}
	proj, status := srv.fetchBookProjection(uuid.New())
	if proj != nil || status != http.StatusBadGateway {
		t.Fatalf("expected 502 for bad json, got proj=%v status=%d", proj, status)
	}
}
