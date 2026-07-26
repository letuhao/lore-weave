package api

// 24 PH20 Row-3 — the transactional reading-order reorder. DB-gated (real Postgres) because the
// WHOLE POINT of this endpoint is the partial unique index `idx_chapters_unique_slot_lang_active`:
// a permutation written naively collides on it and 409s. A mock cannot prove the dodge works — only
// the real index can. Gated on BOOK_TEST_DATABASE_URL like the other *_db_test.go files.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// order reads the book's live chapter ids in reading order.
func liveOrder(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID) []uuid.UUID {
	t.Helper()
	rows, err := pool.Query(ctx, `
SELECT id FROM chapters WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order, id`, bookID)
	if err != nil {
		t.Fatalf("read order: %v", err)
	}
	defer rows.Close()
	var out []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			t.Fatalf("scan: %v", err)
		}
		out = append(out, id)
	}
	return out
}

func reorderReq(t *testing.T, s *Server, owner, bookID uuid.UUID, chapter uuid.UUID, after *uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	body := map[string]any{"chapter_id": chapter.String()}
	if after != nil {
		body["after_chapter_id"] = after.String()
	} else {
		body["after_chapter_id"] = nil
	}
	b, _ := json.Marshal(body)
	return bulkHTTP(t, s, owner, http.MethodPost, "/v1/books/"+bookID.String()+"/chapters/reorder", string(b))
}

func TestReorderChapters_MoveIntoAnOccupiedSlot_DoesNotCollideWithTheUniqueIndex_DB(t *testing.T) {
	// The bug this endpoint exists for: the generic PATCH cannot express this at all. Chapter 4 into
	// slot 2 means chapters 2 and 3 must shift right — a permutation, which a per-row unique check
	// rejects unless it is written through the negative-slot parking phase.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 4)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	rr := reorderReq(t, s, owner, bookID, ch[3], &ch[0]) // move #4 to directly after #1
	if rr.Code != http.StatusOK {
		t.Fatalf("reorder = %d, want 200\n%s", rr.Code, rr.Body.String())
	}

	got := liveOrder(t, ctx, pool, bookID)
	want := []uuid.UUID{ch[0], ch[3], ch[1], ch[2]}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("order[%d] = %s, want %s (full: %v)", i, got[i], want[i], got)
		}
	}
	// And the slots are DENSE 1..N — a gappy sequence would break the reading-position math the
	// Plan Hub's x-axis and the canon-rule anchors are built on.
	var slots []int
	rows, _ := pool.Query(ctx, `SELECT sort_order FROM chapters WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order`, bookID)
	defer rows.Close()
	for rows.Next() {
		var s int
		_ = rows.Scan(&s)
		slots = append(slots, s)
	}
	for i, s := range slots {
		if s != i+1 {
			t.Fatalf("slots = %v, want dense 1..N", slots)
		}
	}
}

func TestReorderChapters_ToFront_AndBack_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 3)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	// after_chapter_id = null ⇒ becomes the FIRST chapter.
	if rr := reorderReq(t, s, owner, bookID, ch[2], nil); rr.Code != http.StatusOK {
		t.Fatalf("to-front = %d\n%s", rr.Code, rr.Body.String())
	}
	got := liveOrder(t, ctx, pool, bookID)
	if got[0] != ch[2] {
		t.Fatalf("to-front: first = %s, want %s", got[0], ch[2])
	}

	// ...and back to last (after the current last).
	last := got[len(got)-1]
	if rr := reorderReq(t, s, owner, bookID, ch[2], &last); rr.Code != http.StatusOK {
		t.Fatalf("to-back = %d\n%s", rr.Code, rr.Body.String())
	}
	got = liveOrder(t, ctx, pool, bookID)
	if got[len(got)-1] != ch[2] {
		t.Fatalf("to-back: last = %s, want %s", got[len(got)-1], ch[2])
	}
}

func TestReorderChapters_IsIdempotent_DB(t *testing.T) {
	// Re-issuing the same move must not drift the sequence (the Plan Hub retries on a failed mirror
	// resync, so a non-idempotent reorder would walk the book apart).
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 4)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	for i := 0; i < 3; i++ {
		if rr := reorderReq(t, s, owner, bookID, ch[3], &ch[0]); rr.Code != http.StatusOK {
			t.Fatalf("reorder #%d = %d\n%s", i, rr.Code, rr.Body.String())
		}
	}
	got := liveOrder(t, ctx, pool, bookID)
	want := []uuid.UUID{ch[0], ch[3], ch[1], ch[2]}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("after 3x: order[%d] = %s, want %s", i, got[i], want[i])
		}
	}
}

func TestReorderChapters_RejectsAnAfterIdOutsideTheBook_DB(t *testing.T) {
	// A silent "place it somewhere else" would be worse than a 400 — the user asked for a specific
	// position (`silent-success-is-a-bug`).
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 2)
	otherBook, otherCh := seedActiveChapters(t, ctx, pool, owner, 1)
	_ = otherBook
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}

	before := liveOrder(t, ctx, pool, bookID)
	rr := reorderReq(t, s, owner, bookID, ch[0], &otherCh[0]) // after a chapter of ANOTHER book
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("cross-book after_id = %d, want 400\n%s", rr.Code, rr.Body.String())
	}
	after := liveOrder(t, ctx, pool, bookID)
	for i := range before {
		if before[i] != after[i] {
			t.Fatalf("a rejected reorder must not mutate the sequence")
		}
	}
}

func TestReorderChapters_ViewGranteeIs403_NonGranteeIs404_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, ch := seedActiveChapters(t, ctx, pool, owner, 2)

	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantView, owner, "active", nil
	}
	if rr := reorderReq(t, s, uuid.New(), bookID, ch[0], nil); rr.Code != http.StatusForbidden {
		t.Fatalf("VIEW grantee = %d, want 403", rr.Code)
	}
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantNone, owner, "active", nil
	}
	if rr := reorderReq(t, s, uuid.New(), bookID, ch[0], nil); rr.Code != http.StatusNotFound {
		t.Fatalf("non-grantee = %d, want 404", rr.Code)
	}
	// And nothing moved.
	if got := liveOrder(t, ctx, pool, bookID); got[0] != ch[0] {
		t.Fatalf("a denied reorder must not mutate the sequence")
	}
}
