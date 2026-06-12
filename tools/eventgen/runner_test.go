package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// repoRoot returns the repo root from the tools/eventgen/ test cwd.
func repoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	// wd is …/tools/eventgen; root is two up.
	return filepath.Join(wd, "..", "..")
}

// TestRun_ValidateMode confirms --validate mode parses registry without emit.
func TestRun_ValidateMode(t *testing.T) {
	root := repoRoot(t)
	tmp := t.TempDir()
	err := Run(Config{
		RegistryPath: filepath.Join(root, "contracts", "events", "_registry.yaml"),
		EventsDir:    filepath.Join(root, "contracts", "events"),
		OutDir:       tmp,
		Target:       "all",
		Validate:     true,
	})
	if err != nil {
		t.Fatalf("Run(validate=true): %v", err)
	}
	// tmp must be EMPTY (validate only).
	entries, _ := os.ReadDir(tmp)
	if len(entries) > 0 {
		t.Fatalf("validate mode wrote files: %v", entries)
	}
}

// TestRun_AllTargets covers the full emit pipeline.
func TestRun_AllTargets(t *testing.T) {
	root := repoRoot(t)
	tmp := t.TempDir()
	err := Run(Config{
		RegistryPath: filepath.Join(root, "contracts", "events", "_registry.yaml"),
		EventsDir:    filepath.Join(root, "contracts", "events"),
		OutDir:       tmp,
		Target:       "all",
	})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	// Expected outputs:
	expected := []string{
		"registry_generated.go",
		"rust/mod.rs",
		"rust/npc_said_v1.rs",
		"rust/npc_said_v2.rs",
		"rust/reality_created_v1.rs",
		"rust/world_tick_v1.rs",
		"ts/index.ts",
		"ts/npc-said-v1.ts",
		"ts/npc-said-v2.ts",
		"ts/reality-created-v1.ts",
		"ts/world-tick-v1.ts",
		"python/__init__.py",
		"python/npc_said_v1.py",
		"python/npc_said_v2.py",
		"python/reality_created_v1.py",
		"python/world_tick_v1.py",
	}
	for _, p := range expected {
		full := filepath.Join(tmp, p)
		if _, err := os.Stat(full); err != nil {
			t.Errorf("expected output missing: %s (%v)", p, err)
		}
	}
}

// TestRun_GoDispatchTableContent confirms generated Go has expected dispatch entries.
func TestRun_GoDispatchTableContent(t *testing.T) {
	root := repoRoot(t)
	tmp := t.TempDir()
	if err := Run(Config{
		RegistryPath: filepath.Join(root, "contracts", "events", "_registry.yaml"),
		EventsDir:    filepath.Join(root, "contracts", "events"),
		OutDir:       tmp,
		Target:       "go",
	}); err != nil {
		t.Fatalf("Run: %v", err)
	}
	body, err := os.ReadFile(filepath.Join(tmp, "registry_generated.go"))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	mustContain := []string{
		"DO NOT EDIT",
		"package events",
		`"npc.said":`,
		`1: "NpcSaidV1"`,
		`2: "NpcSaidV2"`,
		`"reality.created":`,
		`1: "RealityCreatedV1"`,
		`"world.tick":`,
		`1: "WorldTickV1"`,
		"EventTypesGenerated",
	}
	for _, s := range mustContain {
		if !strings.Contains(string(body), s) {
			t.Errorf("registry_generated.go missing %q", s)
		}
	}
}

// TestRun_Deterministic: two runs produce byte-identical output.
func TestRun_Deterministic(t *testing.T) {
	root := repoRoot(t)
	tmp1, tmp2 := t.TempDir(), t.TempDir()
	for _, out := range []string{tmp1, tmp2} {
		if err := Run(Config{
			RegistryPath: filepath.Join(root, "contracts", "events", "_registry.yaml"),
			EventsDir:    filepath.Join(root, "contracts", "events"),
			OutDir:       out,
			Target:       "all",
		}); err != nil {
			t.Fatalf("Run(%s): %v", out, err)
		}
	}
	// Compare every generated file.
	for _, rel := range []string{
		"registry_generated.go",
		"rust/mod.rs",
		"ts/index.ts",
		"python/__init__.py",
	} {
		a, _ := os.ReadFile(filepath.Join(tmp1, rel))
		b, _ := os.ReadFile(filepath.Join(tmp2, rel))
		if !bytes.Equal(a, b) {
			t.Errorf("%s: output not deterministic", rel)
		}
	}
}

// TestRun_UnknownTarget errors.
func TestRun_UnknownTarget(t *testing.T) {
	root := repoRoot(t)
	err := Run(Config{
		RegistryPath: filepath.Join(root, "contracts", "events", "_registry.yaml"),
		EventsDir:    filepath.Join(root, "contracts", "events"),
		OutDir:       t.TempDir(),
		Target:       "cobol",
	})
	if err == nil {
		t.Fatal("expected error for unknown target")
	}
	if !strings.Contains(err.Error(), "cobol") {
		t.Errorf("error should mention target: %v", err)
	}
}
