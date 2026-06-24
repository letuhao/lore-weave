package meta

import (
	"strings"
	"testing"
)

func TestLoadSensitivePaths_ShippedFile(t *testing.T) {
	sp, err := LoadSensitivePaths("meta-sensitive-read-paths.yml")
	if err != nil {
		t.Fatalf("load shipped sensitive paths: %v", err)
	}
	// The full SSOT id-set — MUST match the meta_read_audit query_type CHECK
	// (migration 031); the read-audit-query-type-drift-lint CI gate enforces
	// CHECK == YAML, this asserts the Go loader sees every id.
	want := []string{
		"player_index_cross_user",
		"audit_query",
		"admin_bulk_export",
		"bulk_meta_query",
		"bulk_pii_read",
		"pii_user_get",
		"pii_user_erase",
	}
	for _, id := range want {
		if !sp.Has(id) {
			t.Errorf("shipped sensitive paths missing %q", id)
		}
		p := sp.Get(id)
		if p == nil || len(p.Reviewers) == 0 {
			t.Errorf("%q has no reviewers", id)
		}
	}
	if sp.Has("not_a_real_path") {
		t.Errorf("phantom path returned true")
	}
}

func TestParseSensitivePaths_DuplicateIDRejected(t *testing.T) {
	_, err := ParseSensitivePaths([]byte(`
version: 1
paths:
  - id: x
    description: "first"
    tables: [a]
    rationale: "r"
    reviewers: [team-sec]
  - id: x
    description: "second"
    tables: [b]
    rationale: "r"
    reviewers: [team-sec]
`))
	if err == nil || !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("want duplicate error, got %v", err)
	}
}

func TestParseSensitivePaths_NoTablesRejected(t *testing.T) {
	_, err := ParseSensitivePaths([]byte(`
version: 1
paths:
  - id: x
    description: "first"
    tables: []
    rationale: "r"
    reviewers: [team-sec]
`))
	if err == nil || !strings.Contains(err.Error(), "no tables") {
		t.Fatalf("want no-tables error, got %v", err)
	}
}

func TestParseSensitivePaths_NoReviewersRejected(t *testing.T) {
	_, err := ParseSensitivePaths([]byte(`
version: 1
paths:
  - id: x
    description: "first"
    tables: [a]
    rationale: "r"
    reviewers: []
`))
	if err == nil || !strings.Contains(err.Error(), "no reviewers") {
		t.Fatalf("want no-reviewers error, got %v", err)
	}
}
