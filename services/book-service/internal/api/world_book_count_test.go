package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #309 — a membership count that counted books the user had thrown away.
//
// world_get is correct on everything else, verified field-by-field against the database on a real
// world (封神演義): book_count 2 against 2 non-bible members, bible_book_id and bible_chapter_id
// matching the world's is_bible book and its only sort_order-0 chapter, an unknown UUID answering
// "world not found" and a malformed one "world_id must be a UUID".
//
// book_count was the exception. It excluded only `purge_pending`, so a `trashed` book still
// counted as a member. Constructed live: a world whose single member was an already-trashed book
// reported book_count 1 — and NO surface will show that book, because book_list's access filter
// is lifecycle_state='active'.
//
// What makes it a defect rather than a cosmetic difference is that on the agent surface book_count
// is the ONLY membership signal that exists: world_get returns no member list, and book_list has
// no world filter (its args are book_id, chapter_id, kind, limit, offset). So an agent is told the
// world holds one book and then cannot find any book in it, with no way to reconcile the two.
//
// The instance-wide measurement is what says this is latent rather than raging: 196 worlds, 0 with
// a trashed member. It had to be constructed to be seen — which is also why nothing caught it.
func TestWorldBookCountCountsOnlyActiveBooks(t *testing.T) {
	c := bookCountExpr(t)
	if !strings.Contains(c, "b.lifecycle_state='active'") {
		t.Error("book_count no longer counts active books only — a trashed book counts as a world " +
			"member again, and book_count is the only membership signal the agent surface has")
	}
	if strings.Contains(c, "!='purge_pending'") {
		t.Error("book_count is back to excluding only purge_pending, which counts trashed books")
	}
}

// The count must agree with the definition of "a book you have" used everywhere else. If book_list
// or the book-limit counter ever changes its filter, this count has to move with it — a count and
// a list that disagree are how the original defect read to a caller.
func TestBookCountAgreesWithEveryOtherDefinitionOfHavingABook(t *testing.T) {
	read := mustReadFile(t, "mcp_tools_read.go")
	if !strings.Contains(read, "b.lifecycle_state='active'") {
		t.Error("book_list's access filter is no longer lifecycle_state='active'; world_get's " +
			"book_count was aligned to it and the two have drifted apart")
	}
	write := mustReadFile(t, "mcp_tools_write.go")
	if !strings.Contains(write, "is_bible=false AND kind<>'diary' AND lifecycle_state='active'") {
		t.Error("the book-limit counter no longer defines a book you have as active-only")
	}
}

// The narrowing must stay confined to the COUNT. The list endpoints return b.lifecycle_state per
// row, so a consumer there can tell a trashed member apart; dropping those rows would hide
// membership rather than describe it, and would break the trash view's world context.
func TestTheMemberListStillReturnsTrashedRowsWithTheirState(t *testing.T) {
	src := mustReadFile(t, "worlds.go")
	listCount := strings.Count(src, "WHERE b.world_id=$1 AND b.is_bible=false AND b.lifecycle_state!='purge_pending'")
	if listCount < 2 {
		t.Errorf("the world member-list queries lost their !='purge_pending' filter (found %d, "+
			"want the 2 list endpoints) — narrowing the COUNT must not silently drop rows from "+
			"the LIST, which reports lifecycle_state and can render a trashed member honestly",
			listCount)
	}
	if !strings.Contains(src, "b.lifecycle_state, b.created_at") {
		t.Error("the member list no longer returns lifecycle_state per row, so a consumer can no " +
			"longer distinguish a trashed member — which is the only reason the list may keep " +
			"counting them while the count does not")
	}
}

// bookCountExpr returns just the book_count sub-select, so an assertion cannot match one of the
// several other lifecycle predicates in this file.
func bookCountExpr(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "worlds.go")
	i := strings.Index(src, "AS book_count")
	if i < 0 {
		t.Fatal("book_count is gone from worldSelectSQL")
	}
	start := strings.LastIndex(src[:i], "COALESCE((SELECT COUNT(*) FROM books")
	if start < 0 {
		t.Fatal("the book_count sub-select is gone")
	}
	return src[start:i]
}
