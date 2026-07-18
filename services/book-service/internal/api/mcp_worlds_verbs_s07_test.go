package api

// S-07 §2 — world_update / world_delete MCP verbs. DB-gated (real Postgres) like the
// other *_db_test.go; gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func newS07World(t *testing.T, s *Server, ctx context.Context) string {
	t.Helper()
	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "VerbWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	return wout.World.WorldID
}

// TestWorldUpdate_RoundTrip — rename + describe round-trips, owner-scoped, and the
// no-op / empty-name inputs are rejected before any write.
func TestWorldUpdate_RoundTrip(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)
	worldID := newS07World(t, s, ctx)

	// rename + set a description
	name := "Renamed World"
	desc := "a cold northern realm"
	_, uout, err := s.toolWorldUpdate(ctx, nil, worldUpdateIn{WorldID: worldID, Name: &name, Description: &desc})
	if err != nil {
		t.Fatalf("world_update: %v", err)
	}
	if uout.World.Name != "Renamed World" || uout.World.Description == nil || *uout.World.Description != "a cold northern realm" {
		t.Fatalf("update not reflected: %+v", uout.World)
	}
	// persisted — a fresh get sees it
	_, g, err := s.toolWorldGet(ctx, nil, worldGetIn{WorldID: worldID})
	if err != nil || g.World.Name != "Renamed World" {
		t.Fatalf("rename not persisted: %v %+v", err, g.World)
	}

	// description-only update leaves the name intact (pointer rule)
	newDesc := "now a desert"
	_, u2, err := s.toolWorldUpdate(ctx, nil, worldUpdateIn{WorldID: worldID, Description: &newDesc})
	if err != nil || u2.World.Name != "Renamed World" || *u2.World.Description != "now a desert" {
		t.Fatalf("description-only update wrong: %v %+v", err, u2.World)
	}

	// nothing-to-update is rejected (no silent version bump)
	if _, _, err := s.toolWorldUpdate(ctx, nil, worldUpdateIn{WorldID: worldID}); err == nil {
		t.Fatal("update with neither field must error")
	}
	// empty name is rejected
	empty := "   "
	if _, _, err := s.toolWorldUpdate(ctx, nil, worldUpdateIn{WorldID: worldID, Name: &empty}); err == nil {
		t.Fatal("blank name must error")
	}

	// owner-scoped: user B cannot update owner A's world (uniform not-found)
	ctxB := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldUpdate(ctxB, nil, worldUpdateIn{WorldID: worldID, Name: &name}); err == nil ||
		!strings.Contains(err.Error(), "not found") {
		t.Fatalf("user B must get 'world not found', got: %v", err)
	}
}

// TestWorldDelete_GuardAndScope — a bible-only world deletes; a world holding a member
// book is REFUSED (would orphan it); cross-user is a uniform not-found.
func TestWorldDelete_GuardAndScope(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	// (a) a fresh world (only its hidden bible) deletes cleanly.
	emptyWorld := newS07World(t, s, ctx)
	// Capture the bible book id so we can assert its fate after the world is deleted.
	var bibleBookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT id FROM books WHERE world_id=$1 AND is_bible=true`, uuid.MustParse(emptyWorld),
	).Scan(&bibleBookID); err != nil {
		t.Fatalf("resolve bible book: %v", err)
	}
	_, dout, err := s.toolWorldDelete(ctx, nil, worldDeleteIn{WorldID: emptyWorld})
	if err != nil || !dout.Deleted {
		t.Fatalf("bible-only world must delete: %v deleted=%v", err, dout.Deleted)
	}
	// it's gone — a get 404s
	if _, _, err := s.toolWorldGet(ctx, nil, worldGetIn{WorldID: emptyWorld}); err == nil {
		t.Fatal("world must be gone after delete")
	}
	// S-07 audit — the bible must be routed through purge_pending (the sweeper collects it),
	// NOT left as an orphaned ACTIVE hidden book that leaks forever.
	var bibleState string
	if err := pool.QueryRow(ctx,
		`SELECT lifecycle_state FROM books WHERE id=$1`, bibleBookID).Scan(&bibleState); err != nil {
		t.Fatalf("read bible state: %v", err)
	}
	if bibleState != "purge_pending" {
		t.Fatalf("deleting a world must purge_pending its bible, got lifecycle_state=%q", bibleState)
	}
	// and the bible's chapters too (the sort_order-0 world-bible chapter).
	var activeBibleChapters int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM chapters WHERE book_id=$1 AND lifecycle_state!='purge_pending'`, bibleBookID,
	).Scan(&activeBibleChapters); err != nil {
		t.Fatalf("read bible chapters: %v", err)
	}
	if activeBibleChapters != 0 {
		t.Fatalf("the bible's chapters must also be purge_pending, %d still active", activeBibleChapters)
	}

	// (b) a world holding a member book is REFUSED (no silent orphaning).
	populated := newS07World(t, s, ctx)
	pworldID := uuid.MustParse(populated)
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title,world_id) VALUES($1,'member',$2) RETURNING id`,
		owner, pworldID).Scan(&bookID); err != nil {
		t.Fatalf("seed member book: %v", err)
	}
	_, _, err = s.toolWorldDelete(ctx, nil, worldDeleteIn{WorldID: populated})
	if err == nil || !strings.Contains(err.Error(), "member book") {
		t.Fatalf("delete of a populated world must be refused, got: %v", err)
	}
	// the world (and its book) survive the refusal
	if _, _, gerr := s.toolWorldGet(ctx, nil, worldGetIn{WorldID: populated}); gerr != nil {
		t.Fatalf("a refused delete must leave the world intact: %v", gerr)
	}

	// after the book leaves the world, the delete goes through.
	if _, err := pool.Exec(ctx, `UPDATE books SET world_id=NULL WHERE id=$1`, bookID); err != nil {
		t.Fatalf("un-home book: %v", err)
	}
	if _, dout2, err := s.toolWorldDelete(ctx, nil, worldDeleteIn{WorldID: populated}); err != nil || !dout2.Deleted {
		t.Fatalf("after moving the book out, delete must succeed: %v", err)
	}

	// (c) cross-user delete is a uniform not-found (no existence oracle).
	other := newS07World(t, s, ctx)
	ctxB := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldDelete(ctxB, nil, worldDeleteIn{WorldID: other}); err == nil ||
		!strings.Contains(err.Error(), "not found") {
		t.Fatalf("user B must get 'world not found', got: %v", err)
	}
}
