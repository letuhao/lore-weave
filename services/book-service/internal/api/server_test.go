package api

import (
	"bytes"
	"context"
	"encoding/base64"
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

func TestEncodeParseChapterCursorRoundTrip(t *testing.T) {
	t.Parallel()

	id := uuid.New()
	tok := encodeChapterCursor(42, id)
	gotSort, gotID, ok := parseChapterCursor(tok)
	if !ok || gotSort != 42 || gotID != id {
		t.Fatalf("round-trip failed: ok=%v sort=%d id=%s (want 42/%s)", ok, gotSort, gotID, id)
	}
	// Negative/zero sort_order must survive too (sort_order is a plain INT).
	if s, _, ok := parseChapterCursor(encodeChapterCursor(0, id)); !ok || s != 0 {
		t.Fatalf("zero sort_order round-trip failed: ok=%v s=%d", ok, s)
	}
}

func TestParseChapterCursorRejectsMalformed(t *testing.T) {
	t.Parallel()

	enc := func(s string) string { return base64.RawURLEncoding.EncodeToString([]byte(s)) }
	cases := map[string]string{
		"empty":       "",
		"bad base64":  "!!!not-base64!!!",
		"missing pipe": enc("nopipe"),
		"bad int":     enc("notanint|" + uuid.NewString()),
		"bad uuid":    enc("7|not-a-uuid"),
	}
	for name, tok := range cases {
		if _, _, ok := parseChapterCursor(tok); ok {
			t.Fatalf("%s: expected reject, got ok=true for %q", name, tok)
		}
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

func TestAppendEditorialStatusFilter(t *testing.T) {
	t.Parallel()

	bookID := uuid.New()
	baseSel := "c.book_id=$1 AND c.lifecycle_state='active'"
	baseCnt := "book_id=$1 AND lifecycle_state='active'"

	// Empty es → no-op pass-through (default: all chapters).
	sel, cnt, args := appendEditorialStatusFilter(baseSel, baseCnt, []any{bookID}, "")
	if sel != baseSel || cnt != baseCnt || len(args) != 1 {
		t.Fatalf("empty es: got sel=%q cnt=%q args=%d", sel, cnt, len(args))
	}

	// es=draft → editorial_status filter at $2, NO published_revision_id check.
	sel, cnt, args = appendEditorialStatusFilter(baseSel, baseCnt, []any{bookID}, "draft")
	if sel != baseSel+" AND c.editorial_status=$2" {
		t.Fatalf("draft sel: %q", sel)
	}
	if cnt != baseCnt+" AND editorial_status=$2" {
		t.Fatalf("draft cnt: %q", cnt)
	}
	if len(args) != 2 || args[1] != "draft" {
		t.Fatalf("draft args: %v", args)
	}

	// es=published → editorial_status filter AND published_revision_id IS NOT NULL
	// (the canon-pinnable gate, matching the worker enumeration).
	sel, cnt, args = appendEditorialStatusFilter(baseSel, baseCnt, []any{bookID}, "published")
	wantSel := baseSel + " AND c.editorial_status=$2 AND c.published_revision_id IS NOT NULL"
	wantCnt := baseCnt + " AND editorial_status=$2 AND published_revision_id IS NOT NULL"
	if sel != wantSel {
		t.Fatalf("published sel: %q", sel)
	}
	if cnt != wantCnt {
		t.Fatalf("published cnt: %q", cnt)
	}
	if len(args) != 2 || args[1] != "published" {
		t.Fatalf("published args: %v", args)
	}

	// R2-BLOCK#2 regression: when sort-range args precede it, the status
	// placeholder must be $4 (post-append len), NOT collide with $2/$3 — this
	// is exactly the arithmetic that, if wrong, silently blackouts the gate.
	from, to := 3, 7
	selR, cntR, argsR := buildSortRangeFilter(baseSel, baseCnt, []any{bookID}, &from, &to)
	selR, cntR, argsR = appendEditorialStatusFilter(selR, cntR, argsR, "published")
	if selR != baseSel+" AND c.sort_order >= $2 AND c.sort_order <= $3"+
		" AND c.editorial_status=$4 AND c.published_revision_id IS NOT NULL" {
		t.Fatalf("composed sel: %q", selR)
	}
	if cntR != baseCnt+" AND sort_order >= $2 AND sort_order <= $3"+
		" AND editorial_status=$4 AND published_revision_id IS NOT NULL" {
		t.Fatalf("composed cnt: %q", cntR)
	}
	if len(argsR) != 4 || argsR[3] != "published" {
		t.Fatalf("composed args: %v", argsR)
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

// The library search's SQL fragment. The bug this replaces was not a crash: the
// page asked for no limit, took the endpoint's default of 20, filtered those 20
// in the browser, and displayed `total` from the server. A user with 83 books was
// shown 83 and searched 20, so a book at rank 32 could not be found by name at
// all — recorded for six days as a Vietnamese diacritic defect. The encoding was
// never involved: the DB stores NFC and `title ILIKE '%Đế%'` matches. // doc-language-gate: ok -- the corpus span the bug was reported against
func TestAppendTitleSearchFilter(t *testing.T) {
	owner, lifecycle := "u1", "active"

	t.Run("no query leaves the args and the SQL untouched", func(t *testing.T) {
		frag, args := appendTitleSearchFilter("", []any{owner, lifecycle})
		if frag != "" {
			t.Fatalf("empty query must add no SQL, got %q", frag)
		}
		if len(args) != 2 {
			t.Fatalf("empty query must append no args, got %d", len(args))
		}
	})

	t.Run("the placeholder names the position the pattern lands at", func(t *testing.T) {
		frag, args := appendTitleSearchFilter("Mị Đế", []any{owner, lifecycle}) // doc-language-gate: ok -- the corpus span the bug was reported against
		if frag != " AND b.title ILIKE $3" {
			t.Fatalf("fragment = %q, want $3 (after owner, lifecycle)", frag)
		}
		if len(args) != 3 {
			t.Fatalf("args = %d, want 3", len(args))
		}
		// $3 must BE the pattern. An off-by-one here binds the lifecycle string
		// as the search term and silently returns nothing.
		if got, want := args[2], "%Mị Đế%"; got != want { // doc-language-gate: ok -- the corpus span the bug was reported against
			t.Fatalf("args[2] = %v, want %v", got, want)
		}
	})

	t.Run("the pattern survives multi-byte input verbatim", func(t *testing.T) {
		// escapeLikePattern only rewrites \, %% and _; a byte-oriented escaper
		// would corrupt these and the miss would look like a diacritic problem
		// rather than a mangled pattern.
		for _, q := range []string{"Đế", "Mị Đế", "封神演義", "Winds"} { // doc-language-gate: ok -- the corpus span the bug was reported against
			_, args := appendTitleSearchFilter(q, []any{owner, lifecycle})
			if got, want := args[2], "%"+q+"%"; got != want {
				t.Fatalf("q=%q produced %v, want %v", q, got, want)
			}
		}
	})

	t.Run("LIKE metacharacters are escaped, not honoured", func(t *testing.T) {
		_, args := appendTitleSearchFilter("100%_x", []any{owner, lifecycle})
		if got, want := args[2], `%100\%\_x%`; got != want {
			t.Fatalf("args[2] = %v, want %v", got, want)
		}
	})

	// The half that keeps `total` honest: the COUNT is built from the SAME
	// fragment and a prefix of the SAME args. If the count query were given the
	// unfiltered arg list, `total` would describe the library while `items`
	// described the search — the original defect wearing different clothes.
	t.Run("count args are a prefix of the page args", func(t *testing.T) {
		frag, args := appendTitleSearchFilter("Đế", []any{owner, lifecycle}) // doc-language-gate: ok -- the corpus span the bug was reported against
		countArgs := append([]any{}, args...)
		pageArgs := append(args, 20, 0)

		if len(countArgs) != 3 {
			t.Fatalf("count args = %d, want 3 (owner, lifecycle, pattern)", len(countArgs))
		}
		if len(pageArgs) != 5 {
			t.Fatalf("page args = %d, want 5 (+limit, offset)", len(pageArgs))
		}
		for i := range countArgs {
			if countArgs[i] != pageArgs[i] {
				t.Fatalf("arg %d diverges: count=%v page=%v", i, countArgs[i], pageArgs[i])
			}
		}
		// And the fragment the count uses must be the same string.
		if frag != " AND b.title ILIKE $3" {
			t.Fatalf("fragment = %q", frag)
		}
	})
}

// ── the library list's WIRING, not its helper (L5) ──────────────────────────
//
// `TestAppendTitleSearchFilter` above has a subtest named "count args are a prefix of the
// page args", and it demonstrates that by calling `appendTitleSearchFilter` twice and
// comparing the results to each other. It never reaches the handler. Measured on the worlds
// equivalent, which had the identical shape: deleting the predicate from the COUNT left every
// such subtest GREEN, because the pure function they drive was untouched.
//
// These drive `buildBookListQueries`, which builds both. A predicate that reaches one query
// and not the other is now visible.
func TestBuildBookListQueries(t *testing.T) {
	t.Parallel()
	owner := "u1"

	t.Run("with a query, the title predicate reaches BOTH the page and the count", func(t *testing.T) {
		pageSQL, pageArgs, countSQL, countArgs := buildBookListQueries(owner, "active", "Đế", true, 20, 0) // doc-language-gate: ok -- the corpus span the bug was reported against
		if !strings.Contains(pageSQL, "b.title ILIKE") {
			t.Fatalf("page query lost the title predicate:\n%s", pageSQL)
		}
		// THE REGRESSION THIS EXISTS FOR: an unfiltered COUNT reports `total` over the
		// whole library beside `items` from the search, so the UI says "12 of 340" for a
		// query that matched 12 and the user hunts for 328 books that are not missing.
		if !strings.Contains(countSQL, "b.title ILIKE") {
			t.Fatalf("COUNT is not filtered — total would describe the library while items "+
				"describe the search:\n%s", countSQL)
		}
		if len(countArgs) != 3 {
			t.Fatalf("count args = %d, want 3 (owner, lifecycle, pattern)", len(countArgs))
		}
		if len(pageArgs) != 5 {
			t.Fatalf("page args = %d, want 5 (+limit, offset)", len(pageArgs))
		}
		for i := range countArgs {
			if countArgs[i] != pageArgs[i] {
				t.Fatalf("arg %d diverges: count=%v page=%v", i, countArgs[i], pageArgs[i])
			}
		}
	})

	t.Run("without a query, neither carries a predicate", func(t *testing.T) {
		pageSQL, pageArgs, countSQL, countArgs := buildBookListQueries(owner, "active", "", true, 20, 0)
		if strings.Contains(pageSQL, "ILIKE") || strings.Contains(countSQL, "ILIKE") {
			t.Fatal("an empty q must add no predicate to either query")
		}
		if len(countArgs) != 2 || len(pageArgs) != 4 {
			t.Fatalf("args = count %d / page %d, want 2 and 4", len(countArgs), len(pageArgs))
		}
	})

	// EGRESS GUARD #7 rides the same accessFilter. A guard that reached the page and not
	// the count would leak through `total` — a smaller leak than a row, and still a number
	// about books the caller may not see.
	t.Run("the egress guards reach the COUNT, not just the page", func(t *testing.T) {
		for _, shared := range []bool{true, false} {
			_, _, countSQL, _ := buildBookListQueries(owner, "active", "", shared, 20, 0)
			if !strings.Contains(countSQL, "b.is_bible=false") {
				t.Fatalf("includeShared=%v: COUNT does not hide bible containers:\n%s", shared, countSQL)
			}
			if !strings.Contains(countSQL, "b.kind<>'diary'") {
				t.Fatalf("includeShared=%v: COUNT does not hide diaries:\n%s", shared, countSQL)
			}
		}
	})

	t.Run("includeShared widens BOTH queries the same way", func(t *testing.T) {
		pageSQL, _, countSQL, _ := buildBookListQueries(owner, "active", "", true, 20, 0)
		for _, sql := range []string{pageSQL, countSQL} {
			if !strings.Contains(sql, "book_collaborators") {
				t.Fatalf("includeShared did not reach a query:\n%s", sql)
			}
		}
		ownedPage, _, ownedCount, _ := buildBookListQueries(owner, "active", "", false, 20, 0)
		for _, sql := range []string{ownedPage, ownedCount} {
			if strings.Contains(sql, "EXISTS(SELECT 1 FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1)) AND") {
				t.Fatalf("owned-only leaked the shared access filter:\n%s", sql)
			}
		}
	})

	t.Run("LIMIT/OFFSET follow the search pattern, not precede it", func(t *testing.T) {
		// With a search the pattern takes $3, so the page binds $4/$5. An off-by-one here
		// pages by the search pattern and returns nothing at all.
		withQ, _, _, _ := buildBookListQueries(owner, "active", "Đế", true, 20, 0) // doc-language-gate: ok -- the corpus span the bug was reported against
		if !strings.Contains(withQ, "LIMIT $4 OFFSET $5") {
			t.Fatalf("expected LIMIT $4 OFFSET $5 with a search present:\n%s", withQ)
		}
		noQ, _, _, _ := buildBookListQueries(owner, "active", "", true, 20, 0)
		if !strings.Contains(noQ, "LIMIT $3 OFFSET $4") {
			t.Fatalf("expected LIMIT $3 OFFSET $4 with no search:\n%s", noQ)
		}
	})

	t.Run("lifecycle is BOUND, never interpolated into either query", func(t *testing.T) {
		// It is a server-chosen literal today ("active"/"trashed"), which is exactly the
		// kind of value that gets interpolated "because it is safe" and then stops being.
		//
		// The needle is the QUOTED literal `'trashed'`, not the bare word: the page SQL
		// selects `b.trashed_at` and `b.purge_eligible_at`, so a bare `Contains("trashed")`
		// matches a COLUMN NAME and fails on correct code. It did, on the first run of this
		// subtest — a test asserting something adjacent to what it meant.
		for _, sql := range func() []string {
			p, args, c, _ := buildBookListQueries(owner, "trashed", "", false, 20, 0)
			if args[1] != "trashed" {
				t.Fatalf("lifecycle is not args[1]: %v", args)
			}
			return []string{p, c}
		}() {
			if strings.Contains(sql, "'trashed'") {
				t.Fatalf("lifecycle reached the SQL text instead of the args:\n%s", sql)
			}
			if !strings.Contains(sql, "b.lifecycle_state=$2") {
				t.Fatalf("lifecycle is not bound at $2:\n%s", sql)
			}
		}
	})
}
