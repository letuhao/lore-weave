package prompt

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestLoadTemplateRegistry_AllSevenIntentsLoad(t *testing.T) {
	// Foundation default — templates/ ships alongside the package.
	// Test the actual on-disk registry to catch any registry/intent drift.
	reg, err := LoadTemplateRegistry(repoTemplatesDir(t))
	if err != nil {
		t.Fatalf("LoadTemplateRegistry: %v", err)
	}
	for _, it := range AllIntents() {
		entry, ok := reg.Intents[it]
		if !ok {
			t.Fatalf("intent %q missing from registry", it)
		}
		if entry.ActiveVersion < 1 {
			t.Fatalf("intent %q ActiveVersion %d invalid", it, entry.ActiveVersion)
		}
		if entry.Status != "skeleton" && entry.Status != "active" {
			t.Fatalf("intent %q status %q must be skeleton|active", it, entry.Status)
		}
	}
}

func TestLoadTemplateRegistry_FailsFastOnMissingIntent(t *testing.T) {
	// Build an isolated registry without a required intent → MUST FAIL.
	tmp := t.TempDir()
	regFile := filepath.Join(tmp, "registry.yaml")
	if err := os.WriteFile(regFile, []byte(`intents:
  session_turn:
    active_version: 1
    status: skeleton
`), 0o644); err != nil {
		t.Fatal(err)
	}
	// Stub the v1.tmpl + v1.meta.yaml for the one intent so the
	// loader gets past the file-existence check and FAILS on the
	// missing-intent rule (the load enforces all 7 intents).
	intentDir := filepath.Join(tmp, "session_turn")
	if err := os.MkdirAll(intentDir, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"v1.tmpl", "v1.meta.yaml"} {
		if err := os.WriteFile(filepath.Join(intentDir, f), []byte("stub"), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	_, err := LoadTemplateRegistry(tmp)
	if err == nil {
		t.Fatal("expected FAIL on missing intents (only session_turn listed)")
	}
	if !errors.Is(err, ErrTemplateRegistryMissing) {
		t.Fatalf("expected ErrTemplateRegistryMissing wrap, got %v", err)
	}
}

func TestLoadTemplateRegistry_FailsFastOnMissingTmpl(t *testing.T) {
	tmp := t.TempDir()
	// Write a registry referencing all 7 intents but DON'T create tmpl files.
	body := "intents:\n"
	for _, it := range AllIntents() {
		body += "  " + string(it) + ":\n    active_version: 1\n    status: skeleton\n"
	}
	if err := os.WriteFile(filepath.Join(tmp, "registry.yaml"), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := LoadTemplateRegistry(tmp)
	if err == nil {
		t.Fatal("expected FAIL on missing v1.tmpl")
	}
}

func TestLoadTemplateRegistry_RegistryNotFound(t *testing.T) {
	_, err := LoadTemplateRegistry(t.TempDir())
	if err == nil {
		t.Fatal("expected error on missing registry.yaml")
	}
	if !errors.Is(err, ErrTemplateRegistryMissing) {
		t.Fatalf("expected ErrTemplateRegistryMissing, got %v", err)
	}
}

// repoTemplatesDir returns the absolute path to contracts/prompt/templates/
// at the foundation root. The test binary runs from the package dir so
// the relative path is "templates".
func repoTemplatesDir(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	return filepath.Join(wd, "templates")
}
