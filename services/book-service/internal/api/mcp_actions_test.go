package api

import (
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
