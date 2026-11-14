package api

// Static guards for the two Codex P1 findings on PR #325 (no DB needed —
// they scan this package's own production sources, so they run anywhere).
//
// 1. Every revision INSERT must allocate `seq` from the per-chapter counter
//    (#287). The sort key is `seq DESC`; a writer that omits `seq` leaves a
//    0 that sorts behind every real revision and makes Revision Compare pick
//    a stale pair. Test fixtures (_test.go) are excluded on purpose: they
//    plant legacy seq=0 rows to prove the readers tolerate them.
//
// 2. Every write that locks BOTH a `chapter_drafts` row and its `chapters`
//    row must take the draft lock FIRST. The inverted order (chapters first)
//    deadlocks against REST patchDraft/publish, which lock draft-first:
//    each transaction then waits on the other's row (40P01). A single
//    statement locking both rows (`FOR UPDATE OF d, c`) is also rejected —
//    its lock order is the query plan's, not the code's; split it into two
//    ordered SELECTs.
//
// Non-vacuity: both guards assert a floor on how many sites they see, so a
// refactor that moves the SQL elsewhere fails loudly instead of passing
// vacuously. They FAILED on the pre-fix code (12 unsequenced INSERTs; the
// MCP save_draft / REST restore / diary inversions; the combined FOR UPDATE
// in indexChapter).

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"testing"
)

type sqlSpan struct {
	file     string
	function string
	start    int // byte offset of the opening backquote in the file
	text     string
}

func productionSQLSpans(t *testing.T) []sqlSpan {
	t.Helper()
	_, here, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	dir := filepath.Dir(here)
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read dir: %v", err)
	}
	var spans []sqlSpan
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() || !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") {
			continue
		}
		path := filepath.Join(dir, name)
		fset := token.NewFileSet()
		// Parse with the real Go parser: backquotes inside // comments (which
		// this codebase uses liberally) must not be mistaken for string
		// literals, so a regex scan of the raw source is not sound here.
		f, err := parser.ParseFile(fset, path, nil, 0)
		if err != nil {
			t.Fatalf("parse %s: %v", name, err)
		}
		tokFile := fset.File(f.Pos())
		// Function starts, in offset order, so each literal can be attributed.
		type fnAt struct {
			off  int
			name string
		}
		var fns []fnAt
		for _, d := range f.Decls {
			if fd, ok := d.(*ast.FuncDecl); ok {
				fns = append(fns, fnAt{off: tokFile.Offset(fd.Pos()), name: fd.Name.Name})
			}
		}
		ast.Inspect(f, func(n ast.Node) bool {
			lit, ok := n.(*ast.BasicLit)
			if !ok || lit.Kind != token.STRING || !strings.HasPrefix(lit.Value, "`") {
				return true
			}
			off := tokFile.Offset(lit.Pos())
			fn := "<top-level>"
			for _, f := range fns {
				if f.off <= off {
					fn = f.name
				} else {
					break
				}
			}
			spans = append(spans, sqlSpan{
				file: name, function: fn, start: off,
				text: lit.Value[1 : len(lit.Value)-1],
			})
			return true
		})
	}
	return spans
}

func TestRevisionInsertAlwaysAllocatesSeq(t *testing.T) {
	spans := productionSQLSpans(t)
	colList := regexp.MustCompile(`(?i)INSERT INTO chapter_revisions\s*\(([^)]*)\)`)
	found := 0
	for _, sp := range spans {
		if !strings.Contains(strings.ToUpper(sp.text), "INSERT INTO CHAPTER_REVISIONS") {
			continue
		}
		found++
		m := colList.FindStringSubmatch(sp.text)
		if m == nil {
			t.Errorf("%s:%s: INSERT INTO chapter_revisions without a parseable column list — the guard cannot verify seq; rewrite it in the standard form", sp.file, sp.function)
			continue
		}
		cols := strings.Split(m[1], ",")
		hasSeq := false
		for _, c := range cols {
			if strings.TrimSpace(strings.ToLower(c)) == "seq" {
				hasSeq = true
			}
		}
		if !hasSeq {
			t.Errorf("%s:%s: INSERT INTO chapter_revisions does not assign seq (columns: %s) — allocate from chapters.revision_seq, or the row sorts behind every real revision", sp.file, sp.function, m[1])
		}
	}
	// The package has 18 production INSERTs into chapter_revisions (6 converted
	// by #287, 12 by the Codex P1 fix). Fewer means the scan missed a writer.
	if found < 18 {
		t.Errorf("found %d INSERT INTO chapter_revisions sites, want >= 18 — the guard is not seeing every producer", found)
	}
}

func TestRevisionWriteLockOrderDraftFirst(t *testing.T) {
	spans := productionSQLSpans(t)
	// Per-function first-seen lock order. A span can carry at most one kind;
	// a span locking both rows at once is a violation on its own.
	type locks struct {
		firstDraft    int // -1 = none seen
		firstChapters int
	}
	byFn := map[string]*locks{}
	seenCombined := 0
	order := func(sp sqlSpan) (draft, chapters, combined bool) {
		up := strings.ToUpper(sp.text)
		if strings.Contains(up, "FOR UPDATE OF D, C") || strings.Contains(up, "FOR UPDATE OF D,C") {
			return false, false, true
		}
		if strings.Contains(up, "UPDATE CHAPTER_DRAFTS SET") ||
			strings.Contains(up, "FOR UPDATE OF D") ||
			(strings.Contains(up, "FOR UPDATE") && strings.Contains(up, "FROM CHAPTER_DRAFTS")) {
			draft = true
		}
		if strings.Contains(up, "UPDATE CHAPTERS SET") ||
			strings.Contains(up, "FOR UPDATE OF C") ||
			(strings.Contains(up, "FOR UPDATE") && strings.Contains(up, "FROM CHAPTERS")) {
			chapters = true
		}
		return draft, chapters, false
	}
	for _, sp := range spans {
		draft, chapters, combined := order(sp)
		if combined {
			seenCombined++
			t.Errorf("%s:%s: one statement locks both the draft and the chapter row (FOR UPDATE OF d, c) — its lock order is the query plan's, not the code's; split it into two ordered SELECTs (draft first)", sp.file, sp.function)
			continue
		}
		if !draft && !chapters {
			continue
		}
		key := sp.file + ":" + sp.function
		lk, ok := byFn[key]
		if !ok {
			lk = &locks{firstDraft: -1, firstChapters: -1}
			byFn[key] = lk
		}
		if draft && lk.firstDraft < 0 {
			lk.firstDraft = sp.start
		}
		if chapters && lk.firstChapters < 0 {
			lk.firstChapters = sp.start
		}
	}
	checked := 0
	for key, lk := range byFn {
		if lk.firstDraft < 0 || lk.firstChapters < 0 {
			continue // locks only one of the two rows — no cycle possible
		}
		checked++
		if lk.firstChapters < lk.firstDraft {
			t.Errorf("%s: locks the chapters row before the chapter_drafts row — REST patchDraft/publish lock draft-first, so this order deadlocks (40P01); take the draft lock first", key)
		}
	}
	// The write paths that lock both rows: patchDraft, publishChapter,
	// restoreRevision, mcpRestoreRevision, toolChapterSaveDraft, indexChapter,
	// mcpPublishChapter, and the three diary writers. Fewer means the scan
	// missed a path.
	if checked < 9 {
		t.Errorf("lock-order rule exercised on %d functions, want >= 9 — the guard is not seeing every two-row writer", checked)
	}
	if seenCombined > 0 {
		t.Errorf("found %d combined FOR UPDATE OF d, c statement(s)", seenCombined)
	}
}
