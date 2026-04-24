package api

import (
	"bytes"
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

func TestParseSortRange(t *testing.T) {
	t.Parallel()

	// Unset params → (nil, nil, true) so the caller skips the filter.
	req := httptest.NewRequest(http.MethodGet, "/?limit=10", nil)
	from, to, ok := parseSortRange(req)
	if !ok || from != nil || to != nil {
		t.Fatalf("expected (nil, nil, true) for unset params, got (%v, %v, %v)", from, to, ok)
	}

	// Both set → both parsed.
	req = httptest.NewRequest(http.MethodGet, "/?from_sort=3&to_sort=7", nil)
	from, to, ok = parseSortRange(req)
	if !ok || from == nil || *from != 3 || to == nil || *to != 7 {
		t.Fatalf("expected (3, 7, true), got (%v, %v, %v)", derefInt(from), derefInt(to), ok)
	}

	// Only from set → to remains nil (unbounded upper end).
	req = httptest.NewRequest(http.MethodGet, "/?from_sort=5", nil)
	from, to, ok = parseSortRange(req)
	if !ok || from == nil || *from != 5 || to != nil {
		t.Fatalf("expected (5, nil, true), got (%v, %v, %v)", derefInt(from), derefInt(to), ok)
	}

	// from_sort=0 must NOT be treated as "unset" — the pointer is the
	// difference. If this regresses, from_sort=0 silently becomes a
	// no-op filter and users asking for "from chapter 0" would get the
	// whole book back.
	req = httptest.NewRequest(http.MethodGet, "/?from_sort=0&to_sort=2", nil)
	from, to, ok = parseSortRange(req)
	if !ok || from == nil || *from != 0 || to == nil || *to != 2 {
		t.Fatalf("expected (0, 2, true), got (%v, %v, %v)", derefInt(from), derefInt(to), ok)
	}

	// Malformed → ok=false so the handler can 400.
	for _, url := range []string{
		"/?from_sort=abc",
		"/?to_sort=-1",
		"/?from_sort=1.5",
		"/?from_sort=&to_sort=notnum",
	} {
		req = httptest.NewRequest(http.MethodGet, url, nil)
		if _, _, ok := parseSortRange(req); ok {
			t.Fatalf("expected ok=false for %s", url)
		}
	}
}

func derefInt(p *int) any {
	if p == nil {
		return nil
	}
	return *p
}

func TestBuildSortRangeFilter(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	baseSel := "c.book_id=$1 AND c.lifecycle_state='active'"
	baseCnt := "book_id=$1 AND lifecycle_state='active'"

	// No range → unchanged clauses, args untouched.
	sel, cnt, args := buildSortRangeFilter(baseSel, baseCnt, []any{bookID}, nil, nil)
	if sel != baseSel || cnt != baseCnt || len(args) != 1 {
		t.Fatalf("nil range: got sel=%q cnt=%q args=%d", sel, cnt, len(args))
	}

	// Both ends → $2, $3 placeholders in order appended.
	from, to := 3, 7
	sel, cnt, args = buildSortRangeFilter(baseSel, baseCnt, []any{bookID}, &from, &to)
	wantSel := baseSel + " AND c.sort_order >= $2 AND c.sort_order <= $3"
	wantCnt := baseCnt + " AND sort_order >= $2 AND sort_order <= $3"
	if sel != wantSel || cnt != wantCnt {
		t.Fatalf("both ends: got sel=%q cnt=%q", sel, cnt)
	}
	if len(args) != 3 || args[1] != 3 || args[2] != 7 {
		t.Fatalf("both ends: got args=%v", args)
	}

	// Only to_sort → $2 used for the upper bound even when from is nil.
	sel, cnt, args = buildSortRangeFilter(baseSel, baseCnt, []any{bookID}, nil, &to)
	if sel != baseSel+" AND c.sort_order <= $2" {
		t.Fatalf("to-only sel: %q", sel)
	}
	if cnt != baseCnt+" AND sort_order <= $2" {
		t.Fatalf("to-only cnt: %q", cnt)
	}
	if len(args) != 2 || args[1] != 7 {
		t.Fatalf("to-only args: %v", args)
	}

	// Regression: from_sort=0 must produce a placeholder, not be
	// collapsed as unset. Without pointer semantics, the SQL would
	// drop the filter and return the full book.
	zero := 0
	sel, _, args = buildSortRangeFilter(baseSel, baseCnt, []any{bookID}, &zero, nil)
	if sel != baseSel+" AND c.sort_order >= $2" {
		t.Fatalf("from=0 sel: %q", sel)
	}
	if len(args) != 2 || args[1] != 0 {
		t.Fatalf("from=0 args: %v", args)
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

// C6 — non-DB paths of the batch chapter-title handler. DB-backed
// happy path is covered by knowledge-service integration tests (the
// book-service server_test.go convention is helper-level + HTTP
// parsing, NOT pool-backed integration). The handler returns early
// before touching the pool for empty list / oversized / invalid
// JSON, so a zero-value Server{} suffices here.
func TestPostInternalChapterTitles_EmptyList(t *testing.T) {
	t.Parallel()
	s := &Server{}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/titles",
		strings.NewReader(`{"chapter_ids": []}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterTitles(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("empty list: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var body struct {
		Titles map[string]string `json:"titles"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if len(body.Titles) != 0 {
		t.Fatalf("empty list: want empty titles map, got %v", body.Titles)
	}
}

func TestPostInternalChapterTitles_OversizedRejected(t *testing.T) {
	t.Parallel()
	s := &Server{}
	// 201 fake UUIDs = just above the 200 cap.
	ids := make([]string, 201)
	for i := range ids {
		ids[i] = uuid.New().String()
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": ids})
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/titles",
		bytes.NewReader(body),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterTitles(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("oversized: want 422, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestPostInternalChapterTitles_InvalidJSON(t *testing.T) {
	t.Parallel()
	s := &Server{}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/titles",
		strings.NewReader(`{not json`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterTitles(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("invalid JSON: want 400, got %d body=%s", w.Code, w.Body.String())
	}
}

// ── C12a (D-K16.2-02b) — postInternalChapterSortOrders ──────────────

func TestPostInternalChapterSortOrders_EmptyList(t *testing.T) {
	t.Parallel()
	s := &Server{}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/sort-orders",
		strings.NewReader(`{"chapter_ids": []}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterSortOrders(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("empty list: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var body struct {
		SortOrders map[string]int `json:"sort_orders"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if len(body.SortOrders) != 0 {
		t.Fatalf("empty list: want empty sort_orders map, got %v", body.SortOrders)
	}
}

func TestPostInternalChapterSortOrders_OversizedRejected(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ids := make([]string, 201)
	for i := range ids {
		ids[i] = uuid.New().String()
	}
	body, _ := json.Marshal(map[string]any{"chapter_ids": ids})
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/sort-orders",
		bytes.NewReader(body),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterSortOrders(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("oversized: want 422, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestPostInternalChapterSortOrders_InvalidJSON(t *testing.T) {
	t.Parallel()
	s := &Server{}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/chapters/sort-orders",
		strings.NewReader(`{not json`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	s.postInternalChapterSortOrders(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("invalid JSON: want 400, got %d body=%s", w.Code, w.Body.String())
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
