package api

// 28 AN-7 (B2/B3) DB-gated test for the book_search MCP tool. Real Postgres
// because it exercises the actual runLexicalSearch engine (ILIKE + pg_trgm over
// chapter_blocks). Gated on BOOK_TEST_DATABASE_URL (dbTestServer skips when
// unset). Reuses seedSearchableChapters (search_offset_db_test.go) so the MCP and
// REST front doors are proven over the same seed shape.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

// The MCP tool finds a literal substring the same way the REST route does, and
// surfaces has_more when the page is full.
func TestMCPBookSearch_FindsLiteral_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	// 5 chapters, each carrying the literal term "Thần Hồn" (CJK/VN — the exact
	// class of term the trigram operator misses but ILIKE catches).
	bookID, _ := seedSearchableChapters(t, ctx, pool, owner, 5, "Thần Hồn")
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	uctx := identityCtxForTest(t, owner)

	_, out, err := s.toolBookSearch(uctx, nil, searchToolIn{BookID: bookID.String(), Q: "Thần Hồn"})
	if err != nil {
		t.Fatalf("book_search: %v", err)
	}
	if out.Mode != "lexical" {
		t.Fatalf("mode = %q, want lexical", out.Mode)
	}
	if len(out.Results) == 0 {
		t.Fatal("literal substring search found nothing — engine not wired")
	}
	// Every seeded chapter is an exact hit; the default limit (20) exceeds 5, so
	// the page is not full → has_more false.
	if out.HasMore {
		t.Fatalf("has_more should be false (5 hits < default limit): %+v", out)
	}
	// A full page (limit == hit count) reports has_more.
	_, out2, err := s.toolBookSearch(uctx, nil, searchToolIn{BookID: bookID.String(), Q: "Thần Hồn", Limit: 2})
	if err != nil {
		t.Fatalf("book_search paged: %v", err)
	}
	if len(out2.Results) != 2 || !out2.HasMore {
		t.Fatalf("limit=2 should return 2 results with has_more=true: %d results, has_more=%v", len(out2.Results), out2.HasMore)
	}
}

// The adapter re-enforces the engine's query + enum validators.
func TestMCPBookSearch_RejectsBadInput_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedSearchableChapters(t, ctx, pool, owner, 1, "griffin")
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	uctx := identityCtxForTest(t, owner)

	// empty query
	if _, _, err := s.toolBookSearch(uctx, nil, searchToolIn{BookID: bookID.String(), Q: "   "}); err == nil {
		t.Fatal("empty q must be rejected")
	}
	// bad surface enum
	if _, _, err := s.toolBookSearch(uctx, nil, searchToolIn{BookID: bookID.String(), Q: "griffin", Surface: "sideways"}); err == nil {
		t.Fatal("invalid surface must be rejected")
	}
	// bad granularity enum
	if _, _, err := s.toolBookSearch(uctx, nil, searchToolIn{BookID: bookID.String(), Q: "griffin", Granularity: "paragraph"}); err == nil {
		t.Fatal("invalid granularity must be rejected")
	}
}
