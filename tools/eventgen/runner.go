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

	if cfg.Validate {
		fmt.Fprintf(os.Stderr, "eventgen: registry valid — %d events registered\n", reg.Len())
		return nil
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
