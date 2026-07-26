// K13 (2026-07-23) — `book_create` and `world_create` must be idempotent on a non-empty
// natural key, for the same reason N6 made `book_chapter_create` idempotent.
//
// This was LIVE-PROBED, not theorised: two byte-identical calls through ai-gateway
// produced two books and two worlds. The agent loop was separately measured re-issuing an
// identical Tier-A write across iterations even after an explicit success result, and
// Tier-A auto-commits are bounded only by TIER_A_SAME_OP_CAP (5 per turn) — so one user
// intent could mint five duplicates with no confirm card in between. `book_create` has NO
// agent-invocable undo, so a duplicate is only cleanable by the human in the GUI.
//
// Gated on BOOK_TEST_DATABASE_URL, like its N6 sibling.
package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestMCPBookCreate_Idempotent_DB(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	mk := func(title string) string {
		_, out, err := s.toolBookCreate(ctx, nil, bookCreateIn{
			Title: title, OriginalLanguage: "en",
		})
		if err != nil {
			t.Fatalf("book_create %q: %v", title, err)
		}
		return out.BookID
	}

	first := mk("K13 The Salt Cartographer")
	again := mk("K13 The Salt Cartographer")
	if first != again {
		t.Fatalf("book_create is NOT idempotent: %s vs %s — an agent double-fire mints a "+
			"duplicate book, and book_create has no agent-invocable undo", first, again)
	}

	// Case-insensitive, mirroring the N6 chapter guard.
	if mixed := mk("k13 the SALT cartographer"); mixed != first {
		t.Fatalf("book_create must match case-insensitively: %s vs %s", mixed, first)
	}

	// A genuinely different title must still create — the guard must not swallow real work.
	if other := mk("K13 A Different Book"); other == first {
		t.Fatal("a distinct title must create a NEW book")
	}
}

func TestMCPWorldCreate_Idempotent_DB(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	mk := func(name string) string {
		_, out, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: name})
		if err != nil {
			t.Fatalf("world_create %q: %v", name, err)
		}
		return out.World.WorldID
	}

	first := mk("K13 Tidewatch")
	if again := mk("K13 Tidewatch"); again != first {
		t.Fatalf("world_create is NOT idempotent: %s vs %s", first, again)
	}
	if mixed := mk("k13 TIDEWATCH"); mixed != first {
		t.Fatalf("world_create must match case-insensitively: %s vs %s", mixed, first)
	}
	if other := mk("K13 Emberfall"); other == first {
		t.Fatal("a distinct name must create a NEW world")
	}
}

// The guard must key off a LIVE row only. A trashed book's title is free to reuse — the
// predicate is `lifecycle_state='active'`, and getting that wrong would resurrect a
// deleted book as the "existing" one. (Written after the first draft of this guard used a
// `deleted_at` column that books does not have: the query errored, the error was read as
// "no match", and the guard silently did nothing — the exact silent-no-op class.)
func TestMCPBookCreate_IdempotencyIgnoresTrashedTitles_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, out, err := s.toolBookCreate(ctx, nil, bookCreateIn{
		Title: "K13 Trashed Title", OriginalLanguage: "en",
	})
	if err != nil {
		t.Fatalf("book_create: %v", err)
	}
	if _, err := pool.Exec(context.Background(),
		`UPDATE books SET lifecycle_state='purge_pending' WHERE id=$1 AND owner_user_id=$2`,
		uuid.MustParse(out.BookID), owner); err != nil {
		t.Fatalf("trash the book: %v", err)
	}
	_, out2, err := s.toolBookCreate(ctx, nil, bookCreateIn{
		Title: "K13 Trashed Title", OriginalLanguage: "en",
	})
	if err != nil {
		t.Fatalf("book_create after trash: %v", err)
	}
	if strings.EqualFold(out2.BookID, out.BookID) {
		t.Fatal("the guard matched a NON-active book — a trashed title must be reusable")
	}
}
