package api

// P3.1 (book-structure-pipeline spec §4.6) — a book lifecycle transition (trash / restore / purge)
// must emit exactly one book.lifecycle_changed outbox event, aggregate_type='book', atomic with the
// lifecycle write. Before P3.1 the transition wrote with bare swallowed Exec and emitted nothing, so
// composition's book_lifecycle mirror never learned the book was trashed → live structure over a dead
// book (the read-side half is the resolver gate; this is the write-side signal).
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
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1`, bookID)
		_, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID)
	})

	// countBookEvents returns how many book.lifecycle_changed rows exist for this book, plus the
	// payload's book_id from the latest one (the re-read consumer needs book_id present).
	countBookEvents := func() (int, string) {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND aggregate_type='book' AND event_type='book.lifecycle_changed'`,
			bookID).Scan(&n); err != nil {
			t.Fatalf("count events: %v", err)
		}
		var payloadBook string
		_ = pool.QueryRow(ctx,
			`SELECT payload->>'book_id' FROM outbox_events WHERE aggregate_id=$1 AND aggregate_type='book' ORDER BY created_at DESC LIMIT 1`,
			bookID).Scan(&payloadBook)
		return n, payloadBook
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

	// trash → 1 event, book trashed, payload carries book_id.
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "trashed"); err != nil {
		t.Fatalf("trash: %v", err)
	}
	assertLifecycle("trashed")
	if n, pb := countBookEvents(); n != 1 {
		t.Fatalf("after trash: %d book.lifecycle_changed events, want 1", n)
	} else if pb != bookID.String() {
		t.Fatalf("event payload book_id = %q, want %q", pb, bookID)
	}

	// restore → a 2nd event (the consumer re-reads → active).
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "active"); err != nil {
		t.Fatalf("restore: %v", err)
	}
	assertLifecycle("active")
	if n, _ := countBookEvents(); n != 2 {
		t.Fatalf("after restore: %d events, want 2", n)
	}

	// trash again then purge → 3rd + 4th events; book ends purge_pending.
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "trashed"); err != nil {
		t.Fatalf("re-trash: %v", err)
	}
	if err := srv.transitionBookLifecycleTx(ctx, bookID, "purge_pending"); err != nil {
		t.Fatalf("purge: %v", err)
	}
	assertLifecycle("purge_pending")
	if n, _ := countBookEvents(); n != 4 {
		t.Fatalf("after purge: %d events, want 4", n)
	}
}
