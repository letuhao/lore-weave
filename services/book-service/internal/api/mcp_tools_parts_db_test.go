package api

// S-02 — MCP parts-tool round-trip DB tests. They drive the tool handlers directly
// with a kit-populated identity ctx (identityCtxForTest) against a real Postgres,
// proving agent parity: each tool writes, the write lands, the undo_hint names the
// verified reverse op, and tenancy holds. Gated on BOOK_TEST_DATABASE_URL.

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
)

// undoHintFromResult pulls _meta.undo_hint = {tool, args} off a tool result.
func undoHintFromResult(t *testing.T, meta map[string]any) (string, map[string]any) {
	t.Helper()
	h, ok := meta["undo_hint"].(map[string]any)
	if !ok {
		t.Fatalf("result carries no undo_hint: %v", meta)
	}
	tool, _ := h["tool"].(string)
	args, _ := h["args"].(map[string]any)
	return tool, args
}

// create → rename → archive → restore, verifying DB effect + undo hints at each step.
func TestMCPParts_CreateRenameArchiveRestore_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx0, pool, owner)
	s.resolveBook = ownerResolver(owner)
	ctx := identityCtxForTest(t, owner)

	// create
	res, out, err := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookID.String(), Title: "Act One"})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if out.SortOrder != 1 || out.PartID == "" {
		t.Fatalf("create out wrong: %+v", out)
	}
	if tool, args := undoHintFromResult(t, res.Meta); tool != "book_part_archive" || args["part_id"] != out.PartID {
		t.Fatalf("create undo hint wrong: %s %v", tool, args)
	}
	partID := out.PartID
	// DB: title landed
	var title *string
	_ = pool.QueryRow(ctx0, `SELECT title FROM parts WHERE id=$1`, partID).Scan(&title)
	if title == nil || *title != "Act One" {
		t.Fatalf("create title not persisted: %v", title)
	}

	// rename — undo hint carries the PRIOR title
	res, _, err = s.toolPartRename(ctx, nil, partRenameIn{BookID: bookID.String(), PartID: partID, Title: "Act I"})
	if err != nil {
		t.Fatalf("rename: %v", err)
	}
	if tool, args := undoHintFromResult(t, res.Meta); tool != "book_part_rename" || args["title"] != "Act One" {
		t.Fatalf("rename undo hint should restore prior title 'Act One': %s %v", tool, args)
	}
	_ = pool.QueryRow(ctx0, `SELECT title FROM parts WHERE id=$1`, partID).Scan(&title)
	if *title != "Act I" {
		t.Fatalf("rename not persisted: %v", *title)
	}

	// archive — reverse is restore
	res, _, err = s.toolPartArchive(ctx, nil, partArchiveIn{BookID: bookID.String(), PartID: partID})
	if err != nil {
		t.Fatalf("archive: %v", err)
	}
	if tool, _ := undoHintFromResult(t, res.Meta); tool != "book_part_restore" {
		t.Fatalf("archive reverse should be restore, got %s", tool)
	}
	var lifecycle string
	_ = pool.QueryRow(ctx0, `SELECT lifecycle_state FROM parts WHERE id=$1`, partID).Scan(&lifecycle)
	if lifecycle != "trashed" {
		t.Fatalf("archive did not trash: %s", lifecycle)
	}

	// restore — reverse is archive
	res, _, err = s.toolPartRestore(ctx, nil, partRestoreIn{BookID: bookID.String(), PartID: partID})
	if err != nil {
		t.Fatalf("restore: %v", err)
	}
	if tool, _ := undoHintFromResult(t, res.Meta); tool != "book_part_archive" {
		t.Fatalf("restore reverse should be archive, got %s", tool)
	}
	_ = pool.QueryRow(ctx0, `SELECT lifecycle_state FROM parts WHERE id=$1`, partID).Scan(&lifecycle)
	if lifecycle != "active" {
		t.Fatalf("restore did not reactivate: %s", lifecycle)
	}
}

// reorder round-trips + the undo hint carries the PRIOR order.
func TestMCPParts_Reorder_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx0, pool, owner)
	s.resolveBook = ownerResolver(owner)
	ctx := identityCtxForTest(t, owner)

	_, a, _ := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookID.String(), Title: "A"})
	_, b, _ := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookID.String(), Title: "B"})

	res, _, err := s.toolPartReorder(ctx, nil, partReorderIn{BookID: bookID.String(), OrderedIDs: []string{b.PartID, a.PartID}})
	if err != nil {
		t.Fatalf("reorder: %v", err)
	}
	// DB now [b, a]
	var first uuid.UUID
	_ = pool.QueryRow(ctx0, `SELECT id FROM parts WHERE book_id=$1 AND sort_order=1`, bookID).Scan(&first)
	if first.String() != b.PartID {
		t.Fatalf("reorder did not put B first: %s", first)
	}
	// undo hint restores the prior order [a, b]
	tool, args := undoHintFromResult(t, res.Meta)
	if tool != "book_part_reorder" {
		t.Fatalf("reorder reverse tool = %s", tool)
	}
	prior, _ := args["ordered_ids"].([]string)
	if len(prior) != 2 || prior[0] != a.PartID || prior[1] != b.PartID {
		t.Fatalf("reorder undo hint should carry prior order [a,b], got %v", args["ordered_ids"])
	}

	// mismatch (subset) surfaces the store sentinel
	if _, _, err = s.toolPartReorder(ctx, nil, partReorderIn{BookID: bookID.String(), OrderedIDs: []string{a.PartID}}); !errors.Is(err, errReorderMismatch) {
		t.Fatalf("subset reorder err = %v, want errReorderMismatch", err)
	}
}

// set_part homes a chapter, un-homes it (null), and refuses a cross-book target.
func TestMCPPartsSetPart_RoundTripAndCrossBookBreach_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	bookA := seedPartsBook(t, ctx0, pool, owner)
	bookB := seedPartsBook(t, ctx0, pool, owner)
	s.resolveBook = ownerResolver(owner)
	ctx := identityCtxForTest(t, owner)

	_, partA, _ := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookA.String(), Title: "A-Act"})
	_, partB, _ := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookB.String(), Title: "B-Act"})
	ch := seedPartsChapter(t, ctx0, pool, bookA, 1, nil)

	// home into partA — undo hint restores prior part (null)
	aID := partA.PartID
	res, out, err := s.toolChapterSetPart(ctx, nil, chapterSetPartIn{BookID: bookA.String(), ChapterID: ch.String(), PartID: &aID})
	if err != nil {
		t.Fatalf("set_part in: %v", err)
	}
	if out.PartID == nil || *out.PartID != partA.PartID {
		t.Fatalf("set_part out part_id = %v, want %s", out.PartID, partA.PartID)
	}
	if _, args := undoHintFromResult(t, res.Meta); args["part_id"] != nil {
		t.Fatalf("set_part undo should restore prior null, got %v", args["part_id"])
	}
	var pid *uuid.UUID
	_ = pool.QueryRow(ctx0, `SELECT part_id FROM chapters WHERE id=$1`, ch).Scan(&pid)
	if pid == nil || pid.String() != partA.PartID {
		t.Fatalf("set_part not persisted: %v", pid)
	}

	// un-home (null) — undo restores the prior part (partA)
	res, out, err = s.toolChapterSetPart(ctx, nil, chapterSetPartIn{BookID: bookA.String(), ChapterID: ch.String(), PartID: nil})
	if err != nil {
		t.Fatalf("set_part null: %v", err)
	}
	if out.PartID != nil {
		t.Fatalf("un-home out part_id = %v, want nil", out.PartID)
	}
	if _, args := undoHintFromResult(t, res.Meta); args["part_id"] != partA.PartID {
		t.Fatalf("un-home undo should restore partA %s, got %v", partA.PartID, args["part_id"])
	}

	// cross-book breach: home chA into partB (a part of book B) via book A → refused
	bID := partB.PartID
	if _, _, err = s.toolChapterSetPart(ctx, nil, chapterSetPartIn{BookID: bookA.String(), ChapterID: ch.String(), PartID: &bID}); !errors.Is(err, errPartNotInBook) {
		t.Fatalf("cross-book set_part err = %v, want errPartNotInBook", err)
	}
	_ = pool.QueryRow(ctx0, `SELECT part_id FROM chapters WHERE id=$1`, ch).Scan(&pid)
	if pid != nil {
		t.Fatalf("cross-book move LANDED: %v", *pid)
	}
}

// A caller with no grant is uniformly refused (errBookNotAccessible) on a write,
// and no row lands.
func TestMCPParts_TenancyDenied_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	bookID := seedPartsBook(t, ctx0, pool, owner)
	s.resolveBook = func(_ context.Context, _, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if userID == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, uuid.Nil, "", nil // stranger: no grant
	}
	ctx := identityCtxForTest(t, stranger)

	if _, _, err := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookID.String(), Title: "sneak"}); !errors.Is(err, errBookNotAccessible) {
		t.Fatalf("stranger create err = %v, want errBookNotAccessible", err)
	}
	var n int
	_ = pool.QueryRow(ctx0, `SELECT COUNT(*) FROM parts WHERE book_id=$1`, bookID).Scan(&n)
	if n != 0 {
		t.Fatalf("stranger created a part: %d rows", n)
	}
}

// Parity with REST createPart + toolChapterCreate: you cannot add an act to a
// trashed book (the book-lifecycle gate holds on the MCP surface too).
func TestMCPParts_CreateOnTrashedBookRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx0 := context.Background()
	owner := uuid.New()
	bookID := seedPartsBook(t, ctx0, pool, owner)
	if _, err := pool.Exec(ctx0, `UPDATE books SET lifecycle_state='trashed' WHERE id=$1`, bookID); err != nil {
		t.Fatalf("trash book: %v", err)
	}
	s.resolveBook = ownerResolver(owner) // owner still has the grant on their trashed book
	ctx := identityCtxForTest(t, owner)

	if _, _, err := s.toolPartCreate(ctx, nil, partCreateIn{BookID: bookID.String(), Title: "x"}); err == nil {
		t.Fatal("create on a trashed book should be refused (parity with REST)")
	}
	var n int
	_ = pool.QueryRow(ctx0, `SELECT COUNT(*) FROM parts WHERE book_id=$1`, bookID).Scan(&n)
	if n != 0 {
		t.Fatalf("part created on a trashed book: %d rows", n)
	}
}
