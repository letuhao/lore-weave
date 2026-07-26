// K13 round 3 (2026-07-23) — `book_chapter_bulk_create` must not mint duplicates when the
// caller supplies no `original_filename`.
//
// LIVE-PROBED through ai-gateway: two byte-identical calls produced TWO chapters, despite
// the tool's own description promising "Idempotent on original_filename". The promise held
// only for callers that SUPPLY the filename. Without one the key is auto-generated from
// `sortOrder`, seeded from MAX(sort_order)+1 — so call 1 minted `chapter-0002.txt`, call 2
// minted `chapter-0003.txt`, and the dedup set could never match. The key was DERIVED FROM
// THE STATE THE PREVIOUS CALL HAD JUST CHANGED, which makes the idempotency vacuous by
// construction rather than merely buggy.
//
// It was vacuous precisely where it matters: a folder import carries real filenames, but an
// AGENT creating chapters from chat carries none — so the agent path, the one the Tier-A
// repeat-fire was actually measured on, was the unprotected one.
//
// Gated on BOOK_TEST_DATABASE_URL, like its N6 and K13 siblings.
package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// The test server's cfg carries QuotaBytesDefault=0, so ensureQuotaRow seeds a ZERO quota
// and every bulk write trips "storage quota exceeded" BEFORE reaching the guard under test —
// which would make these assertions pass or fail for a reason that has nothing to do with
// idempotency. Give the owner real headroom.
//
// The quota is keyed on the owner `mcpRequireGrant` resolves. The shared stub's resolveBook
// returns `uuid.New()` on EVERY call — a fresh owner each time — so no pre-seeded quota row
// could ever match it, and the handler failed on the quota gate before reaching the guard
// under test. Pin the resolver to ONE owner (which is also what a real book does), then seed
// that owner's quota.
func bulkTestServer(t *testing.T) (*Server, *pgxpool.Pool, uuid.UUID, context.Context) {
	t.Helper()
	s, pool := dbTestServer(t)
	owner := uuid.New()
	s.resolveBook = func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	if _, err := pool.Exec(context.Background(), `
INSERT INTO user_storage_quota(owner_user_id, used_bytes, quota_bytes) VALUES($1, 0, $2)
ON CONFLICT(owner_user_id) DO UPDATE SET quota_bytes = EXCLUDED.quota_bytes`,
		owner, int64(1<<30)); err != nil {
		t.Fatalf("seed quota: %v", err)
	}
	return s, pool, owner, identityCtxForTest(t, owner)
}

func TestMCPChapterBulkCreate_IdempotentWithoutFilenames_DB(t *testing.T) {
	s, _, _, ctx := bulkTestServer(t)

	_, book, err := s.toolBookCreate(ctx, nil, bookCreateIn{
		Title: "K13r3 Bulk Book", OriginalLanguage: "en",
	})
	if err != nil {
		t.Fatalf("book_create: %v", err)
	}

	call := func(items ...chapterBulkItem) chapterBulkCreateOut {
		_, out, err := s.toolChapterBulkCreate(ctx, nil, chapterBulkCreateIn{
			BookID: book.BookID, OriginalLanguage: "en", Chapters: items,
		})
		if err != nil {
			t.Fatalf("bulk_create: %v", err)
		}
		return out
	}

	item := chapterBulkItem{Title: "K13r3 The Tide Turns", Content: "the tide turns"}

	first := call(item)
	if first.Created != 1 {
		t.Fatalf("setup: expected 1 created, got %+v", first)
	}

	// THE BUG: byte-identical repeat, no original_filename.
	again := call(item)
	if again.Created != 0 || again.Skipped != 1 {
		t.Fatalf("bulk_create duplicated on an identical repeat: %+v — an agent double-fire "+
			"turns one user intent into N chapters", again)
	}

	// Case-insensitive, mirroring the singular N6 guard.
	if mixed := call(chapterBulkItem{Title: "k13r3 THE TIDE TURNS", Content: "x"}); mixed.Created != 0 {
		t.Fatalf("the guard must match case-insensitively: %+v", mixed)
	}

	// The guard must not swallow real work.
	if other := call(chapterBulkItem{Title: "K13r3 A Different Chapter", Content: "y"}); other.Created != 1 {
		t.Fatalf("a distinct title must still create: %+v", other)
	}
}

func TestMCPChapterBulkCreate_DedupsWithinOneBatch_DB(t *testing.T) {
	// The repeat need not be a second CALL. A model that emits the same chapter twice in
	// one `chapters` array is the same defect arriving in a single request, and the
	// same-pass tool-call collapse upstream cannot help here (it is one call).
	s, _, _, ctx := bulkTestServer(t)

	_, book, err := s.toolBookCreate(ctx, nil, bookCreateIn{
		Title: "K13r3 Batch Book", OriginalLanguage: "en",
	})
	if err != nil {
		t.Fatalf("book_create: %v", err)
	}
	item := chapterBulkItem{Title: "K13r3 Twice", Content: "z"}
	_, out, err := s.toolChapterBulkCreate(ctx, nil, chapterBulkCreateIn{
		BookID: book.BookID, OriginalLanguage: "en",
		Chapters: []chapterBulkItem{item, item},
	})
	if err != nil {
		t.Fatalf("bulk_create: %v", err)
	}
	if out.Created != 1 || out.Skipped != 1 {
		t.Fatalf("a duplicate inside ONE batch must collapse: %+v", out)
	}
}

func TestMCPChapterBulkCreate_ExplicitFilenamesStillAllowSameTitle_DB(t *testing.T) {
	// The escape hatch, and the reason the guard is scoped to the no-filename case: a real
	// import legitimately carries many same-titled chapters ("Chapter 1" per volume) in
	// distinct files. Supplying `original_filename` must keep the ORIGINAL behaviour, where
	// the filename is the authoritative key — otherwise this fix would break folder import,
	// which is the feature the tool was built for.
	s, _, _, ctx := bulkTestServer(t)

	_, book, err := s.toolBookCreate(ctx, nil, bookCreateIn{
		Title: "K13r3 Import Book", OriginalLanguage: "en",
	})
	if err != nil {
		t.Fatalf("book_create: %v", err)
	}
	_, out, err := s.toolChapterBulkCreate(ctx, nil, chapterBulkCreateIn{
		BookID: book.BookID, OriginalLanguage: "en",
		Chapters: []chapterBulkItem{
			{Title: "Chapter 1", Content: "vol1", OriginalFilename: "v1/ch01.txt"},
			{Title: "Chapter 1", Content: "vol2", OriginalFilename: "v2/ch01.txt"},
		},
	})
	if err != nil {
		t.Fatalf("bulk_create: %v", err)
	}
	if out.Created != 2 {
		t.Fatalf("distinct filenames must both create even with an identical title: %+v", out)
	}

	// …and re-importing the SAME filenames is still the documented no-op.
	_, again, err := s.toolChapterBulkCreate(ctx, nil, chapterBulkCreateIn{
		BookID: book.BookID, OriginalLanguage: "en",
		Chapters: []chapterBulkItem{
			{Title: "Chapter 1", Content: "vol1", OriginalFilename: "v1/ch01.txt"},
			{Title: "Chapter 1", Content: "vol2", OriginalFilename: "v2/ch01.txt"},
		},
	})
	if err != nil {
		t.Fatalf("bulk_create replay: %v", err)
	}
	if again.Created != 0 || again.Skipped != 2 {
		t.Fatalf("a filename replay must skip both: %+v", again)
	}
}
