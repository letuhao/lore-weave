package api

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// D-2-CHAPTER-PAGINATION — book_get_chapter(include_body) used to be an UNBOUNDED string_agg over
// every block, so a long chapter dumped its entire prose into one tool result: the context problem
// in miniature, and past the MCP result-size ceiling an outright failure. It also had no way to say
// "there is more" — the caller could not tell a whole chapter from a partial one.
//
// These tests pin the contract the W11 reader depends on:
//   - the read is BOUNDED by default (never unbounded again),
//   - a short chapter is returned whole, with NO truncation noise,
//   - a long chapter SIGNALS truncated + next_offset (never silently short — that is the
//     silent-truncation bug class this repo treats as a defect),
//   - paging with offset/limit reassembles the chapter EXACTLY, losing nothing.
func TestMCPGetChapter_PagesAndSignalsTruncation_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()

	owner := uuid.New()
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	bookID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO books(id,owner_user_id,title,kind,lifecycle_state) VALUES($1,$2,'pagination',
'novel','active')`, bookID, owner); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) })

	// A chapter with MORE blocks than one page holds — the case the old code read unbounded.
	nBlocks := maxChapterBlocks + 25
	chID := uuid.New()
	if _, err := pool.Exec(ctx, `
INSERT INTO chapters(id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state)
VALUES($1,$2,'Long chapter','long.txt','en','text/plain',0,1,'k','active')`, chID, bookID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	want := make([]string, 0, nBlocks)
	for i := 0; i < nBlocks; i++ {
		text := fmt.Sprintf("para-%03d", i)
		want = append(want, text)
		if _, err := pool.Exec(ctx,
			`INSERT INTO chapter_blocks(chapter_id,block_index,block_type,text_content,content_hash)
             VALUES($1,$2,'paragraph',$3,md5($3))`, chID, i, text); err != nil {
			t.Fatalf("seed block %d: %v", i, err)
		}
	}

	// ── page 1: bounded, and it SAYS it stopped early ────────────────────────────────────
	_, out, err := s.toolBookGetChapter(tctx, nil, getChapterIn{
		BookID: bookID.String(), ChapterID: chID.String(), IncludeBody: true,
	})
	if err != nil {
		t.Fatalf("get chapter: %v", err)
	}
	if out.Body == nil {
		t.Fatal("body missing")
	}
	if !out.Truncated {
		t.Fatalf("a %d-block chapter must report truncated=true (page holds %d) — a caller "+
			"cannot distinguish a whole chapter from a partial one otherwise", nBlocks, maxChapterBlocks)
	}
	if out.NextOffset == nil || *out.NextOffset != maxChapterBlocks {
		t.Fatalf("next_offset = %v, want %d", out.NextOffset, maxChapterBlocks)
	}
	if out.TotalBlocks == nil || *out.TotalBlocks != nBlocks {
		t.Fatalf("total_blocks = %v, want %d", out.TotalBlocks, nBlocks)
	}
	got1 := strings.Split(*out.Body, "\n\n")
	if len(got1) != maxChapterBlocks {
		t.Fatalf("page 1 returned %d blocks, want the %d-block cap (an unbounded read is the bug)",
			len(got1), maxChapterBlocks)
	}

	// ── page 2: continue from next_offset; the tail arrives and truncation CLEARS ────────
	_, out2, err := s.toolBookGetChapter(tctx, nil, getChapterIn{
		BookID: bookID.String(), ChapterID: chID.String(), IncludeBody: true,
		Offset: *out.NextOffset,
	})
	if err != nil {
		t.Fatalf("get chapter page 2: %v", err)
	}
	if out2.Truncated {
		t.Error("the final page must NOT report truncated")
	}
	if out2.NextOffset != nil {
		t.Errorf("the final page must not carry next_offset, got %v", *out2.NextOffset)
	}

	// ── the whole point: paging LOSES NOTHING ────────────────────────────────────────────
	got := append(got1, strings.Split(*out2.Body, "\n\n")...)
	if len(got) != nBlocks {
		t.Fatalf("reassembled %d blocks, want %d — paging dropped content", len(got), nBlocks)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("block %d = %q, want %q — paging reordered or corrupted the prose", i, got[i], want[i])
		}
	}
}

// A chapter that FITS in one page must look exactly like it always did: whole body, and no
// truncation noise. This is the back-compat half — every existing caller reads a normal chapter.
func TestMCPGetChapter_ShortChapterIsWholeAndNotTruncated_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()

	owner := uuid.New()
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	tctx := identityCtxForTest(t, owner)

	bookID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO books(id,owner_user_id,title,kind,lifecycle_state) VALUES($1,$2,'short','novel','active')`,
		bookID, owner); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID) })

	chID := uuid.New()
	if _, err := pool.Exec(ctx, `
INSERT INTO chapters(id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state)
VALUES($1,$2,'Short','short.txt','en','text/plain',0,1,'k','active')`, chID, bookID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	for i, text := range []string{"one", "two", "three"} {
		if _, err := pool.Exec(ctx,
			`INSERT INTO chapter_blocks(chapter_id,block_index,block_type,text_content,content_hash)
             VALUES($1,$2,'paragraph',$3,md5($3))`, chID, i, text); err != nil {
			t.Fatalf("seed block: %v", err)
		}
	}

	_, out, err := s.toolBookGetChapter(tctx, nil, getChapterIn{
		BookID: bookID.String(), ChapterID: chID.String(), IncludeBody: true,
	})
	if err != nil {
		t.Fatalf("get chapter: %v", err)
	}
	if out.Truncated || out.NextOffset != nil {
		t.Errorf("a 3-block chapter must not be truncated; got truncated=%v next=%v",
			out.Truncated, out.NextOffset)
	}
	if out.Body == nil || *out.Body != "one\n\ntwo\n\nthree" {
		t.Fatalf("body = %q, want the whole chapter", derefStr(out.Body))
	}
}
