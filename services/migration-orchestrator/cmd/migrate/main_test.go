package main

import (
	"bytes"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
