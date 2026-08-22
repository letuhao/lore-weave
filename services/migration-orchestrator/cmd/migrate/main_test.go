package main

import (
	"bytes"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/loreweave/foundation/contracts/realityreg"
)

// writeTempManifest puts a valid manifest into a tmp file and returns the path.
func writeTempManifest(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "manifest.yaml")
	body := `
version: 1
migrations:
  - id: "0001_initial"
    version: 1
    breaking: false
    description: "skeleton"
  - id: "0002_breaking_change"
    version: 2
    breaking: true
    dependencies: ["0001_initial"]
    description: "breaking thing"
`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

// captureRun executes run() with a temp-stdout helper.
func captureRun(args []string) (string, string, error) {
	stdoutR, stdoutW, _ := os.Pipe()
	stderrR, stderrW, _ := os.Pipe()
	err := run(args, stdoutW, stderrW)
	_ = stdoutW.Close()
	_ = stderrW.Close()
	out, _ := io.ReadAll(stdoutR)
	errOut, _ := io.ReadAll(stderrR)
	return string(out), string(errOut), err
}

func TestHelp(t *testing.T) {
	for _, arg := range []string{"-h", "--help"} {
		out, _, err := captureRun([]string{arg})
		if err != nil {
			t.Errorf("%s: %v", arg, err)
		}
		if !strings.Contains(out, "Usage:") {
			t.Errorf("%s: usage missing in output", arg)
		}
	}
}

func TestList(t *testing.T) {
	mp := writeTempManifest(t)
	out, _, err := captureRun([]string{"list", "--manifest", mp})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "0001_initial") || !strings.Contains(out, "0002_breaking_change") {
		t.Errorf("list output missing entries: %s", out)
	}
}

func TestApply_DryRun_NonBreaking(t *testing.T) {
	mp := writeTempManifest(t)
	out, _, err := captureRun([]string{"0001_initial", "--dry-run", "--manifest", mp})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "concurrency=10") {
		t.Errorf("expected concurrency=10 in non-breaking dry-run output: %s", out)
	}
}

func TestApply_DryRun_Breaking_RoutesThroughCanary(t *testing.T) {
	mp := writeTempManifest(t)
	out, _, err := captureRun([]string{"0002_breaking_change", "--dry-run", "--manifest", mp})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "canary") {
		t.Errorf("expected canary route in breaking dry-run output: %s", out)
	}
	if !strings.Contains(out, "Q-L1D-1") {
		t.Errorf("expected Q-L1D-1 rollback hint: %s", out)
	}
}

func TestApply_UnknownMigration_Errors(t *testing.T) {
	mp := writeTempManifest(t)
	_, _, err := captureRun([]string{"nope", "--dry-run", "--manifest", mp})
	if err == nil {
		t.Fatal("expected error on unknown migration")
	}
}

// Sanity: ensure the binary's bytes line count is sensible (regression guard
// for accidental file truncation).
func TestUsageNonEmpty(t *testing.T) {
	if len(bytes.TrimSpace([]byte(usage))) < 100 {
		t.Errorf("usage string suspiciously short")
	}
}

// ─── `A2` — `--reality`, and why its refusal is the point ────────────────────
//
// The fleet was all-or-nothing: `ActiveRealities` returns every drainable row
// and nothing narrowed it. A board that wanted "dry-run first, on ONE reality"
// could not express that, and both alternatives were worse — editing
// `reality_registry.status` is a live write to the meta database made in order
// to make a live write safer, and a fleet-wide first attempt is the caution
// abandoned.

func fleetOf(ids ...string) []realityreg.Reality {
	out := make([]realityreg.Reality, 0, len(ids))
	for _, id := range ids {
		out = append(out, realityreg.Reality{ID: id, DBHost: "h", DBName: "db_" + id})
	}
	return out
}

func TestSelectFleet_EmptySelectorIsTheWholeFleet(t *testing.T) {
	f := fleetOf("a", "b", "c")
	got, err := selectFleet(f, "")
	if err != nil {
		t.Fatalf("empty selector must be the previous behaviour, got %v", err)
	}
	if len(got) != 3 {
		t.Fatalf("want the whole fleet, got %d", len(got))
	}
}

func TestSelectFleet_NarrowsToNamedIds(t *testing.T) {
	f := fleetOf("a", "b", "c")
	got, err := selectFleet(f, " b , c ")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0].ID != "b" || got[1].ID != "c" {
		t.Fatalf("want [b c], got %v", got)
	}
}

// THE ARM THAT MATTERS. A mistyped uuid must not narrow the fleet to nothing:
// `runLive` would print "no active realities to migrate", exit 0, and an
// operator would believe a migration reached a reality it never touched.
func TestSelectFleet_UnknownIdIsRefusedNotSilentlyNarrowed(t *testing.T) {
	f := fleetOf("a", "b")
	got, err := selectFleet(f, "typo")
	if err == nil {
		t.Fatalf("an id outside the fleet must be REFUSED, got %d selected", len(got))
	}
	if !strings.Contains(err.Error(), "not in the drainable fleet") {
		t.Fatalf("the refusal must say why, got %q", err)
	}
}

func TestSelectFleet_OneGoodOneBadStillRefuses(t *testing.T) {
	// Partial credit is the dangerous shape: applying to `a` while silently
	// dropping the typo reads as success for both.
	f := fleetOf("a", "b")
	if _, err := selectFleet(f, "a,typo"); err == nil {
		t.Fatal("a selector with one bad id must refuse the whole selection")
	}
}

func TestSelectFleet_DuplicatesAreCollapsed(t *testing.T) {
	f := fleetOf("a", "b")
	got, err := selectFleet(f, "a,a")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("a repeated id must not migrate it twice, got %d", len(got))
	}
}

func TestSelectFleet_SelectorOfOnlySeparatorsIsRefused(t *testing.T) {
	// `--reality ,,,` is a typo, not a request for the whole fleet. Falling
	// back to "everything" here would make the safest-looking flag the most
	// dangerous one.
	f := fleetOf("a", "b")
	if _, err := selectFleet(f, ",, ,"); err == nil {
		t.Fatal("a selector naming no ids must refuse, never fall back to the fleet")
	}
}
