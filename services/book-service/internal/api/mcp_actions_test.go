package api

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

// TOOLV2 LOOP #86 — an absent CHAPTER used to be reported as an inaccessible BOOK.
//
// Measured live: proposing a publish for a chapter id that does not exist, in a book the caller
// had just read successfully, answered "book not accessible". The grant check runs BEFORE this
// point, so by then the book is accessible by definition and the message states something false.
// book_get_chapter — same service, same book, same absent id — answers "no active chapter with
// that chapter_id in this book — check the chapter_id (call book_list kind=chapters for valid
// ids)": it names the argument and its satisfier instead of the wrong noun.
//
// H13's uniform "not found or not accessible" exists to deny an enumeration ORACLE. There is no
// oracle to protect at this point in the flow — the caller has already proven it may read this
// book — so uniformity here buys nothing and costs the caller its next move.
//
// LIMITATION, stated rather than implied: this reads the source. Both branches sit behind a pgx
// pool and a grant check, so exercising them needs a live database, and this package has no such
// harness. The anchors are the FULL branch including its return, not a loose substring, so a
// revert reds them — but a guard that cannot run the handler is weaker than one that can, and
// calling it behavioural would be a lie.
func TestAnAbsentChapterIsNotReportedAsAnInaccessibleBook(t *testing.T) {
	src, err := os.ReadFile("mcp_actions.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	// The working copy is CRLF here and os.ReadFile returns the raw bytes, so anchors written
	// with LF find nothing and the guard reds for the wrong reason. It did, on its first run.
	// Normalise so the anchors describe the CODE rather than the checkout.
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	// Both chapter-existence checks — the plain propose path and the gated one. A fix applied
	// to one of two sites is the shape this repo keeps finding.
	for _, want := range []string{
		"Scan(&exists); err != nil || !exists {\n\t\treturn nil, confirmCardOut{}, errChapterNotInBook",
		"Scan(&exists); err != nil || !exists {\n\t\treturn nil, nil, errChapterNotInBook",
	} {
		if strings.Count(body, want) != 1 {
			t.Errorf("a chapter-existence branch does not name the chapter: %q", want)
		}
	}
	for _, bad := range []string{
		"Scan(&exists); err != nil || !exists {\n\t\treturn nil, confirmCardOut{}, errBookNotAccessible",
		"Scan(&exists); err != nil || !exists {\n\t\treturn nil, nil, errBookNotAccessible",
	} {
		if strings.Contains(body, bad) {
			t.Errorf("a chapter-existence check still blames the book: %q", bad)
		}
	}

	// TOOLV2 LOOP #129 — the same false noun at two more sites, in kg_index.go, on a path that is
	// not a propose at all. errActionTargetGone means the CHAPTER is gone, and the grant check has
	// already passed, so errBookNotAccessible there is equally false.
	kg, kerr := os.ReadFile("kg_index.go")
	if kerr != nil {
		t.Fatalf("read kg_index.go: %v", kerr)
	}
	kgBody := strings.ReplaceAll(string(kg), "\r\n", "\n")
	// Anchor on the RETURN, not on bare mentions: my own explanatory comment names
	// errBookNotAccessible, and the first version of this guard reddened on that.
	if strings.Contains(kgBody, "indexChapterOut{}, errBookNotAccessible") ||
		strings.Contains(kgBody, "setKGExcludeOut{}, errBookNotAccessible") {
		t.Error("kg_index.go still maps a missing CHAPTER (errActionTargetGone) to the BOOK error")
	}
	if n := strings.Count(kgBody, "errChapterNotInBook"); n != 2 {
		t.Errorf("both kg_index target-gone branches must name the chapter, got %d", n)
	}

	// TOOLV2 LOOP #131 — the BOOK-level purge had the same missing precondition as the
	// chapter-level one. There is only ONE book-card mint site (proposeBookActionGated); the
	// chapter path has two, which is why #123 needed a pair and this needs one.
	if n := strings.Count(body, `SELECT lifecycle_state='trashed' FROM books`); n != 1 {
		t.Errorf("the book propose path must CHECK lifecycle_state='trashed' at mint time, got %d", n)
	}
	if !strings.Contains(body, "purge only removes an ALREADY-TRASHED book; delete it first (book_delete), then purge") {
		t.Error("the book-purge refusal must name the precondition and its satisfier")
	}
}

// The two errors must stay distinguishable, and the chapter one must carry its satisfier —
// otherwise the fix above would be swapping one uninformative message for another.
func TestTheChapterErrorNamesTheArgumentAndItsSatisfier(t *testing.T) {
	got := errChapterNotInBook.Error()
	if !strings.Contains(got, "chapter_id") {
		t.Errorf("must name the offending argument: %q", got)
	}
	if !strings.Contains(got, "book_list") {
		t.Errorf("must name the tool that lists valid ids: %q", got)
	}
	if got == errBookNotAccessible.Error() {
		t.Errorf("the chapter and book errors must be distinguishable")
	}
}

// TOOLV2 LOOP #123 — book_chapter_purge minted an irreversible card for an ACTIVE chapter.
//
// Its own description promises it purges a TRASHED chapter. Live, against a chapter whose
// lifecycle_state was `active`, it returned a normal "Permanently purge chapter (irreversible)"
// card — putting a human one click from destroying a live chapter, having been told the tool
// only removes trash. Found on the tool's first ever invocation; nothing had called it before.
func TestPurgeRefusesAChapterThatIsNotTrashed(t *testing.T) {
	src, err := os.ReadFile("mcp_actions.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	// BOTH propose paths — the plain one and the durable-gate one. A guard on one of two
	// sites is the shape this repo keeps finding, and #86 fixed exactly that pair.
	// Anchor on the CHECK, not on `if op == "purge_chapter"` — that phrase also appears in the
	// apply path, where it selects the target state rather than guarding a precondition. The
	// first version of this guard counted 3 and reddened for the wrong reason.
	if n := strings.Count(body, `SELECT lifecycle_state='trashed' FROM chapters`); n != 2 {
		t.Errorf("both propose paths must CHECK lifecycle_state='trashed' at mint time, got %d", n)
	}
	// The refusal has to name the state AND the way out, not just say no.
	if !strings.Contains(body, "purge only removes an ALREADY-TRASHED chapter; delete it first (book_chapter_delete), then purge") {
		t.Error("the refusal must name the precondition and its satisfier")
	}
}

// TOOLV2 LOOP #122 — the bulk-create undo hint named an argument the delete tool rejects.
func TestBulkCreateUndoHintIsNotAVerbatimArgLie(t *testing.T) {
	src, err := os.ReadFile("mcp_tools_write.go")
	if err != nil {
		t.Fatalf("read source: %v", err)
	}
	body := strings.ReplaceAll(string(src), "\r\n", "\n")

	// `args` is documented as the reverse tool's argument TEMPLATE. book_chapter_delete takes
	// chapter_id (singular), so a bare chapter_ids list in args is unreplayable.
	if !strings.Contains(body, `"repeat_arg":  "chapter_id"`) {
		t.Error("a multi-id undo must declare that it repeats, or the hint reads as one verbatim call")
	}
	if strings.Contains(body, `map[string]any{"book_id": bookID.String(), "chapter_ids": ids}`) {
		t.Error("the bare chapter_ids arg template is back — replaying it is rejected by book_chapter_delete")
	}
}

// TOOLV2 LOOP #124 — book_chapter_reorder committed its write and then failed its OWN output
// schema, so the caller saw a protocol error for an effect that had landed.
//
// uuid.UUID is [16]byte: the MCP schema generator declares it `type: "array"` while it marshals
// as a string. Measured on the tool's first ever invocation — two chapters moved in the database
// and the response was rejected with
// `/properties/chapters/items/properties/chapter_id: type: <uuid> has type "string", want "array"`.
//
// This is a TYPE guard, not a string match: it fails to compile if ChapterID stops being a
// string, which is stronger than any source anchor.
func TestReorderedChapterIDIsAStringSoTheSchemaMatchesTheJSON(t *testing.T) {
	var rc reorderedChapter
	if _, ok := any(rc.ChapterID).(string); !ok {
		t.Fatalf("reorderedChapter.ChapterID must be a string; a uuid.UUID generates "+
			`type:"array" in the output schema while marshalling as a string, and the SDK `+
			"then rejects every successful response. got %T", rc.ChapterID)
	}
	// And the field must still serialise under the same key — the JSON is meant to be
	// byte-identical to the uuid.UUID form, so no consumer sees a change.
	b, err := json.Marshal(reorderedChapter{ChapterID: "019febe4-79b1-7936-a78e-aa6f550dd3d8", SortOrder: 2})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if got := string(b); got != `{"chapter_id":"019febe4-79b1-7936-a78e-aa6f550dd3d8","sort_order":2}` {
		t.Errorf("wire shape changed: %s", got)
	}
}
