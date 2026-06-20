package api

// Pipeline M2 — direct (class-W) write tool guards. glossary_create_chapter_link is
// Edit-gated, entity-in-book guarded, and validates relevance + chapter_id before any
// write. (The happy-path insert shares createChapterLinkCore with the HTTP handler.)
// Requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPipelineWriteTool_ChapterLinkGuards(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	octx := ctxWithUser(f.ownerID)

	charKind := bookKindID(t, pool, f.bookID, "character")
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description) VALUES($1,$2,'cl entity') RETURNING entity_id`,
		f.bookID, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE entity_id=$1`, entityID) }) //nolint:errcheck

	book := f.bookID.String()

	// grant gate — a non-grantee is denied
	if _, _, err := f.srv.toolCreateChapterLink(ctxWithUser(uuid.New()), nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: uuid.NewString()}); err == nil {
		t.Error("non-grantee must be denied")
	}
	// entity-in-book guard
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: uuid.NewString(), ChapterID: uuid.NewString()}); err == nil {
		t.Error("entity not in book must error")
	}
	// invalid chapter_id uuid (rejected before the core)
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: "not-a-uuid"}); err == nil {
		t.Error("invalid chapter_id must error")
	}
	// bad relevance (rejected by the core before any upstream/insert)
	if _, _, err := f.srv.toolCreateChapterLink(octx, nil,
		createChapterLinkToolIn{BookID: book, EntityID: entityID.String(), ChapterID: uuid.NewString(), Relevance: "bogus"}); err == nil {
		t.Error("bad relevance must error")
	}
}
