package api

// S-07 §3 — book_chapter_reorder MCP tool. DB-gated (real Postgres): the whole point is the
// two-phase write dodging the partial UNIQUE(book_id, sort_order, original_language), which a
// mock can't prove. Reuses seedActiveChapters / liveOrder from chapter_reorder_db_test.go.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func idStrs(ids []uuid.UUID) []string {
	out := make([]string, len(ids))
	for i, id := range ids {
		out[i] = id.String()
	}
	return out
}

// TestChapterReorder_MCP — a full-list reorder through the tool matches what the REST route
// produces (dense 1..N, the requested order) with no transient unique collision.
func TestChapterReorder_MCP(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 4)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	toolCtx := identityCtxForTest(t, owner)

	// A non-trivial permutation of all four.
	want := []uuid.UUID{ch[2], ch[0], ch[3], ch[1]}
	_, out, err := s.toolChapterReorder(toolCtx, nil, chapterReorderIn{
		BookID: bookID.String(), ChapterIDs: idStrs(want),
	})
	if err != nil {
		t.Fatalf("reorder: %v", err)
	}
	// The tool returns the dense 1..N slots in the requested order.
	if len(out.Chapters) != 4 {
		t.Fatalf("expected 4 chapters back, got %d", len(out.Chapters))
	}
	for i, rc := range out.Chapters {
		if rc.ChapterID != want[i] || rc.SortOrder != i+1 {
			t.Fatalf("out[%d] = {%s, %d}, want {%s, %d}", i, rc.ChapterID, rc.SortOrder, want[i], i+1)
		}
	}
	// And the DB agrees — the persisted reading order IS the requested permutation, dense.
	got := liveOrder(t, ctx, pool, bookID)
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("persisted order[%d] = %s, want %s (full: %v)", i, got[i], want[i], got)
		}
	}
}

// TestChapterReorder_MCP_RejectsBadLists — a partial / foreign / duplicated list is a
// validation error, never a silent partial reorder that would strand a slot.
func TestChapterReorder_MCP_RejectsBadLists(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 3)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	toolCtx := identityCtxForTest(t, owner)

	// partial (2 of 3) → "exactly once"
	_, _, err := s.toolChapterReorder(toolCtx, nil, chapterReorderIn{
		BookID: bookID.String(), ChapterIDs: idStrs(ch[:2]),
	})
	if err == nil || !strings.Contains(err.Error(), "exactly once") {
		t.Fatalf("partial list must be rejected, got: %v", err)
	}

	// foreign chapter swapped in → "not an active chapter"
	foreign := []uuid.UUID{ch[0], ch[1], uuid.New()}
	_, _, err = s.toolChapterReorder(toolCtx, nil, chapterReorderIn{
		BookID: bookID.String(), ChapterIDs: idStrs(foreign),
	})
	if err == nil || !strings.Contains(err.Error(), "not an active chapter") {
		t.Fatalf("foreign chapter must be rejected, got: %v", err)
	}

	// duplicate id → "not repeat"
	dupe := []uuid.UUID{ch[0], ch[0], ch[1]}
	_, _, err = s.toolChapterReorder(toolCtx, nil, chapterReorderIn{
		BookID: bookID.String(), ChapterIDs: idStrs(dupe),
	})
	if err == nil || !strings.Contains(err.Error(), "repeat") {
		t.Fatalf("duplicate id must be rejected, got: %v", err)
	}

	// empty list → required
	_, _, err = s.toolChapterReorder(toolCtx, nil, chapterReorderIn{BookID: bookID.String()})
	if err == nil || !strings.Contains(err.Error(), "required") {
		t.Fatalf("empty list must be rejected, got: %v", err)
	}

	// the manuscript was NOT mutated by any of the rejected calls (still the seeded order).
	got := liveOrder(t, ctx, pool, bookID)
	for i := range ch {
		if got[i] != ch[i] {
			t.Fatalf("a rejected reorder mutated the order: got %v, want %v", got, ch)
		}
	}
}

// TestChapterReorder_MCP_RequiresEdit — a view-only grant cannot reorder (edit-gated).
func TestChapterReorder_MCP_RequiresEdit(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 3)
	// A viewer (below Edit) is refused before any write.
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantView, owner, "active", nil
	}
	toolCtx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolChapterReorder(toolCtx, nil, chapterReorderIn{
		BookID: bookID.String(), ChapterIDs: idStrs([]uuid.UUID{ch[2], ch[1], ch[0]}),
	}); err == nil {
		t.Fatal("a view-only grant must not reorder")
	}
}
