package catalog

import (
	"os"
	"path/filepath"
	"testing"
)

func write(t *testing.T, dir, name, body string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

const validLint = `
id: projection-coverage
description: "L3.B every event type accounted for"
invariant: PRR-32
kind: lint
command: ["bash", "scripts/projection-coverage-lint.sh"]
requires: []
skip_when: []
fail_closed_on_setup_error: false
`

const validProbe = `
id: publisher-smoke
description: "outbox -> redis publish round-trip"
kind: live-probe
command: ["bash", "scripts/publisher-live-smoke.sh"]
requires: ["docker"]
`

func TestLoadValid(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "generic"), "projection-coverage.yaml", validLint)
	write(t, filepath.Join(root, "generic"), "publisher-smoke.yaml", validProbe)
	// the reserved expunge.yaml must be ignored, not parsed as a case
	write(t, root, "expunge.yaml", "projection-coverage: D-EXAMPLE\n")

	cases, err := Load(root)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(cases) != 2 {
		t.Fatalf("want 2 cases (expunge.yaml ignored), got %d: %+v", len(cases), cases)
	}
	// sorted by id → "projection-coverage" < "publisher-smoke" ('r' < 'u')
	if cases[0].ID != "projection-coverage" || cases[1].ID != "publisher-smoke" {
		t.Errorf("cases not sorted by id: %q, %q", cases[0].ID, cases[1].ID)
	}
	pc := cases[0]
	if pc.Kind != KindLint || pc.Invariant != "PRR-32" {
		t.Errorf("unexpected parse: %+v", pc)
	}
	if len(pc.Command) != 2 || pc.Command[0] != "bash" {
		t.Errorf("command parse: %+v", pc.Command)
	}
	probe := cases[1]
	if len(probe.Requires) != 1 || probe.Requires[0] != "docker" {
		t.Errorf("requires parse: %+v", probe.Requires)
	}
	if pc.Path() == "" {
		t.Error("Path() should record the source file")
	}
}

func TestLoadDuplicateID(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "a"), "one.yaml", validLint)
	write(t, filepath.Join(root, "b"), "two.yaml", validLint) // same id
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject duplicate case ids")
	}
}

func TestLoadMalformedYAML(t *testing.T) {
	root := t.TempDir()
	write(t, root, "bad.yaml", "id: x\nkind: lint\ncommand: [unterminated\n")
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject malformed YAML")
	}
}

func TestLoadInvalidKind(t *testing.T) {
	root := t.TempDir()
	write(t, root, "c.yaml", "id: x\nkind: wat\ncommand: [\"true\"]\n")
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject an invalid kind")
	}
}

func TestLoadEmptyCommand(t *testing.T) {
	root := t.TempDir()
	write(t, root, "c.yaml", "id: x\nkind: lint\ncommand: []\n")
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject an empty command")
	}
}

func TestLoadMissingID(t *testing.T) {
	root := t.TempDir()
	write(t, root, "c.yaml", "kind: lint\ncommand: [\"true\"]\n")
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject a missing id")
	}
}

func TestLoadUnknownKeyRejected(t *testing.T) {
	root := t.TempDir()
	write(t, root, "c.yaml", "id: x\nkind: lint\ncommand: [\"true\"]\ntypo_field: 1\n")
	if _, err := Load(root); err == nil {
		t.Fatal("Load must reject unknown keys (KnownFields) so typos surface")
	}
}
