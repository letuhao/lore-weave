// Command conformance runs the foundation conformance suite.
//
// It loads the declarative catalog, executes each case, downgrades expunged
// failures, writes a JSONL run record, prints a summary, and exits:
//
//	0  — no case failed (notrun/skip/pass only)              → gate green
//	1  — at least one case failed                            → gate red
//	2  — a harness error (catalog/expunge load failed, etc.) → not a case verdict
//
// Run it from the module dir (the default -repo-root of ../.. then points at the
// repo root, where case commands like `bash scripts/<lint>.sh` resolve):
//
//	go run ./cmd/conformance -catalog ./catalog
package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/loreweave/foundation/tests/conformance/internal/catalog"
	"github.com/loreweave/foundation/tests/conformance/internal/expunge"
	"github.com/loreweave/foundation/tests/conformance/internal/runner"
	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

type config struct {
	catalogDir  string
	repoRoot    string
	resultsDir  string
	runID       string
	allowEmpty  bool
	caseTimeout time.Duration
}

func main() {
	var cfg config
	flag.StringVar(&cfg.catalogDir, "catalog", "catalog", "path to the conformance catalog tree")
	flag.StringVar(&cfg.repoRoot, "repo-root", "../..", "repo root to run case commands from")
	flag.StringVar(&cfg.resultsDir, "results", "results", "directory for the JSONL run record")
	flag.StringVar(&cfg.runID, "run-id", "", "identifier for this run (default: a UTC timestamp)")
	flag.BoolVar(&cfg.allowEmpty, "allow-empty", false, "permit a catalog that loads zero cases (default: zero cases is a harness error, so a mis-pointed -catalog fails loudly instead of going green)")
	flag.DurationVar(&cfg.caseTimeout, "case-timeout", 5*time.Minute, "per-case execution ceiling (0 disables)")
	flag.Parse()

	os.Exit(run(cfg))
}

func run(cfg config) int {
	cases, err := catalog.Load(cfg.catalogDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "conformance: load catalog: %v\n", err)
		return 2
	}
	if len(cases) == 0 && !cfg.allowEmpty {
		fmt.Fprintf(os.Stderr, "conformance: catalog %q loaded 0 cases (use -allow-empty to permit)\n", cfg.catalogDir)
		return 2
	}
	exp, err := expunge.Load(filepath.Join(cfg.catalogDir, catalog.ExpungeFilename))
	if err != nil {
		fmt.Fprintf(os.Stderr, "conformance: load expunge list: %v\n", err)
		return 2
	}

	// An expunge entry that names no real case means the list has rotted (a case
	// was renamed/removed) — fail loudly rather than let a stale audit trail rot.
	known := make(map[string]bool, len(cases))
	for _, c := range cases {
		known[c.ID] = true
	}
	if dangling := exp.Dangling(known); len(dangling) > 0 {
		fmt.Fprintf(os.Stderr, "conformance: expunge list has dangling id(s) with no matching case: %s\n", strings.Join(dangling, ", "))
		return 2
	}

	absRoot, err := filepath.Abs(cfg.repoRoot)
	if err != nil {
		fmt.Fprintf(os.Stderr, "conformance: resolve repo root: %v\n", err)
		return 2
	}

	r := runner.New(runner.OSEnvironment{}, runner.OSExecutor{Dir: absRoot}).WithCaseTimeout(cfg.caseTimeout)
	raw := r.Run(context.Background(), cases)
	results := exp.Downgrade(raw)
	summary := runner.Summarize(results)

	if err := writeJSONL(cfg.resultsDir, cfg.runID, results); err != nil {
		// Non-fatal: a missing results store must not turn a green run red.
		fmt.Fprintf(os.Stderr, "conformance: warning: could not write results: %v\n", err)
	}

	fmt.Printf("repo root: %s · catalog: %s · %d case(s)\n", absRoot, cfg.catalogDir, len(cases))
	fmt.Print(summary.Render())
	for _, rr := range results {
		if expunge.WasExpunged(rr) {
			fmt.Printf("  (expunged) %s — %s\n", rr.ID, rr.Reason)
		}
	}
	return summary.GateExitCode()
}

// writeJSONL appends one JSON object per result to results/conformance-<id>.jsonl,
// giving a machine-readable run history (parallels the perf time-series §8).
func writeJSONL(dir, runID string, results []verdict.Result) error {
	if runID == "" {
		runID = time.Now().UTC().Format("20060102T150405Z")
	}
	runID = filepath.Base(runID) // keep the record file inside dir (no path escape)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(dir, "conformance-"+runID+".jsonl")
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	w := bufio.NewWriter(f)
	for _, r := range results {
		line, err := r.MarshalLine()
		if err != nil {
			return err
		}
		if _, err := w.Write(append(line, '\n')); err != nil {
			return err
		}
	}
	return w.Flush()
}
