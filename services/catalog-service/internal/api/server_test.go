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
	"github.com/google/uuid"

	"github.com/loreweave/catalog-service/internal/config"
)

func TestFetchPublicIDs(t *testing.T) {
	t.Parallel()
	var gotQuery string
	id := uuid.New()
	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{id.String()},
			"total":    1,
		})
	}))
	defer sharing.Close()

	srv := &Server{cfg: &config.Config{SharingServiceInternalURL: sharing.URL}}
	out, status := srv.fetchPublicIDs(10, 5)
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d", status)
	}
	if len(out.BookIDs) != 1 || out.BookIDs[0] != id {
		t.Fatalf("unexpected book ids: %+v", out.BookIDs)
	}
	// TOOLV2 LOOP #141 — this assertion used to require `q=hello+world` in the outbound query,
	// which pinned a silent seam rather than a behaviour: sharing_policies is (book_id,
	// visibility) with no title, its handler reads only limit/offset, and the parameter was
	// discarded on arrival. A test asserting that we SEND a dead parameter is exactly what let
	// the catalogue's free-text search return the unfiltered list for as long as it existed.
	if strings.Contains(gotQuery, "q=") {
		t.Fatalf("q must not be forwarded to a service that cannot see titles, got %q", gotQuery)
	}
	if !strings.Contains(gotQuery, "limit=10") || !strings.Contains(gotQuery, "offset=5") {
		t.Fatalf("paging must still be forwarded, got %q", gotQuery)
	}
}

func TestListPublicBooksFiltersInactive(t *testing.T) {
	t.Parallel()
	activeID := uuid.New()
	trashedID := uuid.New()

	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{activeID.String(), trashedID.String()},
			"total":    2,
		})
	}))
	defer sharing.Close()

	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimPrefix(r.URL.Path, "/internal/books/")
		id = strings.TrimSuffix(id, "/projection")
		state := "active"
		title := "Active Book"
		if id == trashedID.String() {
			state = "trashed"
			title = "Trashed Book"
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":           id,
			"title":             title,
			"lifecycle_state":   state,
			"chapter_count":     1,
			"original_language": "en",
			"created_at":        time.Now().UTC(),
		})
	}))
	defer book.Close()

	srv := &Server{
		cfg: &config.Config{
			SharingServiceInternalURL: sharing.URL,
			BookServiceInternalURL:    book.URL,
		},
	}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/catalog/books", nil)
	srv.listPublicBooks(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rr.Code)
	}
	var body struct {
		Items []map[string]any `json:"items"`
		Total int              `json:"total"`
	}
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 {
		t.Fatalf("expected only active projection, got %d items", len(body.Items))
	}
}

func TestGetPublicBookInvalidUUID(t *testing.T) {
	t.Parallel()
	srv := &Server{cfg: &config.Config{}}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/catalog/books/bad-id", nil)
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", "bad-id")
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
	srv.getPublicBook(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}

func TestFetchPublicChapterList(t *testing.T) {
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
	out, status := srv.fetchPublicChapterList(bookID, 20, 0)
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d out=%v", status, out)
	}
}

func TestFetchPublicChapterDetail(t *testing.T) {
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
			"body":       "reader text",
		})
	}))
	defer upstream.Close()

	srv := &Server{cfg: &config.Config{BookServiceInternalURL: upstream.URL}}
	out, status := srv.fetchPublicChapterDetail(bookID, chapterID)
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d out=%v", status, out)
	}
}

// TOOLV2 LOOP #141 — the catalogue's free-text search returned the ENTIRE public catalogue.
//
// Measured live on catalog_list_public_books, the tool's first ever invocation: query="zzznomatch"
// returned total=1 with the one public book, identical to the bare call and to a query that
// genuinely matched. author, language and genre all filtered correctly; only `query` did nothing.
//
// The cause was a filter applied in the wrong service. `q` was forwarded to sharing-service, whose
// public list is `SELECT book_id FROM sharing_policies WHERE visibility='public'` — a table of
// (book_id, visibility) that has never held a title and whose handler reads only limit and offset.
// The parameter was discarded on arrival, while catalog-service, which does hold the title in the
// projection it fetches for every candidate, filtered language/genre/author locally and left the
// advertised search out of that list.
//
// This drives the real handler through the same stubs as the test above, so it fails if the filter
// is removed OR if it is applied to the wrong field.
func TestFreeTextQueryActuallyFiltersByTitle(t *testing.T) {
	t.Parallel()
	dragonID, harbourID := uuid.New(), uuid.New()

	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{dragonID.String(), harbourID.String()},
			"total":    2,
		})
	}))
	defer sharing.Close()

	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimPrefix(strings.TrimSuffix(r.URL.Path, "/projection"), "/internal/books/")
		title := "The Dragon of Elsewhere"
		if id == harbourID.String() {
			title = "Harbour Lights"
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":         id,
			"title":           title,
			"lifecycle_state": "active",
			"chapter_count":   1,
			"created_at":      time.Now().UTC(),
		})
	}))
	defer book.Close()

	srv := &Server{cfg: &config.Config{
		SharingServiceInternalURL: sharing.URL,
		BookServiceInternalURL:    book.URL,
	}}

	list := func(rawQuery string) (titles []string, total int) {
		rr := httptest.NewRecorder()
		srv.listPublicBooks(rr, httptest.NewRequest(http.MethodGet, "/v1/catalog/books?"+rawQuery, nil))
		if rr.Code != http.StatusOK {
			t.Fatalf("q=%q: expected 200, got %d", rawQuery, rr.Code)
		}
		var body struct {
			Items []map[string]any `json:"items"`
			Total int              `json:"total"`
		}
		if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
			t.Fatalf("q=%q: decode: %v", rawQuery, err)
		}
		for _, it := range body.Items {
			titles = append(titles, it["title"].(string))
		}
		return titles, body.Total
	}

	// The control: no query returns both, so a filtered result is the filter working rather
	// than the stubs being empty. Without this, every assertion below passes on a broken fetch.
	if titles, total := list(""); len(titles) != 2 || total != 2 {
		t.Fatalf("control: expected both books, got %v (total %d)", titles, total)
	}

	// A query matching nothing must return nothing. This is the measured defect: it returned
	// the full catalogue.
	if titles, total := list("q=zzznomatch"); len(titles) != 0 || total != 0 {
		t.Errorf("a non-matching query must return no books, got %v (total %d)", titles, total)
	}

	// A query matching one must return exactly that one — and `total` must agree, or the caller
	// pages through a count that does not describe its own result set.
	titles, total := list("q=dragon") // lower-case against a capitalised title: case-insensitive
	if len(titles) != 1 || titles[0] != "The Dragon of Elsewhere" || total != 1 {
		t.Errorf("expected only the Dragon title, got %v (total %d)", titles, total)
	}

	// Mid-word substring, because the catalogue is multilingual: a token-based match degrades on
	// CJK, where a title carries no spaces to tokenize on.
	if titles, _ := list("q=arbour"); len(titles) != 1 || titles[0] != "Harbour Lights" {
		t.Errorf("substring match must work mid-word, got %v", titles)
	}

	// Whitespace-only is not a filter — it must behave as an absent query rather than matching
	// every title that happens to contain a space (and none of a CJK catalogue's titles).
	if titles, _ := list("q=%20%20"); len(titles) != 2 {
		t.Errorf("a whitespace-only query must not filter, got %v", titles)
	}
}
