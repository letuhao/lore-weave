package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/book-service/internal/config"
)

func TestParseLimitOffset(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodGet, "/v1/books?limit=33&offset=7", nil)
	limit, offset := parseLimitOffset(req)
	if limit != 33 || offset != 7 {
		t.Fatalf("unexpected limit/offset: got %d/%d", limit, offset)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/v1/books?limit=-1&offset=-9", nil)
	limit2, offset2 := parseLimitOffset(req2)
	if limit2 != 20 || offset2 != 0 {
		t.Fatalf("expected defaults for invalid query, got %d/%d", limit2, offset2)
	}
}

func TestHelpers(t *testing.T) {
	t.Parallel()

	if nullableString("") != nil {
		t.Fatal("nullableString empty should return nil")
	}
	if nullableString("vi") != "vi" {
		t.Fatal("nullableString non-empty should return string")
	}
	if nullIfEmpty("  ") != nil {
		t.Fatal("nullIfEmpty blank should return nil")
	}
	if nullIfEmpty("abc") != "abc" {
		t.Fatal("nullIfEmpty non-empty should keep value")
	}

	s := "ok"
	if got := stringFromAny(s); got == nil || *got != "ok" {
		t.Fatal("stringFromAny string failed")
	}
	if got := stringFromAny(123); got != nil {
		t.Fatal("stringFromAny non-string should be nil")
	}

	if got := intFromAny(float64(9)); got.(int) != 9 {
		t.Fatal("intFromAny float64 failed")
	}
	if got := intFromAny("x"); got != nil {
		t.Fatal("intFromAny invalid should be nil")
	}

	if excerpt("abcdef", 3) != "abc" {
		t.Fatal("excerpt truncate failed")
	}
	if excerpt("abc", 10) != "abc" {
		t.Fatal("excerpt short string failed")
	}
}

func TestRequireUserID(t *testing.T) {
	t.Parallel()

	uid := uuid.New()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   uid.String(),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
		},
	})
	secret := "12345678901234567890123456789012"
	signed, err := token.SignedString([]byte(secret))
	if err != nil {
		t.Fatalf("sign token: %v", err)
	}

	srv := &Server{secret: []byte(secret)}
	req := httptest.NewRequest(http.MethodGet, "/v1/books", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	got, ok := srv.requireUserID(req)
	if !ok || got != uid {
		t.Fatalf("expected valid user id, got=%v ok=%v", got, ok)
	}

	req2 := httptest.NewRequest(http.MethodGet, "/v1/books", nil)
	req2.Header.Set("Authorization", "Bearer invalid")
	if _, ok := srv.requireUserID(req2); ok {
		t.Fatal("invalid token should fail")
	}
}

func TestParseUUIDParam(t *testing.T) {
	t.Parallel()

	id := uuid.New()
	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+id.String(), nil)
	rr := httptest.NewRecorder()

	routeCtx := chi.NewRouteContext()
	routeCtx.URLParams.Add("book_id", id.String())
	req = req.WithContext(contextWithChi(req, routeCtx))

	got, ok := parseUUIDParam(rr, req, "book_id")
	if !ok || got != id {
		t.Fatalf("expected parsed UUID, got=%v ok=%v", got, ok)
	}

	reqBad := httptest.NewRequest(http.MethodGet, "/v1/books/bad", nil)
	rrBad := httptest.NewRecorder()
	routeCtxBad := chi.NewRouteContext()
	routeCtxBad.URLParams.Add("book_id", "bad")
	reqBad = reqBad.WithContext(contextWithChi(reqBad, routeCtxBad))

	if _, ok := parseUUIDParam(rrBad, reqBad, "book_id"); ok {
		t.Fatal("expected parse failure")
	}
	if rrBad.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rrBad.Code)
	}
}

func contextWithChi(req *http.Request, rctx *chi.Context) context.Context {
	return context.WithValue(req.Context(), chi.RouteCtxKey, rctx)
}

func TestFetchSharingVisibility(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/sharing/books/"+bookID.String()+"/visibility" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":    bookID,
			"visibility": "public",
		})
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{SharingInternalURL: upstream.URL}}
	got := srv.fetchSharingVisibility(context.Background(), bookID)
	if got != "public" {
		t.Fatalf("expected public visibility, got %q", got)
	}
}

func TestFetchSharingVisibilityFallsBackToPrivate(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{SharingInternalURL: upstream.URL}}
	got := srv.fetchSharingVisibility(context.Background(), bookID)
	if got != "private" {
		t.Fatalf("expected private fallback on upstream error, got %q", got)
	}
}

func TestPlainTextToTiptapJSON(t *testing.T) {
	t.Parallel()

	t.Run("single paragraph", func(t *testing.T) {
		result := plainTextToTiptapJSON("Hello world")
		var doc map[string]any
		if err := json.Unmarshal(result, &doc); err != nil {
			t.Fatal(err)
		}
		if doc["type"] != "doc" {
			t.Fatalf("expected doc type, got %v", doc["type"])
		}
		content := doc["content"].([]any)
		if len(content) != 1 {
			t.Fatalf("expected 1 paragraph, got %d", len(content))
		}
		p := content[0].(map[string]any)
		if p["_text"] != "Hello world" {
			t.Fatalf("expected _text 'Hello world', got %v", p["_text"])
		}
	})

	t.Run("multiple paragraphs", func(t *testing.T) {
		result := plainTextToTiptapJSON("First paragraph\n\nSecond paragraph\n\nThird")
		var doc map[string]any
		_ = json.Unmarshal(result, &doc)
		content := doc["content"].([]any)
		if len(content) != 3 {
			t.Fatalf("expected 3 paragraphs, got %d", len(content))
		}
		texts := []string{"First paragraph", "Second paragraph", "Third"}
		for i, c := range content {
			p := c.(map[string]any)
			if p["_text"] != texts[i] {
				t.Fatalf("paragraph %d: expected %q, got %v", i, texts[i], p["_text"])
			}
		}
	})

	t.Run("empty text", func(t *testing.T) {
		result := plainTextToTiptapJSON("")
		var doc map[string]any
		_ = json.Unmarshal(result, &doc)
		content := doc["content"].([]any)
		if len(content) != 1 {
			t.Fatalf("expected 1 empty paragraph, got %d", len(content))
		}
		p := content[0].(map[string]any)
		if p["_text"] != "" {
			t.Fatalf("expected empty _text, got %v", p["_text"])
		}
		if _, hasContent := p["content"]; hasContent {
			t.Fatal("empty paragraph should not have content array")
		}
	})

	t.Run("windows line endings", func(t *testing.T) {
		result := plainTextToTiptapJSON("Line one\r\n\r\nLine two")
		var doc map[string]any
		_ = json.Unmarshal(result, &doc)
		content := doc["content"].([]any)
		if len(content) != 2 {
			t.Fatalf("expected 2 paragraphs, got %d", len(content))
		}
	})

	t.Run("valid JSON output", func(t *testing.T) {
		result := plainTextToTiptapJSON("Test with \"quotes\" and <html>")
		if !json.Valid(result) {
			t.Fatal("output is not valid JSON")
		}
	})
}
