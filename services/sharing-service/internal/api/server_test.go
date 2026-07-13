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
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   uid.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
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

// TestDiaryVisibilityGuard — a diary can never be made non-private (P-4 / D16),
// and the guard FAILS CLOSED when book-service can't confirm the kind.
func TestDiaryVisibilityGuard(t *testing.T) {
	t.Parallel()

	projServer := func(kind string) *httptest.Server {
		return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"book_id": uuid.New(), "owner_user_id": uuid.New(),
				"kind": kind, "title": "X", "lifecycle_state": "active",
				"created_at": time.Now().UTC(),
			})
		}))
	}

	t.Run("diary cannot go public", func(t *testing.T) {
		up := projServer("diary")
		defer up.Close()
		srv := &Server{cfg: &config.Config{BookServiceInternalURL: up.URL}}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), "public"); code != http.StatusForbidden {
			t.Fatalf("diary→public: want 403, got %d", code)
		}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), "unlisted"); code != http.StatusForbidden {
			t.Fatalf("diary→unlisted: want 403, got %d", code)
		}
	})

	t.Run("diary stays private with no fetch", func(t *testing.T) {
		// A private (or empty no-op) set must be allowed WITHOUT even calling
		// book-service — proven by pointing at a dead URL and still getting allow.
		srv := &Server{cfg: &config.Config{BookServiceInternalURL: "http://127.0.0.1:0"}}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), "private"); code != 0 {
			t.Fatalf("diary→private: want allow(0), got %d", code)
		}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), ""); code != 0 {
			t.Fatalf("empty→noop: want allow(0), got %d", code)
		}
	})

	t.Run("a normal book can go public", func(t *testing.T) {
		up := projServer("novel")
		defer up.Close()
		srv := &Server{cfg: &config.Config{BookServiceInternalURL: up.URL}}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), "public"); code != 0 {
			t.Fatalf("novel→public: want allow(0), got %d", code)
		}
	})

	t.Run("fail closed when book-service is unreachable", func(t *testing.T) {
		up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusServiceUnavailable)
		}))
		defer up.Close()
		srv := &Server{cfg: &config.Config{BookServiceInternalURL: up.URL}}
		if code, _ := srv.diaryVisibilityGuard(uuid.New(), "public"); code != http.StatusBadGateway {
			t.Fatalf("unreachable→public: want 502 fail-closed, got %d", code)
		}
	})
}

func TestFetchBookChaptersInternal(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/internal/books/"+bookID.String()+"/chapters") {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{"chapter_id": uuid.New(), "sort_order": 1},
			},
			"total": 1,
		})
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{BookServiceInternalURL: upstream.URL}}
	out, status := srv.fetchBookChaptersInternal(bookID, 20, 0)
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d out=%v", status, out)
	}
}

func TestFetchBookChapterInternal(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	chapterID := uuid.New()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		wantPath := "/internal/books/" + bookID.String() + "/chapters/" + chapterID.String()
		if r.URL.Path != wantPath {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"chapter_id": chapterID,
			"body":       "hello world",
		})
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{BookServiceInternalURL: upstream.URL}}
	out, status := srv.fetchBookChapterInternal(bookID, chapterID)
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d out=%v", status, out)
	}
}

// ── W11-M3 public canon-only lore ─────────────────────────────────────────────

func TestUnlistedLoreBeforeChapterIndex(t *testing.T) {
	// Glossary is exclusive (chapter_index < before), so N → N+1 to include chapter N.
	// Absent → (-1, valid) = whole canon; malformed/negative → (_, INVALID) = 400.
	type want struct {
		idx   int
		valid bool
	}
	cases := map[string]want{
		"":    {-1, true}, // absent → deliberate whole-canon
		"0":   {1, true},
		"5":   {6, true},
		"12":  {13, true},
		"-3":  {0, false}, // negative → invalid (fail closed, not whole-canon)
		"abc": {0, false}, // malformed → invalid
	}
	for in, w := range cases {
		gotIdx, gotOK := unlistedLoreBeforeChapterIndex(in)
		if gotIdx != w.idx || gotOK != w.valid {
			t.Fatalf("before_chapter=%q: want (%d,%v), got (%d,%v)", in, w.idx, w.valid, gotIdx, gotOK)
		}
	}
}

// The load-bearing security assertion: the public lore fetch MUST pin canon-only
// (status=active) so a status='draft'/ai-suggested entity can never reach the
// public surface — never relying on the implicit "drafts have no chapter links".
// The mock emits the REAL wire shape — a BARE JSON ARRAY (getKnownEntities), NOT an
// {entities,count} object — because a prior object-decode silently failed and the
// route always returned empty while an object-mock test passed against fiction.
func TestFetchCanonLoreInternalPinsCanonOnly(t *testing.T) {
	var gotQuery string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[{"entity_id":"e1","name":"Alice","kind_code":"character"}]`))
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{GlossaryServiceInternalURL: upstream.URL}}
	ents, status := srv.fetchCanonLoreInternal(uuid.New(), 6, 50)
	if status != http.StatusOK {
		t.Fatalf("expected 200, got %d", status)
	}
	if !strings.Contains(gotQuery, "status=active") {
		t.Fatalf("canon-only NOT enforced — query missing status=active: %s", gotQuery)
	}
	if !strings.Contains(gotQuery, "before_chapter_index=6") {
		t.Fatalf("spoiler window not passed: %s", gotQuery)
	}
	if !strings.Contains(gotQuery, "alive=true") || !strings.Contains(gotQuery, "min_frequency=1") {
		t.Fatalf("belt-and-suspenders filters missing: %s", gotQuery)
	}
	// The bare array must decode to the entity slice (the shape-bug regression).
	if len(ents) != 1 || ents[0]["name"] != "Alice" {
		t.Fatalf("expected the bare-array entity to decode, got %v", ents)
	}
}

func TestFetchCanonLoreInternalUpstreamErrorDegrades(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer upstream.Close()
	srv := &Server{cfg: &config.Config{GlossaryServiceInternalURL: upstream.URL}}
	_, status := srv.fetchCanonLoreInternal(uuid.New(), -1, 50)
	if status == http.StatusOK {
		t.Fatalf("expected non-200 on upstream 500, got %d", status)
	}
}
