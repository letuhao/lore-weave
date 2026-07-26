package api

// prose_state_db_test.go — the REAL-SQL proof for GET /internal/books/{book_id}/prose-state.
//
// A fake/mock querier records the statement but never executes it, so the FILTER + the
// two EXISTS predicates (the entire substance of this endpoint) are only actually
// exercised here. DB-gated like mcp_actions_db_test.go: needs BOOK_TEST_DATABASE_URL
// (real PG18 — jsonb_path_query / uuidv7), else skipped.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

type proseStateResp struct {
	BookID    string `json:"book_id"`
	Chapters  int    `json:"chapters"`
	WithProse int    `json:"with_prose"`
}

func getProseState(t *testing.T, s *Server, bookID uuid.UUID) (int, proseStateResp) {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/internal/books/"+bookID.String()+"/prose-state", nil)
	req.Header.Set(lwmcp.HeaderInternalToken, mcpTestToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	var out proseStateResp
	if rr.Code == http.StatusOK {
		if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
			t.Fatalf("decode: %v (body=%s)", err, rr.Body.String())
		}
	}
	return rr.Code, out
}

// insertChapter adds an active chapter at the given sort slot and returns its id.
func insertChapter(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID, sort int, lifecycle string) uuid.UUID {
	t.Helper()
	var chID uuid.UUID
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,$2,'en','text/plain',$3,'k',$4,'draft') RETURNING id`,
		bookID, "c"+uuid.NewString()+".txt", sort, lifecycle).Scan(&chID); err != nil {
		t.Fatalf("seed chapter (sort=%d): %v", sort, err)
	}
	return chID
}

// The load-bearing test. A book whose prose arrives by every route the service actually
// writes it, plus the two shapes that must NOT be counted.
//
// Chapter 5 is the one that motivated this endpoint: an IMPORTED chapter whose prose is
// in chapter_raw_objects. The existing /internal/books/{id}/chapters route derives
// word_count_estimate from chapter_drafts alone, so it reports 0 words for that chapter.
//
// Chapter 3 is the one that kills the naive `EXISTS (SELECT 1 FROM chapter_drafts)`
// predicate: EVERY chapter-creation path unconditionally inserts a drafts row, and
// plainTextToTiptapJSON("") yields a structurally valid but prose-free doc. A bare EXISTS
// counts it as prose-bearing — reporting a book of blank chapters as fully written.
func TestInternalBookProseState_CountsRealProseOnly_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'prose-state') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}

	// 1. draft, standard tiptap (nested {"type":"text","text":…} leaves) → PROSE
	ch1 := insertChapter(t, ctx, pool, bookID, 1, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`,
		ch1, json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"the knight rode north"}]}]}`)); err != nil {
		t.Fatalf("seed draft ch1: %v", err)
	}

	// 2. draft, legacy editor `_text` projection (no nested text leaves) → PROSE
	ch2 := insertChapter(t, ctx, pool, bookID, 2, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`,
		ch2, json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"hello world"}]}`)); err != nil {
		t.Fatalf("seed draft ch2: %v", err)
	}

	// 3. draft, but the EMPTY doc that plainTextToTiptapJSON("") produces → NOT prose
	ch3 := insertChapter(t, ctx, pool, bookID, 3, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`,
		ch3, json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":""}]}`)); err != nil {
		t.Fatalf("seed draft ch3: %v", err)
	}

	// 4. no draft, no raw object at all → NOT prose
	_ = insertChapter(t, ctx, pool, bookID, 4, "active")

	// 5. IMPORTED: raw object only, no draft → PROSE (the /chapters route reports 0 words here)
	ch5 := insertChapter(t, ctx, pool, bookID, 5, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`,
		ch5, "It was a dark and stormy night."); err != nil {
		t.Fatalf("seed raw ch5: %v", err)
	}

	// 6. raw object present but whitespace-only → NOT prose
	ch6 := insertChapter(t, ctx, pool, bookID, 6, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, ch6, "   \n  "); err != nil {
		t.Fatalf("seed raw ch6: %v", err)
	}

	// 7. TRASHED chapter with real prose → excluded from BOTH counts (lifecycle gate)
	ch7 := insertChapter(t, ctx, pool, bookID, 7, "trashed")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, ch7, "deleted but wordy"); err != nil {
		t.Fatalf("seed raw ch7: %v", err)
	}

	// 8. draft whose text is whitespace INCLUDING NEWLINES → NOT prose. Pins the draft
	// side of the btrim bug: single-arg btrim() trims only spaces, so "\n  " survived it
	// as non-empty and this chapter was counted as prose (real PG caught it; ch6 pins the
	// same bug on the raw-object side).
	ch8 := insertChapter(t, ctx, pool, bookID, 8, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_version) VALUES($1,$2,'json',1)`,
		ch8, json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"\n  \n"}]}`)); err != nil {
		t.Fatalf("seed draft ch8: %v", err)
	}

	// A second book must not bleed into the counts (book_id scoping).
	var otherBook uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'other') RETURNING id`, owner).Scan(&otherBook); err != nil {
		t.Fatalf("seed other book: %v", err)
	}
	chOther := insertChapter(t, ctx, pool, otherBook, 1, "active")
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chOther, "someone else's novel"); err != nil {
		t.Fatalf("seed raw other: %v", err)
	}

	code, out := getProseState(t, s, bookID)
	if code != http.StatusOK {
		t.Fatalf("prose-state = %d, want 200", code)
	}
	// 7 active chapters (the trashed one is excluded); 3 of them hold real prose (1, 2, 5).
	if out.Chapters != 7 {
		t.Errorf("chapters = %d, want 7 (trashed chapter must be excluded)", out.Chapters)
	}
	if out.WithProse != 3 {
		t.Errorf("with_prose = %d, want 3 (draft-tiptap + draft-_text + imported-raw)", out.WithProse)
	}
	if out.BookID != bookID.String() {
		t.Errorf("book_id = %q, want %q", out.BookID, bookID)
	}
}

// A book with no chapters is a 200 with zeros — NOT a 404. chat-service calls this every
// turn on a brand-new book and must get a clean "empty" answer, not an error to special-case.
func TestInternalBookProseState_NoChapters_ZerosNot404_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'empty') RETURNING id`, uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}

	code, out := getProseState(t, s, bookID)
	if code != http.StatusOK {
		t.Fatalf("empty book prose-state = %d, want 200 (must not 404)", code)
	}
	if out.Chapters != 0 || out.WithProse != 0 {
		t.Fatalf("empty book: got chapters=%d with_prose=%d, want 0/0", out.Chapters, out.WithProse)
	}
}
