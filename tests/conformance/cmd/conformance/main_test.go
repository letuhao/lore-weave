package main

import (
	"bufio"
	"os"
	"path/filepath"
	"testing"

	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

const sampleCase = `id: only-case
kind: lint
command: ["true"]
`

func TestWriteJSONLRoundTrip(t *testing.T) {
	dir := t.TempDir()
	results := []verdict.Result{
		{ID: "a", Kind: "lint", Verdict: verdict.Pass, DurationMS: 1},
		{ID: "b", Kind: "live-probe", Verdict: verdict.Notrun, Reason: "precondition unmet: foundation-stack"},
	}
	if err := writeJSONL(dir, "test-run", results); err != nil {
		t.Fatalf("writeJSONL: %v", err)
	}

	f, err := os.Open(filepath.Join(dir, "conformance-test-run.jsonl"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer f.Close()

	var got []verdict.Result
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		r, err := verdict.ParseLine(sc.Bytes())
		if err != nil {
			t.Fatalf("ParseLine: %v", err)
		}
		got = append(got, r)
	}
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0].ID != "a" || got[1].Verdict != verdict.Notrun {
		t.Errorf("round-trip mismatch: %+v", got)
	}
}

func TestWriteJSONLSanitizesRunID(t *testing.T) {
	dir := t.TempDir()
	// A traversal-y run id must not escape dir; filepath.Base strips it.
	if err := writeJSONL(dir, filepath.Join("..", "..", "evil"), nil); err != nil {
		t.Fatalf("writeJSONL: %v", err)
	}
	if _, err := os.Stat(filepath.Join(dir, "conformance-evil.jsonl")); err != nil {
		t.Errorf("record should be written inside dir as conformance-evil.jsonl: %v", err)
	}
	// nothing should have been written outside dir
	if entries, _ := os.ReadDir(filepath.Dir(dir)); len(entries) != 1 {
		t.Errorf("expected only the temp dir in its parent, got %d entries", len(entries))
	}
}

func TestRunHarnessErrorOnMissingCatalog(t *testing.T) {
	// A nonexistent catalog dir is a harness error (exit 2), not a gate verdict.
	code := run(config{catalogDir: filepath.Join(t.TempDir(), "nope"), repoRoot: "../..", resultsDir: t.TempDir(), runID: "x"})
	if code != 2 {
		t.Errorf("missing catalog must exit 2 (harness error), got %d", code)
	}
}

func TestRunZeroCasesIsHarnessError(t *testing.T) {
	empty := t.TempDir() // exists but holds no case files
	if code := run(config{catalogDir: empty, repoRoot: "../..", resultsDir: t.TempDir(), runID: "z"}); code != 2 {
		t.Errorf("zero cases must exit 2 by default, got %d", code)
	}
	if code := run(config{catalogDir: empty, repoRoot: "../..", resultsDir: t.TempDir(), runID: "z", allowEmpty: true}); code != 0 {
		t.Errorf("zero cases with -allow-empty must be green (0), got %d", code)
	}
}

func TestRunDanglingExpungeIsHarnessError(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "case.yaml"), []byte(sampleCase), 0o644); err != nil {
		t.Fatal(err)
	}
	// expunge names an id that is not a real case → dangling → exit 2
	if err := os.WriteFile(filepath.Join(dir, "expunge.yaml"), []byte("ghost-case: DEFERRED-X\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if code := run(config{catalogDir: dir, repoRoot: "../..", resultsDir: t.TempDir(), runID: "d"}); code != 2 {
		t.Errorf("a dangling expunge id must exit 2, got %d", code)
	}
}
