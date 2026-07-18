package api

// W11-M1 (spec §4.1) — DB-gated tests for the reading-position resolver's SQL,
// the load-bearing bit the pre-pool guard tests can't reach: furthest = MAX
// sort_order over the reader's ACTIVE read chapters (soft-deleted chapters
// excluded), and a reader with no active read chapter → null position (the
// facade's fail-closed input). Gating matches the other *_db_test.go files:
// requires BOOK_TEST_DATABASE_URL, else skipped.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func seedChapterAt(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID, sortOrder int, lifecycle string) uuid.UUID {
	t.Helper()
	var chID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',$2,'k',$3,'draft') RETURNING id`, bookID, sortOrder, lifecycle).Scan(&chID); err != nil {
		t.Fatalf("seed chapter (sort=%d, %s): %v", sortOrder, lifecycle, err)
	}
	return chID
}

func seedReadRow(t *testing.T, ctx context.Context, pool *pgxpool.Pool, userID, bookID, chID uuid.UUID) {
	t.Helper()
	if _, err := pool.Exec(ctx,
		`INSERT INTO reading_progress(user_id,book_id,chapter_id,time_spent_ms,scroll_depth,read_count) VALUES($1,$2,$3,100,0.5,1)`,
		userID, bookID, chID); err != nil {
		t.Fatalf("seed reading_progress: %v", err)
	}
}

func readingPosition(t *testing.T, s *Server, bookID, userID uuid.UUID) map[string]any {
	t.Helper()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet,
		"/internal/books/"+bookID.String()+"/reading-position?user_id="+userID.String(),
		"", "", map[string]string{"book_id": bookID.String()})
	s.getInternalReadingPosition(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rr.Code, rr.Body.String())
	}
	var out map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return out
}

func seedBook(t *testing.T, ctx context.Context, pool *pgxpool.Pool, ownerID uuid.UUID) uuid.UUID {
	t.Helper()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'t') RETURNING id`, ownerID).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	return bookID
}

// Reader read chapters 1 and 3 (both active) → furthest is chapter 3.
func TestReadingPositionReturnsFurthestActiveChapter(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner, reader := uuid.New(), uuid.New()
	bookID := seedBook(t, ctx, pool, owner)
	ch1 := seedChapterAt(t, ctx, pool, bookID, 1, "active")
	seedChapterAt(t, ctx, pool, bookID, 2, "active")
	ch3 := seedChapterAt(t, ctx, pool, bookID, 3, "active")
	seedReadRow(t, ctx, pool, reader, bookID, ch1)
	seedReadRow(t, ctx, pool, reader, bookID, ch3)

	out := readingPosition(t, s, bookID, reader)
	if got := out["furthest_sort_order"].(float64); got != 3 {
		t.Fatalf("expected furthest_sort_order 3, got %v", got)
	}
	if out["furthest_chapter_id"].(string) != ch3.String() {
		t.Fatalf("expected furthest_chapter_id %s, got %v", ch3, out["furthest_chapter_id"])
	}
}

// The reader's furthest-read chapter (sort 3) was SOFT-deleted → the resolver must
// fall through to the furthest ACTIVE read chapter (sort 2), not return the deleted
// one. This is the fail-open the review caught: an INNER JOIN alone keeps the
// soft-deleted row (it isn't hard-deleted), so without the lifecycle filter a
// reader would be windowed at a chapter the sort-order resolver later drops.
func TestReadingPositionExcludesSoftDeletedChapter(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner, reader := uuid.New(), uuid.New()
	bookID := seedBook(t, ctx, pool, owner)
	ch1 := seedChapterAt(t, ctx, pool, bookID, 1, "active")
	ch2 := seedChapterAt(t, ctx, pool, bookID, 2, "active")
	ch3 := seedChapterAt(t, ctx, pool, bookID, 3, "deleted") // soft-deleted, row survives
	seedReadRow(t, ctx, pool, reader, bookID, ch1)
	seedReadRow(t, ctx, pool, reader, bookID, ch2)
	seedReadRow(t, ctx, pool, reader, bookID, ch3)

	out := readingPosition(t, s, bookID, reader)
	if got := out["furthest_sort_order"].(float64); got != 2 {
		t.Fatalf("expected furthest_sort_order 2 (soft-deleted ch3 excluded), got %v", got)
	}
	if out["furthest_chapter_id"].(string) != ch2.String() {
		t.Fatalf("expected furthest_chapter_id %s (ch2), got %v", ch2, out["furthest_chapter_id"])
	}
}

// No reading rows → null position (fail-closed input for the facade).
func TestReadingPositionEmptyReaderIsNull(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner, reader := uuid.New(), uuid.New()
	bookID := seedBook(t, ctx, pool, owner)
	seedChapterAt(t, ctx, pool, bookID, 1, "active")

	out := readingPosition(t, s, bookID, reader)
	if out["furthest_chapter_id"] != nil || out["furthest_sort_order"] != nil {
		t.Fatalf("expected null position for a reader with no progress, got %+v", out)
	}
}

// The reader's ONLY read chapter was soft-deleted → null (fail-closed), never the
// deleted chapter.
func TestReadingPositionAllReadChaptersDeletedIsNull(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner, reader := uuid.New(), uuid.New()
	bookID := seedBook(t, ctx, pool, owner)
	chDel := seedChapterAt(t, ctx, pool, bookID, 1, "deleted")
	seedReadRow(t, ctx, pool, reader, bookID, chDel)

	out := readingPosition(t, s, bookID, reader)
	if out["furthest_chapter_id"] != nil || out["furthest_sort_order"] != nil {
		t.Fatalf("expected null position when all read chapters are soft-deleted, got %+v", out)
	}
}
