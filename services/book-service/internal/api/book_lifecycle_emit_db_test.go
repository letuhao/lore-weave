package api

// P3.1 + H1 (book-structure-pipeline spec §4.6) — a book lifecycle transition (trash / restore / purge)
// must, in ONE tx: (a) emit exactly one book.lifecycle_changed (aggregate_type='book'), and (b) emit ONE
// per-chapter event for every chapter it moved — chapter.trashed on trash, chapter.restored on restore,
// chapter.deleted on purge — so the consumers of those events (glossary staleness, statistics, written-
// verdict) react to a BULK book transition exactly as to N single-chapter ones. Before H1 the bulk path
// emitted no per-chapter events, so a trashed book's chapters still read as live to those consumers.
//
// DB-gated on BOOK_TEST_DATABASE_URL via dbTestServer's throwaway guard.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestTransitionBookLifecycle_EmitsBookLifecycleChanged_DB(t *testing.T) {
	srv, pool := dbTestServer(t)
	ctx := context.Background()

	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'p3-emit','novel') RETURNING id`,
		uuid.New()).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	// Two active chapters — the per-chapter emit is what H1 added; a book with 0 chapters would prove
	// only the book event.
	for i := 0; i < 2; i++ {
		fn := uuid.NewString()
		if _, err := pool.Exec(ctx,
			`INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state)
			 VALUES($1,$2,$3,'en','text/plain',$4,$5,'active')`,
			bookID, "ch", fn+".txt", i+1, "k/"+fn); err != nil {
			t.Fatalf("seed chapter %d: %v", i, err)
		}
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1
			OR aggregate_id IN (SELECT id FROM chapters WHERE book_id=$1)`, bookID)
		_, _ = pool.Exec(ctx, `DELETE FROM chapters WHERE book_id=$1`, bookID)
		_, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID)
	})

	countBookEvents := func() int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND aggregate_type='book' AND event_type='book.lifecycle_changed'`,
			bookID).Scan(&n); err != nil {
			t.Fatalf("count book events: %v", err)
		}
		var payloadBook string
		_ = pool.QueryRow(ctx,
			`SELECT payload->>'book_id' FROM outbox_events WHERE aggregate_id=$1 AND aggregate_type='book' ORDER BY created_at DESC LIMIT 1`,
			bookID).Scan(&payloadBook)
		if payloadBook != bookID.String() {
			t.Fatalf("book event payload book_id = %q, want %q", payloadBook, bookID)
		}
		return n
	}

	// countChapterEvents: rows of `eventType` (aggregate_type='chapter') over THIS book's chapters, with
	// the payload's book_id verified (the consumers key on it).
	countChapterEvents := func(eventType string) int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events
			 WHERE aggregate_type='chapter' AND event_type=$2 AND payload->>'book_id'=$1
			   AND aggregate_id IN (SELECT id FROM chapters WHERE book_id=$1::uuid)`,
			bookID.String(), eventType).Scan(&n); err != nil {
			t.Fatalf("count chapter events %s: %v", eventType, err)
		}
		return n
	}

	assertLifecycle := func(want string) {
		t.Helper()
		var got string
		if err := pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&got); err != nil {
			t.Fatalf("read lifecycle: %v", err)
		}
		if got != want {
			t.Fatalf("book lifecycle = %q, want %q", got, want)
		}
	}

	// trash → 1 book event + 2 chapter.trashed.
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "trashed"); err != nil {
		t.Fatalf("trash: %v", err)
	}
	assertLifecycle("trashed")
	if n := countBookEvents(); n != 1 {
		t.Fatalf("after trash: %d book events, want 1", n)
	}
	if n := countChapterEvents("chapter.trashed"); n != 2 {
		t.Fatalf("after trash: %d chapter.trashed, want 2 (the bulk path must emit per-chapter, H1)", n)
	}

	// restore → 2nd book event + 2 chapter.restored (the symmetric event the pre-H1 code never had).
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "active"); err != nil {
		t.Fatalf("restore: %v", err)
	}
	assertLifecycle("active")
	if n := countBookEvents(); n != 2 {
		t.Fatalf("after restore: %d book events, want 2", n)
	}
	if n := countChapterEvents("chapter.restored"); n != 2 {
		t.Fatalf("after restore: %d chapter.restored, want 2 (restore must be symmetric — statistics/"+
			"glossary/written-verdict re-read/re-ground/reconcile on it)", n)
	}

	// re-trash → 2 more chapter.trashed (total 4) → then purge → 2 chapter.deleted.
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "trashed"); err != nil {
		t.Fatalf("re-trash: %v", err)
	}
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "purge_pending"); err != nil {
		t.Fatalf("purge: %v", err)
	}
	assertLifecycle("purge_pending")
	if n := countBookEvents(); n != 4 {
		t.Fatalf("after purge: %d book events, want 4", n)
	}
	if n := countChapterEvents("chapter.trashed"); n != 4 {
		t.Fatalf("after re-trash: %d chapter.trashed total, want 4", n)
	}
	if n := countChapterEvents("chapter.deleted"); n != 2 {
		t.Fatalf("after purge: %d chapter.deleted, want 2", n)
	}
}
