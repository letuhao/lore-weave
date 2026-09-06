package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/loreweave/foundation/contracts/events"
)

// Config is the eventgen run config.
type Config struct {
	RegistryPath string
	EventsDir    string
	OutDir       string
	Target       string // all | go | rust | ts | python
	Validate     bool   // parse only; emit nothing
	// SDKPythonOut, when non-empty, is the path of a SELF-CONTAINED Python module of
	// event-name constants, written for distribution through `sdks/python`.
	//
	// It is a separate flag rather than another file under OutDir on purpose:
	// `scripts/eventgen-validate.sh` regenerates into a temp dir and `diff -r`s it against
	// OutDir, so anything extra written under OutDir during validation would read as drift.
	// Empty (the default) writes nothing, which is what keeps that comparison honest.
	SDKPythonOut string
}

// Run executes the eventgen pipeline:
//  1. Load + validate registry
//  2. If --validate: return early
//  3. Emit per-target outputs to OutDir
//
// Determinism: events are sorted by name before each emitter is invoked.
func Run(cfg Config) error {
	reg, err := events.LoadRegistry(cfg.RegistryPath)
	if err != nil {
		return fmt.Errorf("load registry: %w", err)
	}

	// BEFORE --validate returns and before any emitter runs. A field-map gap is
	// a registry-level defect, so `--validate` — the mode whose whole job is to
	// answer "is this registry OK to ship" — must not answer yes to a registry
	// that generates empty contracts. And running it ahead of the emitters means
	// a bad state never reaches disk, so the files a reviewer opens are never
	// the empty ones.
	if err := checkFieldMaps(reg); err != nil {
		return err
	}

	if cfg.Validate {
		fmt.Fprintf(os.Stderr, "eventgen: registry valid — %d events registered\n", reg.Len())
		return nil
	}

	// The SDK constants module. Emitted from the registry, so the names it carries and the
	// names the Go constants carry cannot disagree.
	if cfg.SDKPythonOut != "" {
		if err := EmitSDKPythonConstants(reg, cfg.SDKPythonOut); err != nil {
			return fmt.Errorf("emit sdk python constants: %w", err)
		}
	}

	emitters := map[string]Emitter{
		"go":     EmitGo,
		"rust":   EmitRust,
		"ts":     EmitTypeScript,
		"python": EmitPython,
	}

	targets := []string{}
	switch cfg.Target {
	case "all":
		// stable order so output paths are predictable
		targets = []string{"go", "rust", "ts", "python"}
	case "go", "rust", "ts", "python":
		targets = []string{cfg.Target}
	default:
		return fmt.Errorf("unknown --target %q (want: all | go | rust | ts | python)", cfg.Target)
	}

	for _, t := range targets {
		emit, ok := emitters[t]
		if !ok {
			return fmt.Errorf("no emitter for target %q", t)
		}
		// outDir per target:
		//   go     → cfg.OutDir/registry_generated.go    (single file at root)
		//   rust   → cfg.OutDir/rust/
		//   ts     → cfg.OutDir/ts/
		//   python → cfg.OutDir/python/
		out := cfg.OutDir
		if t != "go" {
			out = filepath.Join(cfg.OutDir, t)
		}
		if err := os.MkdirAll(out, 0o755); err != nil {
			return fmt.Errorf("mkdir %s: %w", out, err)
		}
		if err := emit(reg, out); err != nil {
			return fmt.Errorf("emit %s: %w", t, err)
		}
	}

	return nil
}

// Emitter is the per-language codegen function signature.
type Emitter func(reg *events.Registry, outDir string) error
