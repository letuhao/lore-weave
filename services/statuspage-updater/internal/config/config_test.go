package config

import (
	"path/filepath"
	"testing"
)

func base(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "..", "infra", "statuspage")
}

func TestLoadComponents(t *testing.T) {
	c, err := LoadComponents(filepath.Join(base(t), "components.yaml"))
	if err != nil {
		t.Fatalf("LoadComponents: %v", err)
	}
	if len(c.Components) != 5 {
		t.Fatalf("components = %d want 5", len(c.Components))
	}
	for _, id := range []string{"gateway", "auth", "world", "roleplay", "realtime"} {
		if _, ok := c.Lookup(id); !ok {
			t.Errorf("missing component %q", id)
		}
	}
	if _, ok := c.Lookup("nope"); ok {
		t.Error("unknown component should not resolve")
	}
}

func TestLoadBannerConfig(t *testing.T) {
	b, err := LoadBannerConfig(filepath.Join(base(t), "banner-config.yaml"))
	if err != nil {
		t.Fatalf("LoadBannerConfig: %v", err)
	}
	sev0, ok := b.PolicyFor("SEV0")
	if !ok || !sev0.AutoBanner || sev0.StatuspageImpact != "critical" {
		t.Errorf("SEV0 policy = %+v", sev0)
	}
	sev2, _ := b.PolicyFor("SEV2")
	if sev2.AutoBanner {
		t.Error("SEV2 must not auto-banner")
	}
	sev3, _ := b.PolicyFor("SEV3")
	if sev3.StatuspageImpact != "none" {
		t.Errorf("SEV3 impact = %s want none", sev3.StatuspageImpact)
	}
	if !b.ClearOnResolve {
		t.Error("clear_on_resolve should be true")
	}
}
