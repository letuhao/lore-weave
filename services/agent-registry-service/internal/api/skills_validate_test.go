package api

import "testing"

// invalidSurface is the shared REST-path gate (validateSkill, patchSkill) that
// keeps `surfaces` in sync with the MCP schema's enum (tool_helpers.go
// enumSurfaces) — both REST write paths must reject an out-of-set value
// instead of silently persisting it.

func TestInvalidSurface_AllValid(t *testing.T) {
	if bad := invalidSurface([]string{"chat", "admin"}); bad != "" {
		t.Fatalf("expected no invalid surface, got %q", bad)
	}
}

func TestInvalidSurface_Empty(t *testing.T) {
	if bad := invalidSurface(nil); bad != "" {
		t.Fatalf("expected empty surfaces to be valid (no filter), got %q", bad)
	}
}

func TestInvalidSurface_RejectsUnknownValue(t *testing.T) {
	if bad := invalidSurface([]string{"chat", "bogus"}); bad != "bogus" {
		t.Fatalf("expected 'bogus' flagged as invalid, got %q", bad)
	}
}

func TestValidateSkill_RejectsInvalidSurface(t *testing.T) {
	in := &skillInput{
		Slug:        "my-skill",
		Description: "does a thing",
		Surfaces:    []string{"chat", "not-a-real-surface"},
	}
	msg, ok := validateSkill(in)
	if ok {
		t.Fatalf("expected validateSkill to reject an unknown surface, got ok=true")
	}
	if msg == "" {
		t.Fatalf("expected a non-empty validation message")
	}
}

func TestValidateSkill_AcceptsValidSurfaces(t *testing.T) {
	in := &skillInput{
		Slug:        "my-skill",
		Description: "does a thing",
		Surfaces:    []string{"chat", "compose", "translate", "admin"},
	}
	if _, ok := validateSkill(in); !ok {
		t.Fatalf("expected validateSkill to accept the full canonical surface set")
	}
}
