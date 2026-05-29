package auth

import (
	"errors"
	"strings"
	"testing"
)

func TestValidate_Empty(t *testing.T) {
	if _, err := Validate(""); err == nil || !errors.Is(err, ErrAuth) {
		t.Fatalf("want ErrAuth on empty, got %v", err)
	}
}

func TestValidate_NoDevPrefix(t *testing.T) {
	if _, err := Validate("foo:bar"); err == nil || !strings.Contains(err.Error(), "dev:") {
		t.Fatalf("want dev: prefix error, got %v", err)
	}
}

func TestValidate_HappyPath_PipeScopes(t *testing.T) {
	c, err := Validate("dev:ops1:sre:admin:read|admin:destructive")
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if c.Subject != "ops1" || c.Role != "sre" {
		t.Fatalf("bad claims: %+v", c)
	}
	if !c.HasScope("admin:read") || !c.HasScope("admin:destructive") {
		t.Fatalf("missing scope: %+v", c.Scopes)
	}
}

func TestValidate_BreakGlassSuffix(t *testing.T) {
	c, err := Validate("dev:ops1:founder:admin:destructive:break-glass")
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if !c.BreakGlass {
		t.Fatal("want BreakGlass=true")
	}
	if !c.HasScope("admin:destructive") {
		t.Fatalf("missing scope: %+v", c.Scopes)
	}
}

func TestRequireScopeForTier(t *testing.T) {
	cases := map[string]string{
		"tier-1-destructive":   "admin:destructive",
		"tier-2-griefing":      "admin:write",
		"tier-3-informational": "admin:read",
	}
	for tier, want := range cases {
		if got := RequireScopeForTier(tier); got != want {
			t.Errorf("RequireScopeForTier(%q) = %q, want %q", tier, got, want)
		}
	}
}
