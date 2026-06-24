package manifest

import (
	"errors"
	"strings"
	"testing"
)

const validYAML = `
version: 1
migrations:
  - id: "0001_initial"
    version: 1
    breaking: false
    description: "per-reality skeleton (events/outbox/snapshots/projection_meta) — cycle 5"
  - id: "0002_events_partitioning"
    version: 2
    breaking: true
    dependencies: ["0001_initial"]
    description: "L2 cycle 8 monthly partitioning"
`

func TestParse_Valid(t *testing.T) {
	m, err := Parse([]byte(validYAML))
	if err != nil {
		t.Fatalf("expected ok, got %v", err)
	}
	if len(m.Migrations) != 2 {
		t.Fatalf("expected 2 migrations, got %d", len(m.Migrations))
	}
	if m.Migrations[0].ID != "0001_initial" {
		t.Fatalf("first migration must be 0001_initial; got %q", m.Migrations[0].ID)
	}
	if !m.Migrations[1].Breaking {
		t.Fatal("migration 0002_events_partitioning must be breaking=true")
	}
}

func TestValidate_VersionWrong(t *testing.T) {
	in := strings.Replace(validYAML, "version: 1\n", "version: 2\n", 1)
	_, err := Parse([]byte(in))
	if !errors.Is(err, ErrManifestInvalid) {
		t.Fatalf("expected ErrManifestInvalid, got %v", err)
	}
}

func TestValidate_FirstMigrationMustBe0001Initial(t *testing.T) {
	in := strings.Replace(validYAML, `id: "0001_initial"`, `id: "0001_other"`, 1)
	_, err := Parse([]byte(in))
	if !errors.Is(err, ErrManifestInvalid) {
		t.Fatalf("expected ErrManifestInvalid (cycle 5 skeleton invariant), got %v", err)
	}
}

func TestValidate_DuplicateID(t *testing.T) {
	in := strings.Replace(validYAML, `id: "0002_events_partitioning"`, `id: "0001_initial"`, 1)
	_, err := Parse([]byte(in))
	if !errors.Is(err, ErrManifestInvalid) {
		t.Fatalf("expected ErrManifestInvalid (duplicate id), got %v", err)
	}
}

func TestValidate_NonMonotonic(t *testing.T) {
	// Author the bad YAML directly — strings.Replace on validYAML is brittle.
	in := `
version: 1
migrations:
  - id: "0001_initial"
    version: 1
  - id: "0002_b"
    version: 1
    dependencies: ["0001_initial"]
`
	_, err := Parse([]byte(in))
	if !errors.Is(err, ErrManifestInvalid) {
		t.Fatalf("expected ErrManifestInvalid (non-monotonic), got %v", err)
	}
}

func TestValidate_DependencyForwardRef(t *testing.T) {
	in := `
version: 1
migrations:
  - id: "0001_initial"
    version: 1
    dependencies: ["0099_future"]
`
	_, err := Parse([]byte(in))
	if !errors.Is(err, ErrManifestInvalid) {
		t.Fatalf("expected ErrManifestInvalid (forward dep), got %v", err)
	}
}

func TestFind(t *testing.T) {
	m, err := Parse([]byte(validYAML))
	if err != nil {
		t.Fatal(err)
	}
	if got := m.Find("0001_initial"); got == nil {
		t.Fatal("Find(0001_initial) returned nil")
	}
	if got := m.Find("nope"); got != nil {
		t.Fatal("Find(nope) returned non-nil")
	}
}

// TestValidate_RealManifestFile parses the actual shipped manifest.yaml as
// a cycle-5 carryforward regression guard. If the file moves or the
// schema drifts, this test fails loudly.
func TestValidate_RealManifestFile(t *testing.T) {
	// Path is relative to the test binary's working dir = this package dir.
	// repo root is 4 levels up: internal/manifest → service → services → repo
	const realPath = "../../../../contracts/migrations/manifest.yaml"
	m, err := Load(realPath)
	if err != nil {
		t.Fatalf("Load(%s): %v", realPath, err)
	}
	if m.Migrations[0].ID != "0001_initial" {
		t.Fatalf("shipped manifest first id = %q (expected 0001_initial)", m.Migrations[0].ID)
	}
}
