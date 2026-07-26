package api

// WS-1.4 (step 1) — one active diary book per user (spec 02 §Q2.1).
//
// Provisioning the assistant is a retryable, concurrent fan-out: two devices open /assistant
// at the same moment, or a BFF call is retried. Its get-or-create matches on
// (owner_user_id, kind='diary', active). If two of those race, the user must end up with ONE
// diary book, not two — two diaries silently split their assistant memory in half (the same
// split-brain the knowledge-side one-per-user is_assistant unique prevents). The partial
// unique index is what makes "one diary" a database fact instead of a hope.
//
// DB-gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestDiaryBook_OnlyOneActivePerUser_DB(t *testing.T) {
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()

	var first uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'diary','diary') RETURNING id`,
		owner).Scan(&first); err != nil {
		t.Fatalf("seed first diary: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	// A SECOND active diary for the same user must be refused by the DB.
	_, err := pool.Exec(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'diary2','diary')`, owner)
	if err == nil {
		t.Fatal("a second active diary book was created for the same user. Two diaries split " +
			"the assistant's memory in half — provisioning must converge on ONE, enforced in the DB.")
	}
	if !strings.Contains(strings.ToLower(err.Error()), "uq_books_one_active_diary_per_user") &&
		!strings.Contains(strings.ToLower(err.Error()), "unique") {
		t.Fatalf("expected the one-diary-per-user unique to fire, got: %v", err)
	}
}

func TestDiaryBook_TrashedDoesNotBlockAFreshOne_DB(t *testing.T) {
	// E14: the user trashes their diary and re-provisions. The partial index is active-only,
	// so a trashed diary must NOT block making a fresh one — otherwise a deleted diary would
	// lock the user out of the assistant forever (the partial-unique-must-exempt-tombstones
	// lesson).
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	var first uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'d1','diary') RETURNING id`,
		owner).Scan(&first); err != nil {
		t.Fatalf("seed first diary: %v", err)
	}
	// Trash it (this is how book-service trashes a book; setting lifecycle_state does not
	// change kind, so the immutability trigger allows it).
	if _, err := pool.Exec(ctx,
		`UPDATE books SET lifecycle_state='trashed' WHERE id=$1`, first); err != nil {
		t.Fatalf("trash first diary: %v", err)
	}

	// A fresh diary must now succeed.
	if _, err := pool.Exec(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'d2','diary')`, owner); err != nil {
		t.Fatalf("a trashed diary blocked creating a fresh one — the partial unique is not "+
			"exempting tombstones: %v", err)
	}

	var active int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM books WHERE owner_user_id=$1 AND kind='diary' AND lifecycle_state='active'`,
		owner).Scan(&active); err != nil {
		t.Fatalf("count active: %v", err)
	}
	if active != 1 {
		t.Fatalf("active diaries = %d, want exactly 1 (the fresh one)", active)
	}
}

func TestDiaryBook_DifferentUsersEachGetOne_DB(t *testing.T) {
	// The constraint is PER USER. Two different users each keeping a diary must not collide.
	_, pool := dbTestServer(t)
	ctx := context.Background()
	a, b := uuid.New(), uuid.New()
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=ANY($1)`, []uuid.UUID{a, b})
	})

	if _, err := pool.Exec(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'da','diary')`, a); err != nil {
		t.Fatalf("user A diary: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO books(owner_user_id,title,kind) VALUES($1,'db','diary')`, b); err != nil {
		t.Fatalf("user B diary was refused — the unique is colliding ACROSS users (it must be "+
			"scoped to owner_user_id): %v", err)
	}
}

func TestDiaryBook_DoesNotConstrainNonDiaryBooks_DB(t *testing.T) {
	// The predicate only bites kind='diary'. A user may keep one diary AND many novels; the
	// index must not accidentally cap a user's novels at one.
	_, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE owner_user_id=$1`, owner) })

	for _, k := range []string{"diary", "novel", "novel", "document"} {
		if _, err := pool.Exec(ctx,
			`INSERT INTO books(owner_user_id,title,kind) VALUES($1,$2,$2)`, owner, k); err != nil {
			t.Fatalf("insert kind=%q was refused — the diary unique is over-reaching to "+
				"non-diary books: %v", k, err)
		}
	}
}
