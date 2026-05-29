package events

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// ── L2.F acceptance test ── registry loads from the shipped _registry.yaml.
func TestLoadRegistry_ShippedFile(t *testing.T) {
	// Find the package directory; _registry.yaml is co-located.
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	path := filepath.Join(wd, "_registry.yaml")
	r, err := LoadRegistry(path)
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	if r.Len() < 3 {
		t.Fatalf("expected >=3 events in seed registry, got %d", r.Len())
	}
	// Sanity: all three seed events present.
	for _, name := range []string{"reality.created", "npc.said", "world.tick"} {
		if _, err := r.LookupType(name); err != nil {
			t.Errorf("seed event %q missing: %v", name, err)
		}
	}
	// npc.said has v1 + v2.
	for _, v := range []uint32{1, 2} {
		if _, err := r.Lookup("npc.said", v); err != nil {
			t.Errorf("npc.said v%d missing: %v", v, err)
		}
	}
	// v1 is deprecated; v2 is not.
	if !r.IsDeprecated("npc.said", 1) {
		t.Error("npc.said v1 should be deprecated")
	}
	if r.IsDeprecated("npc.said", 2) {
		t.Error("npc.said v2 should NOT be deprecated")
	}
}

// ── L2.F: unknown (type, version) returns ErrUnknownEventSchema.
func TestLookup_UnknownReturnsTypedError(t *testing.T) {
	r := mustParseRegistry(t, `version: 1
events:
  - name: foo.bar
    aggregate: foo
    versions: [1]
    active_version: 1
    go_struct: FooBarV1
    description: Bar.
    shipped_cycle: 8
    owner: test
`)
	_, err := r.Lookup("foo.bar", 99)
	if err == nil {
		t.Fatal("expected error for unknown version")
	}
	var typed ErrUnknownEventSchemaText
	if !errors.As(err, &typed) {
		t.Errorf("expected ErrUnknownEventSchemaText, got %T: %v", err, err)
	}
	if typed.EventType != "foo.bar" || typed.EventVersion != 99 {
		t.Errorf("typed error fields wrong: %+v", typed)
	}
}

// ── L2.F: malformed registry fails fast.
func TestParseRegistry_DuplicateName(t *testing.T) {
	_, err := ParseRegistry([]byte(`version: 1
events:
  - {name: foo.bar, aggregate: foo, versions: [1], active_version: 1, go_struct: FooV1, description: x, shipped_cycle: 8, owner: t}
  - {name: foo.bar, aggregate: foo, versions: [1], active_version: 1, go_struct: FooV1, description: x, shipped_cycle: 8, owner: t}
`))
	assertParseError(t, err, "duplicate")
}

func TestParseRegistry_VersionsNotAscending(t *testing.T) {
	_, err := ParseRegistry([]byte(`version: 1
events:
  - {name: foo.bar, aggregate: foo, versions: [2, 1], active_version: 1, go_struct: FooV1, description: x, shipped_cycle: 8, owner: t}
`))
	assertParseError(t, err, "ascending")
}

func TestParseRegistry_ActiveVersionNotInVersions(t *testing.T) {
	_, err := ParseRegistry([]byte(`version: 1
events:
  - {name: foo.bar, aggregate: foo, versions: [1, 2], active_version: 99, go_struct: FooV1, description: x, shipped_cycle: 8, owner: t}
`))
	assertParseError(t, err, "active_version")
}

func TestParseRegistry_EmptyDescription(t *testing.T) {
	_, err := ParseRegistry([]byte(`version: 1
events:
  - {name: foo.bar, aggregate: foo, versions: [1], active_version: 1, go_struct: FooV1, description: '', shipped_cycle: 8, owner: t}
`))
	assertParseError(t, err, "description")
}

func TestParseRegistry_UnsupportedFileVersion(t *testing.T) {
	_, err := ParseRegistry([]byte(`version: 99
events: []`))
	assertParseError(t, err, "unsupported registry file version")
}

func TestParseRegistry_DeprecationUpcasterToInvalid(t *testing.T) {
	// upcaster_to references a version NOT in versions[]
	_, err := ParseRegistry([]byte(`version: 1
events:
  - name: foo.bar
    aggregate: foo
    versions: [1, 2]
    active_version: 2
    go_struct: FooV2
    description: x
    shipped_cycle: 8
    owner: t
    deprecations:
      - {version: 1, deprecated_at: '2026-01-01', retire_after: '2026-07-01', upcaster_to: 99}
`))
	assertParseError(t, err, "upcaster_to 99")
}

func TestParseRegistry_DeprecationUpcasterBackward(t *testing.T) {
	// upcaster_to must be > version (forward only)
	_, err := ParseRegistry([]byte(`version: 1
events:
  - name: foo.bar
    aggregate: foo
    versions: [1, 2]
    active_version: 2
    go_struct: FooV2
    description: x
    shipped_cycle: 8
    owner: t
    deprecations:
      - {version: 2, deprecated_at: '2026-01-01', retire_after: '2026-07-01', upcaster_to: 1}
`))
	assertParseError(t, err, "forward-only")
}

// ── helpers ──

func mustParseRegistry(t *testing.T, yaml string) *Registry {
	t.Helper()
	r, err := ParseRegistry([]byte(yaml))
	if err != nil {
		t.Fatalf("ParseRegistry: %v", err)
	}
	return r
}

func assertParseError(t *testing.T, err error, contains string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected parse error containing %q, got nil", contains)
	}
	var typed ErrRegistryParseText
	if !errors.As(err, &typed) {
		t.Fatalf("expected ErrRegistryParseText, got %T: %v", err, err)
	}
	if !contains2(typed.Detail, contains) {
		t.Errorf("error detail %q does not contain %q", typed.Detail, contains)
	}
}

func contains2(haystack, needle string) bool {
	if len(needle) == 0 {
		return true
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
