package api

// TOOL DEEP-DIVE `book_chapter_save_draft` — two defects the tool's own success hid.
//
// The tool was PROVEN live on 2026-08-13: driven from plain prose, it wrote four paragraphs into a
// chapter and returned ok with word_count=269. Reading the OWNING STORE rather than the response
// turned up two things the success said nothing about.
//
//  1. BILLING. `recalcQuota` bills an account by SUM(chapters.byte_size), and this tool never
//     touched byte_size or re-billed. Its sibling `book_chapter_create` in the same file already
//     does both. Measured: 139 of the 299 chapters holding prose carry byte_size=0.
//
//  2. ORDERING. save_draft writes TWO revisions in ONE transaction — the "before assistant save"
//     snapshot and the new body — and now() is the TRANSACTION timestamp, so both carry the SAME
//     created_at. `book_list_revisions` ordered by created_at DESC alone and returned the
//     PRE-SAVE snapshot first, ahead of the body that replaced it. Measured through the product
//     surface: index 0 was 'before assistant save' at 64B, index 1 the real 3388B body. The tool's
//     own description says "newest first" and "use before restoring", so the row a reader would
//     restore as "the latest" is the one that UNDOES the save.
//
// DB-gated on BOOK_TEST_DATABASE_URL like the other *_db_test.go files: both defects are about what
// Postgres actually holds and what a real ORDER BY returns, and a mock can prove neither.

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

const draftProse = "The pre-dawn light was a bruised purple.\n\nThe ink was still wet."

func TestMCP_SaveDraft_BillsTheBytesItWrites_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: draftProse,
	}); err != nil {
		t.Fatalf("save_draft: %v", err)
	}

	var size int64
	if err := pool.QueryRow(ctx, `SELECT byte_size FROM chapters WHERE id=$1`, chID).Scan(&size); err != nil {
		t.Fatalf("read byte_size: %v", err)
	}
	if size != int64(len(draftProse)) {
		t.Fatalf("byte_size = %d, want %d — the tool that REPLACES a chapter's prose is not "+
			"accounting for the bytes it wrote, so the account is never billed for it",
			size, len(draftProse))
	}
}

func TestMCP_SaveDraft_RebillsTheOwnersQuota_DB(t *testing.T) {
	// Writing byte_size is only half of it: `used_bytes` is a STORED aggregate that only moves when
	// something calls recalcQuota. book_chapter_create calls it; this tool did not, so even a
	// correct byte_size would have left the account's usage reading stale until some other write
	// happened to refresh it.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: draftProse,
	}); err != nil {
		t.Fatalf("save_draft: %v", err)
	}

	var used int64
	if err := pool.QueryRow(ctx,
		`SELECT used_bytes FROM user_storage_quota WHERE owner_user_id=$1`, owner).Scan(&used); err != nil {
		t.Fatalf("read quota (the row must exist — the tool ensures it, as create does): %v", err)
	}
	if used < int64(len(draftProse)) {
		t.Fatalf("used_bytes = %d, want >= %d — the stored quota aggregate was never refreshed, "+
			"so the author's usage reads stale until an unrelated write happens to fix it",
			used, len(draftProse))
	}
}

func TestMCP_SaveDraft_ShrinkingAChapterLowersItsBilledSize_DB(t *testing.T) {
	// THE CONTROL. byte_size must track the CURRENT body, not a high-water mark: billing that only
	// ever grows is the same defect pointed the other way, and it is what a naive "add the new
	// bytes" fix would produce.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	long := draftProse + "\n\n" + draftProse + "\n\n" + draftProse
	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: long,
	}); err != nil {
		t.Fatalf("save long: %v", err)
	}
	short := "One line."
	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: short,
	}); err != nil {
		t.Fatalf("save short: %v", err)
	}

	var size int64
	if err := pool.QueryRow(ctx, `SELECT byte_size FROM chapters WHERE id=$1`, chID).Scan(&size); err != nil {
		t.Fatalf("read byte_size: %v", err)
	}
	if size != int64(len(short)) {
		t.Fatalf("byte_size = %d after shrinking to %d bytes — billing is a high-water mark, "+
			"so deleting prose never gives the quota back", size, len(short))
	}
}

func TestMCP_SaveDraft_NewestRevisionIsTheOneItJustWrote_DB(t *testing.T) {
	// 🔴 THE DEFECT. Both revisions this tool writes share the transaction's now(), so an ORDER BY
	// created_at DESC alone is a coin toss that landed, in production, on the WRONG row.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	if _, _, err := s.toolChapterSaveDraft(tctx, nil, saveDraftIn{
		BookID: bookID.String(), ChapterID: chID.String(), Body: draftProse,
	}); err != nil {
		t.Fatalf("save_draft: %v", err)
	}

	_, out, err := s.toolBookListRevisions(tctx, nil, listRevisionsIn{
		BookID: bookID.String(), ChapterID: chID.String(),
	})
	if err != nil {
		t.Fatalf("list revisions: %v", err)
	}
	if len(out.Revisions) < 2 {
		t.Fatalf("got %d revisions, want at least the snapshot + the new body", len(out.Revisions))
	}
	// The tool documents "newest first". The newest is the body just written — never the snapshot
	// taken of what it replaced.
	if out.Revisions[0].Message != nil && *out.Revisions[0].Message == "before assistant save" {
		t.Fatalf("revision[0] is the PRE-SAVE snapshot — 'newest first' is offering the row whose "+
			"restore would undo the save the author just made (sizes: %d then %d)",
			out.Revisions[0].BodyByteLength, out.Revisions[1].BodyByteLength)
	}
	if out.Revisions[0].BodyByteLength <= out.Revisions[1].BodyByteLength {
		t.Fatalf("revision[0] is %dB and revision[1] is %dB — the newly written body is not first",
			out.Revisions[0].BodyByteLength, out.Revisions[1].BodyByteLength)
	}
}
