// migrate — admin CLI for migration-orchestrator (L1.D.4).
//
// Usage:
//
//	migrate <migration_id> [--dry-run] [--manifest <path>]
//	migrate list [--manifest <path>]
//
// On `migrate <migration_id>`:
//   - Loads contracts/migrations/manifest.yaml (or --manifest path).
//   - Looks up the migration entry.
//   - If breaking=true → routes through internal/canary (1 reality first).
//     SRE must then call `migrate verify <migration_id> --pass` (or --fail)
//     to release the gate; cycle 7 wires the actual verification suite.
//   - If breaking=false → routes through internal/runner directly with
//     the default concurrency cap of 10.
//
// Cycle 6 (L1.D.4) ships the CLI skeleton: argument parsing, manifest
// lookup, and dry-run flow. The live MetaWriter / Applier bindings to
// the meta-HA + per-reality DBs ship in cycle 7+ (L1.C ↔ L1.D wiring),
// captured as deferred in docs/deferred/DEFERRED.md.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/manifest"
)

const usage = `migrate — LoreWeave migration orchestrator CLI

Usage:
  migrate <migration_id> [--dry-run] [--manifest <path>]
  migrate list [--manifest <path>]

Flags:
  --dry-run         print what would be done without invoking dispatchers
  --manifest <p>    path to manifest.yaml (default: contracts/migrations/manifest.yaml)
`

func main() {
	if err := run(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "ERROR:", err)
		os.Exit(1)
	}
}

func run(args []string, stdout, stderr *os.File) error {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Fprint(stdout, usage)
		return nil
	}

	fs := flag.NewFlagSet("migrate", flag.ContinueOnError)
	fs.SetOutput(stderr)
	dryRun := fs.Bool("dry-run", false, "print plan without invoking dispatchers")
	manifestPath := fs.String("manifest", "contracts/migrations/manifest.yaml", "manifest path")

	cmd := args[0]
	switch cmd {
	case "list":
		if err := fs.Parse(args[1:]); err != nil {
			return err
		}
		return cmdList(*manifestPath, stdout)
	default:
		// Treat as <migration_id>
		if err := fs.Parse(args[1:]); err != nil {
			return err
		}
		return cmdApply(cmd, *manifestPath, *dryRun, stdout)
	}
}

func cmdList(manifestPath string, stdout *os.File) error {
	m, err := manifest.Load(manifestPath)
	if err != nil {
		return err
	}
	fmt.Fprintln(stdout, "migration_id\tversion\tbreaking\tdescription")
	for _, mig := range m.Migrations {
		fmt.Fprintf(stdout, "%s\t%d\t%v\t%s\n", mig.ID, mig.Version, mig.Breaking, mig.Description)
	}
	return nil
}

func cmdApply(migrationID, manifestPath string, dryRun bool, stdout *os.File) error {
	m, err := manifest.Load(manifestPath)
	if err != nil {
		return err
	}
	mig := m.Find(migrationID)
	if mig == nil {
		return fmt.Errorf("migration %q not found in %s", migrationID, manifestPath)
	}
	fmt.Fprintf(stdout, "migration: %s v%d breaking=%v\n", mig.ID, mig.Version, mig.Breaking)
	if dryRun {
		if mig.Breaking {
			fmt.Fprintln(stdout, "would: route through internal/canary (1 reality first, verification gate, fanout)")
		} else {
			fmt.Fprintln(stdout, "would: route through internal/runner with concurrency=10")
		}
		fmt.Fprintln(stdout, "Q-L1D-1: V1 doc-only rollback. On persistent failure consult runbooks/migration/persistent_failure.md")
		return nil
	}
	// Cycle 6 ships the CLI skeleton; the live MetaWriter / Applier wiring
	// to the meta-HA stack ships in cycle 7+. Until then, non-dry-run is a
	// no-op with a tracked deferral message — same conservative pattern as
	// the cycle-5 orphan_scanner safety guard.
	_ = context.Background()
	_ = time.Now()
	fmt.Fprintln(stdout, "live dispatch not yet wired (cycle 7+ task: bind MetaWriter + per-reality Applier)")
	fmt.Fprintln(stdout, "tracked in docs/deferred/DEFERRED.md row D-MIGRATE-CLI-LIVE-WIRING")
	return nil
}
