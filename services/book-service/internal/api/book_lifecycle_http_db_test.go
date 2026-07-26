package api

// M3 (audit) — two gaps the direct-call emit test left: (1) the HTTP ENTRY PATH actually funnels through
// transitionBookLifecycleTx (book + chapters + events in ONE tx); (2) a FAILED tx commits NOTHING
// (atomicity — INV-O12: the emit can't diverge from the lifecycle write).
//
// DB-gated on BOOK_TEST_DATABASE_URL via dbTestServer's throwaway guard.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

func TestTransitionBookLifecycle_HTTPEntryPathAndAtomicity_DB(t *testing.T) {
	srv, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner) // an active book + 1 chapter + a draft
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1
			OR aggregate_id IN (SELECT id FROM chapters WHERE book_id=$1)`, bookID)
	})

	bookEvents := func() int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='book.lifecycle_changed'`,
			bookID).Scan(&n); err != nil {
			t.Fatalf("count events: %v", err)
		}
		return n
	}
	lifecycle := func() string {
		t.Helper()
		var s string
		if err := pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&s); err != nil {
			t.Fatalf("read lifecycle: %v", err)
		}
		return s
	}

	// (1) HTTP entry path: DELETE /v1/books/{id} → trashBook → the shared tx. (dbTestServer's resolveBook
	// stub grants owner on an "active" book, so authBook passes; the real work goes through the tx.)
	req := httptest.NewRequest(http.MethodDelete, "/v1/books/"+bookID.String(), nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", bookID.String())
	req = req.WithContext(addChi(req, rctx))
	w := httptest.NewRecorder()
	srv.trashBook(w, req)

	if w.Code != http.StatusNoContent {
		t.Fatalf("HTTP trash: want 204, got %d body=%s", w.Code, w.Body.String())
	}
	if got := lifecycle(); got != "trashed" {
		t.Fatalf("HTTP path did not trash the book, lifecycle=%q", got)
	}
	if n := bookEvents(); n != 1 {
		t.Fatalf("HTTP path emitted %d book.lifecycle_changed, want 1 (must funnel through the tx)", n)
	}

	// (2) ATOMICITY: restore, then a cancelled-context transition must ERROR and change NOTHING — the
	// lifecycle write + the emit share one tx, so a failed tx rolls back both (never a half-commit).
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "active"); err != nil {
		t.Fatalf("restore: %v", err)
	}
	before := bookEvents()
	cctx, cancel := context.WithCancel(ctx)
	cancel()
	if err := srv.transitionBookLifecycleTx(cctx, bookID, "trashed"); err == nil {
		t.Fatal("a cancelled-context transition must return an error, not silently succeed")
	}
	if got := lifecycle(); got != "active" {
		t.Fatalf("a FAILED tx must leave the book UNCHANGED (atomicity), got %q", got)
	}
	if n := bookEvents(); n != before {
		t.Fatalf("a FAILED tx must emit NO new event (atomicity), events %d→%d", before, n)
	}
}
