package api

// A5 (search.go OFFSET fix) — DB-gated regression test proving page 2+ of a
// raw-search query now returns DIFFERENT rows instead of the old "offset
// ignored" behavior (LOW-3). Real Postgres because it exercises the actual
// LIMIT/OFFSET SQL + pg_trgm/similarity ranking. Gated on
// BOOK_TEST_DATABASE_URL like the other *_db_test.go files.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// seedSearchableChapters seeds an active book with n active chapters, each
// with one chapter_blocks row containing the given term (so every chapter is
// an exact-substring hit, letting ORDER BY fall back to sort_order/block_index
// as the deterministic tiebreak — needed so page1/page2 are reproducible).
func seedSearchableChapters(t *testing.T, ctx context.Context, pool *pgxpool.Pool, owner uuid.UUID, n int, term string) (bookID uuid.UUID, chapterIDs []uuid.UUID) {
	t.Helper()
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'search-offset-test') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	for i := 0; i < n; i++ {
		var chID uuid.UUID
		if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state)
VALUES($1,'c.txt','en','text/plain',$2,'k','active') RETURNING id`, bookID, i+1).Scan(&chID); err != nil {
			t.Fatalf("seed chapter %d: %v", i, err)
		}
		chapterIDs = append(chapterIDs, chID)
		text := fmt.Sprintf("a %s appears in chapter %d", term, i)
		if _, err := pool.Exec(ctx, `
INSERT INTO chapter_blocks(chapter_id, block_index, block_type, text_content, content_hash)
VALUES ($1, 0, 'paragraph', $2, 'h')`, chID, text); err != nil {
			t.Fatalf("seed block %d: %v", i, err)
		}
	}
	return bookID, chapterIDs
}

func searchGET(t *testing.T, s *Server, caller uuid.UUID, bookID uuid.UUID, query string) []map[string]any {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/search?"+query, nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("search = %d, want 200\n%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Results []map[string]any `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v — %s", err, rr.Body.String())
	}
	return out.Results
}

// Default surface=draft, granularity=chapter (lexicalSearchChapterSQL) —
// page 2 must return DIFFERENT chapters than page 1, not the same page
// repeated (the pre-A5 bug: offset was always ignored).
func TestSearchOffset_ChapterGranularity_PagesDiffer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chIDs := seedSearchableChapters(t, ctx, pool, owner, 5, "wizard")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	_ = chIDs

	page1 := searchGET(t, s, owner, bookID, "q=wizard&limit=2&offset=0")
	page2 := searchGET(t, s, owner, bookID, "q=wizard&limit=2&offset=2")
	if len(page1) != 2 || len(page2) != 2 {
		t.Fatalf("expected 2 hits per page, got page1=%d page2=%d", len(page1), len(page2))
	}
	seen := map[string]bool{}
	for _, r := range page1 {
		seen[fmt.Sprint(r["chapterId"])] = true
	}
	for _, r := range page2 {
		if seen[fmt.Sprint(r["chapterId"])] {
			t.Fatalf("page 2 repeated a chapter from page 1 — offset was ignored: %v", r["chapterId"])
		}
	}
}

// Same check for granularity=block (the flat lexicalSearchSQL variant).
func TestSearchOffset_BlockGranularity_PagesDiffer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedSearchableChapters(t, ctx, pool, owner, 5, "griffin")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	page1 := searchGET(t, s, owner, bookID, "q=griffin&granularity=block&limit=2&offset=0")
	page2 := searchGET(t, s, owner, bookID, "q=griffin&granularity=block&limit=2&offset=2")
	if len(page1) != 2 || len(page2) != 2 {
		t.Fatalf("expected 2 hits per page, got page1=%d page2=%d", len(page1), len(page2))
	}
	seen := map[string]bool{}
	for _, r := range page1 {
		seen[fmt.Sprint(r["chapterId"])] = true
	}
	overlap := 0
	for _, r := range page2 {
		if seen[fmt.Sprint(r["chapterId"])] {
			overlap++
		}
	}
	if overlap == len(page2) {
		t.Fatalf("page 2 (block granularity) identical to page 1 — offset was ignored")
	}
}

// Offset past the end of the result set must return an empty array, not an error.
func TestSearchOffset_PastEnd_ReturnsEmpty_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedSearchableChapters(t, ctx, pool, owner, 2, "phoenix")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	results := searchGET(t, s, owner, bookID, "q=phoenix&limit=10&offset=100")
	if len(results) != 0 {
		t.Fatalf("offset past the end should return 0 results, got %d", len(results))
	}
}

// surface=all merges draft+canon; offset must page over the MERGED, re-ranked
// set correctly (not naively pushed into each leg — see runLexicalSearch's doc
// comment). With only a draft leg populated here, this also proves the "all"
// path doesn't regress to 0 results or double-count when canon is empty.
func TestSearchOffset_AllSurface_PagesDiffer_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedSearchableChapters(t, ctx, pool, owner, 5, "dragon")
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	page1 := searchGET(t, s, owner, bookID, "q=dragon&surface=all&limit=2&offset=0")
	page2 := searchGET(t, s, owner, bookID, "q=dragon&surface=all&limit=2&offset=2")
	if len(page1) != 2 || len(page2) != 2 {
		t.Fatalf("expected 2 hits per page, got page1=%d page2=%d", len(page1), len(page2))
	}
	seen := map[string]bool{}
	for _, r := range page1 {
		seen[fmt.Sprint(r["chapterId"])+fmt.Sprint(r["location"])] = true
	}
	for _, r := range page2 {
		key := fmt.Sprint(r["chapterId"]) + fmt.Sprint(r["location"])
		if seen[key] {
			t.Fatalf("surface=all page 2 repeated a page-1 hit — merge offset slicing is wrong: %v", r)
		}
	}
}
