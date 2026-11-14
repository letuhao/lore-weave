package tasks

// Static guard for the Codex P1 finding on PR #325 (F1 residual): the #287
// change made `seq DESC` the primary sort key for chapter revisions, but
// worker-infra writes book-service's chapter_revisions table DIRECTLY
// (BookDB; see the WS-0.3 comments at the import sites) and its two import
// writers (EPUB/DOCX in import_processor.go, PDF chunks in
// import_processor_pdf.go) still inserted without `seq`. Those rows kept the
// DEFAULT 0, breaking the counter invariant the #287 design promises
// (chapters.revision_seq == revision count) and sorting as legacy
// unsequenced rows.
//
// This test scans this package's own production sources (no DB needed, so it
// runs anywhere) and requires every revision INSERT to assign `seq` from the
// per-chapter counter. Test fixtures (_test.go) are excluded on purpose: they
// may plant legacy seq=0 rows to prove the readers tolerate them.
//
// Non-vacuity: the test asserts a floor on how many sites it sees, so a
// refactor that moves the SQL elsewhere fails loudly instead of passing
// vacuously. It FAILED on the pre-fix code (2 unsequenced INSERTs).

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

func TestWorkerRevisionInsertAlwaysAllocatesSeq(t *testing.T) {
	_, here, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	dir := filepath.Dir(here)
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("read dir: %v", err)
	}
	colList := regexp.MustCompile(`(?i)INSERT INTO chapter_revisions\s*\(([^)]*)\)`)
	found := 0
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
		ast.Inspect(f, func(n ast.Node) bool {
			lit, ok := n.(*ast.BasicLit)
			if !ok || lit.Kind != token.STRING || !strings.HasPrefix(lit.Value, "`") {
				return true
			}
			text := lit.Value[1 : len(lit.Value)-1]
			if !strings.Contains(strings.ToUpper(text), "INSERT INTO CHAPTER_REVISIONS") {
				return true
			}
			found++
			m := colList.FindStringSubmatch(text)
			if m == nil {
				t.Errorf("%s: INSERT INTO chapter_revisions without a parseable column list — the guard cannot verify seq; rewrite it in the standard form", name)
				return true
			}
			for _, c := range strings.Split(m[1], ",") {
				if strings.TrimSpace(strings.ToLower(c)) == "seq" {
					return true
				}
			}
			t.Errorf("%s: INSERT INTO chapter_revisions does not assign seq (columns: %s) — allocate from chapters.revision_seq, or the row sorts behind every real revision", name, m[1])
			return true
		})
	}
	// The package has 2 production INSERTs into chapter_revisions (the EPUB/DOCX
	// importer and the PDF chunk importer). Fewer means the scan missed a writer.
	if found < 2 {
		t.Errorf("found %d INSERT INTO chapter_revisions sites, want >= 2 — the guard is not seeing every producer", found)
	}
}
