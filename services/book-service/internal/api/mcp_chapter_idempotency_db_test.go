// N6 (dogfood 2026-07-18 F7) — book_chapter_create must be idempotent on a non-empty title
// within a book+language, so the agent double-firing the tool in one turn can't leave a
// duplicate chapter. Empty-title placeholders stay distinct. Gated on BOOK_TEST_DATABASE_URL.
package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestMCPChapterCreate_Idempotent_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx0, pool, owner)
	s.resolveBook = ownerResolver(owner)
	ctx := identityCtxForTest(t, owner)

	mk := func(title string) string {
		_, out, err := s.toolChapterCreate(ctx, nil, chapterCreateIn{
			BookID: bookID.String(), Title: title, OriginalLanguage: "en",
		})
		if err != nil {
			t.Fatalf("create %q: %v", title, err)
		}
		return out.ChapterID
	}

	// The double-fire: two identical create calls → ONE chapter, same id.
	a := mk("Emberfall")
	b := mk("Emberfall")
	if a != b {
		t.Fatalf("double-create should be idempotent: got two ids %s and %s", a, b)
	}
	// Case-insensitive match too (lower(title)).
	c := mk("emberfall")
	if c != a {
		t.Fatalf("case-insensitive title should dedup: %s vs %s", c, a)
	}
	// DB holds exactly ONE active chapter with that title.
	var n int
	_ = pool.QueryRow(ctx0,
		`SELECT count(*) FROM chapters WHERE book_id=$1 AND lower(title)='emberfall' AND lifecycle_state='active'`,
		bookID).Scan(&n)
	if n != 1 {
		t.Fatalf("want exactly 1 active 'Emberfall' chapter, got %d", n)
	}

	// A DIFFERENT title makes a distinct chapter.
	d := mk("The Second Fire")
	if d == a {
		t.Fatalf("different title must be a new chapter")
	}

	// Empty-title placeholders ("Chapter N") stay distinct — two empties = two chapters.
	e1 := mk("")
	e2 := mk("")
	if e1 == e2 {
		t.Fatalf("empty-title placeholders must NOT dedup: both %s", e1)
	}
}
