package meta

import (
	"strings"
	"testing"
)

func TestParseAllowlist_RoundTrip(t *testing.T) {
	doc := []byte(`
version: 1
entries:
  - table: reality_registry
    owner: world-service
    events:
      - op: INSERT
        event_name: reality.created
      - op: UPDATE
        event_name: reality.status.changed
  - table: publisher_heartbeats
    owner: publisher
    events: []
`)
	a, err := ParseAllowlist(doc)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if !a.AllowsTable("reality_registry") {
		t.Errorf("reality_registry not allowed")
	}
	if !a.AllowsTable("publisher_heartbeats") {
		t.Errorf("publisher_heartbeats not allowed")
	}
	if a.AllowsTable("not_in_file") {
		t.Errorf("unexpected table allowed")
	}
	if name, ok := a.EmitsEvent("reality_registry", OpInsert); !ok || name != "reality.created" {
		t.Errorf("INSERT event mismatch: %q ok=%v", name, ok)
	}
	if name, ok := a.EmitsEvent("reality_registry", OpUpdate); !ok || name != "reality.status.changed" {
		t.Errorf("UPDATE event mismatch: %q ok=%v", name, ok)
	}
	if _, ok := a.EmitsEvent("reality_registry", OpDelete); ok {
		t.Errorf("DELETE should not emit")
	}
	if _, ok := a.EmitsEvent("publisher_heartbeats", OpInsert); ok {
		t.Errorf("publisher_heartbeats should not emit (events: [])")
	}
}

func TestParseAllowlist_VersionMismatch(t *testing.T) {
	_, err := ParseAllowlist([]byte(`version: 2
entries: []`))
	if err == nil || !strings.Contains(err.Error(), "version=2 unsupported") {
		t.Errorf("expected unsupported-version error, got %v", err)
	}
}

func TestParseAllowlist_DuplicateTable(t *testing.T) {
	_, err := ParseAllowlist([]byte(`
version: 1
entries:
  - table: foo
    events: []
  - table: foo
    events: []
`))
	if err == nil || !strings.Contains(err.Error(), "duplicate table") {
		t.Errorf("expected duplicate-table error, got %v", err)
	}
}

func TestParseAllowlist_InvalidOp(t *testing.T) {
	_, err := ParseAllowlist([]byte(`
version: 1
entries:
  - table: foo
    events:
      - op: TRUNCATE
        event_name: foo.truncated
`))
	if err == nil || !strings.Contains(err.Error(), "invalid") {
		t.Errorf("expected invalid-op error, got %v", err)
	}
}

func TestParseAllowlist_EmptyTable(t *testing.T) {
	_, err := ParseAllowlist([]byte(`
version: 1
entries:
  - table: ""
    events: []
`))
	if err == nil || !strings.Contains(err.Error(), "empty table") {
		t.Errorf("expected empty-table error, got %v", err)
	}
}

func TestLoadAllowlist_ShippedFile(t *testing.T) {
	a, err := LoadAllowlist("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load shipped file: %v", err)
	}
	// All 7 routing+lifecycle tables + session_cost_summary + meta_write_audit + meta_read_audit
	expect := []string{
		"reality_registry",
		"instance_schema_migrations",
		"publisher_heartbeats",
		"lifecycle_transition_audit",
		"reality_close_audit",
		"archive_verification_log",
		"reality_migration_audit",
		"session_cost_summary",
		"meta_write_audit",
		"meta_read_audit",
	}
	for _, tbl := range expect {
		if !a.AllowsTable(tbl) {
			t.Errorf("shipped allowlist missing %q", tbl)
		}
	}
}
