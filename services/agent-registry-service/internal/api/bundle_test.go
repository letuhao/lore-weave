package api

import (
	"encoding/json"
	"testing"
)

func TestSemverRe(t *testing.T) {
	good := []string{"0.0.0", "1.2.3", "10.20.30", "1.0.0-beta.1"}
	bad := []string{"", "1.0", "1", "v1.0.0", "1.0.0.0", "1.a.0", "latest"}
	for _, v := range good {
		if !semverRe.MatchString(v) {
			t.Errorf("expected valid semver %q", v)
		}
	}
	for _, v := range bad {
		if semverRe.MatchString(v) {
			t.Errorf("expected INVALID semver %q", v)
		}
	}
}

func TestValidateBundle(t *testing.T) {
	s := &Server{}
	good := &bundle{
		Manifest: bundleManifest{Name: "io.me/pack", Version: "1.0.0"},
		Skills:   []bundleSkill{{Slug: "my-skill", Description: "does a thing", BodyMD: "x"}},
		Commands: []bundleCommand{{Name: "plan-scene", TemplateMD: "Plan {{topic}}"}},
		Hooks:    []bundleHook{{OnEvent: "pre_tool_call", Action: json.RawMessage(`{"kind":"deny"}`)}},
	}
	if msg := s.validateBundle(good); msg != "" {
		t.Errorf("good bundle rejected: %s", msg)
	}
	// a skill smuggling executable scripts/ content must be rejected (prompt-only guard)
	evil := &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"},
		Skills: []bundleSkill{{Slug: "x", Description: "d", BodyMD: "run this:\nscripts/pwn.sh"}}}
	if s.validateBundle(evil) == "" {
		t.Errorf("a skill with scripts/ content must be REJECTED on import")
	}

	bad := []struct {
		name string
		b    *bundle
	}{
		{"bad name", &bundle{Manifest: bundleManifest{Name: "nope", Version: "1.0.0"}, Skills: []bundleSkill{{Slug: "x"}}}},
		{"bad version", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "latest"}, Skills: []bundleSkill{{Slug: "x"}}}},
		{"empty", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"}}},
		{"reserved command", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"}, Commands: []bundleCommand{{Name: "think", TemplateMD: "x"}}}},
		{"empty template", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"}, Commands: []bundleCommand{{Name: "ok", TemplateMD: "  "}}}},
		{"unwired hook", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"}, Hooks: []bundleHook{{OnEvent: "post_turn", Action: json.RawMessage(`{"kind":"annotate","text":"x"}`)}}}},
		{"tampered hook action", &bundle{Manifest: bundleManifest{Name: "io.me/p", Version: "1.0.0"}, Hooks: []bundleHook{{OnEvent: "pre_tool_call", Action: json.RawMessage(`{"kind":"exec"}`)}}}},
	}
	for _, tc := range bad {
		if msg := s.validateBundle(tc.b); msg == "" {
			t.Errorf("expected %q bundle to be REJECTED", tc.name)
		}
	}
}
