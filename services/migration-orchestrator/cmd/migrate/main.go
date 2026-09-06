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
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/realityreg"

	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/live"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/manifest"
)

const usage = `migrate — LoreWeave migration orchestrator CLI

Usage:
  migrate <migration_id> [--dry-run] [--manifest <path>] [live flags]
  migrate list [--manifest <path>]

Flags:
  --dry-run             print what would be done without invoking dispatchers
  --manifest <p>        path to manifest.yaml (default: contracts/migrations/manifest.yaml)

Live flags (non-dry-run; the CLI is fail-closed without --meta-dsn):
  --meta-dsn <dsn>      meta DB DSN (reality_registry + audit tables). Required.
  --sql-dir <dir>       per-reality migration SQL dir (default: contracts/migrations/per_reality)
  --allowlist <p>       events_allowlist.yaml (default: contracts/meta/events_allowlist.yaml)
  --host-override <m>   dev shard remap, e.g. "*=127.0.0.1:55511" (default: none — prod hosts)
  --pg-user / --pg-pass per-reality shard role (default: foundation/foundation)
  --pg-port <n>         per-reality shard port (default: 5432)
  --ssl <mode>          per-reality sslmode (default: disable)
  --concurrency <n>     fan-out concurrency cap (default: 10)
  --reality <id[,id]>   apply to ONLY these realities (default: the whole
                        drainable fleet). An id that is not in the fleet is a
                        REFUSAL, never a silent narrowing.
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
	lf := liveFlags{}
	fs.StringVar(&lf.metaDSN, "meta-dsn", "", "meta DB DSN (required for live apply)")
	fs.StringVar(&lf.sqlDir, "sql-dir", "contracts/migrations/per_reality", "per-reality migration SQL dir")
	fs.StringVar(&lf.allowlist, "allowlist", "contracts/meta/events_allowlist.yaml", "events allowlist path")
	fs.StringVar(&lf.hostOverride, "host-override", "", "dev shard remap host=host:port[,*=...]")
	fs.StringVar(&lf.pgUser, "pg-user", "foundation", "per-reality shard role")
	fs.StringVar(&lf.pgPass, "pg-pass", "foundation", "per-reality shard password")
	fs.IntVar(&lf.pgPort, "pg-port", 5432, "per-reality shard port")
	fs.StringVar(&lf.ssl, "ssl", "disable", "per-reality sslmode")
	fs.IntVar(&lf.concurrency, "concurrency", 0, "fan-out concurrency cap (0 = default 10)")
	fs.StringVar(&lf.reality, "reality", "", "comma-separated reality ids; default = whole fleet")

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
		return cmdApply(cmd, *manifestPath, *dryRun, lf, stdout)
	}
}

// liveFlags holds the live-apply connection + routing config.
type liveFlags struct {
	metaDSN      string
	sqlDir       string
	allowlist    string
	hostOverride string
	pgUser       string
	pgPass       string
	pgPort       int
	ssl          string
	concurrency  int
	reality      string
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

func cmdApply(migrationID, manifestPath string, dryRun bool, lf liveFlags, stdout *os.File) error {
	m, err := manifest.Load(manifestPath)
	if err != nil {
		return err
	}
	mig := m.Find(migrationID)
	if mig == nil {
		return fmt.Errorf("migration %q not found in %s", migrationID, manifestPath)
	}
	fmt.Fprintf(stdout, "migration: %s v%d breaking=%v\n", mig.ID, mig.Version, mig.Breaking)
	// `A2` -- a dry run WITH a meta DSN resolves the REAL fleet and prints what
	// would be touched, without touching it. See planLive.
	if dryRun && lf.metaDSN != "" {
		return planLive(migrationID, mig.Breaking, lf, stdout)
	}
	if dryRun {
		if mig.Breaking {
			fmt.Fprintln(stdout, "would: route through internal/canary (1 reality first, verification gate, fanout)")
		} else {
			fmt.Fprintln(stdout, "would: route through internal/runner with concurrency=10")
		}
		fmt.Fprintln(stdout, "Q-L1D-1: V1 doc-only rollback. On persistent failure consult runbooks/migration/persistent_failure.md")
		return nil
	}
	// W1.2 live dispatch — fail-closed: no --meta-dsn → refuse (no silent no-op).
	if lf.metaDSN == "" {
		return fmt.Errorf("live apply requires --meta-dsn (use --dry-run for a no-op plan)")
	}
	return runLive(migrationID, mig.Breaking, lf, stdout)
}

// planLive resolves the real fleet and prints what a live apply WOULD do.
//
// Read-only by construction: it opens the meta pool, reads `reality_registry`,
// narrows by `--reality`, and returns. It never constructs an Applier and never
// reaches a per-reality database.
//
// `A2`. Until now `--dry-run` never opened a database: it printed a route and
// stopped, so it could not name a reality, say which were behind, or be used to
// ASK for authorisation. "Dry-run first, on one reality" was not expressible,
// and an operator's only way to learn what a migration would do was to run it.
func planLive(migrationID string, breaking bool, lf liveFlags, stdout *os.File) error {
	ctx := context.Background()

	metaPool, err := pgxpool.New(ctx, lf.metaDSN)
	if err != nil {
		return fmt.Errorf("meta pool: %w", err)
	}
	defer metaPool.Close()

	fleet, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("resolve fleet: %w", err)
	}
	if len(fleet) == 0 {
		fmt.Fprintln(stdout, "no active realities to migrate")
		return nil
	}
	selected, err := selectFleet(fleet, lf.reality)
	if err != nil {
		return err
	}

	route := "internal/runner with concurrency=10"
	if breaking {
		route = "internal/canary (1 reality first, verification gate, fanout)"
	}
	fmt.Fprintln(stdout, "PLAN (nothing is written)")
	fmt.Fprintf(stdout, "  route          : %s\n", route)
	fmt.Fprintf(stdout, "  drainable fleet: %d\n", len(fleet))
	fmt.Fprintf(stdout, "  would apply to : %d\n", len(selected))
	for _, r := range selected {
		fmt.Fprintf(stdout, "    %s  %s @ %s\n", r.ID, r.DBName, r.DBHost)
	}
	fmt.Fprintf(stdout, "  migration      : %s\n", migrationID)
	fmt.Fprintln(stdout, "Q-L1D-1: V1 doc-only rollback. On persistent failure consult runbooks/migration/persistent_failure.md")
	return nil
}

// selectFleet narrows `fleet` to the comma-separated ids in `want`.
//
// An empty selector means the WHOLE fleet — the previous behaviour, unchanged.
//
// AN ID THAT IS NOT IN THE FLEET IS A REFUSAL. The alternative is a silent
// narrowing: a mistyped uuid would produce an empty selection, the caller would
// print "no active realities to migrate", exit 0, and an operator would believe
// a migration had been applied to a reality it never touched. That is the same
// fail-closed reasoning the `--meta-dsn` check already states one function up.
func selectFleet(fleet []realityreg.Reality, want string) ([]realityreg.Reality, error) {
	want = strings.TrimSpace(want)
	if want == "" {
		return fleet, nil
	}
	have := make(map[string]realityreg.Reality, len(fleet))
	for _, r := range fleet {
		have[r.ID] = r
	}
	var out []realityreg.Reality
	seen := map[string]bool{}
	for _, id := range strings.Split(want, ",") {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		r, ok := have[id]
		if !ok {
			return nil, fmt.Errorf(
				"--reality %s is not in the drainable fleet of %d; refusing rather than "+
					"narrowing to nothing (a typo would otherwise read as a clean no-op)",
				id, len(fleet))
		}
		if seen[id] {
			continue
		}
		seen[id] = true
		out = append(out, r)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("--reality named no ids")
	}
	return out, nil
}

// runLive wires the real collaborators (contracts/meta MetaWrite, the per-
// reality pgx Applier, contracts/realityreg DSN resolver) and dispatches.
func runLive(migrationID string, breaking bool, lf liveFlags, stdout *os.File) error {
	ctx := context.Background()

	metaPool, err := pgxpool.New(ctx, lf.metaDSN)
	if err != nil {
		return fmt.Errorf("meta pool: %w", err)
	}
	defer metaPool.Close()

	allow, err := meta.LoadAllowlist(lf.allowlist)
	if err != nil {
		return fmt.Errorf("load allowlist %s: %w", lf.allowlist, err)
	}

	fleet, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("resolve fleet: %w", err)
	}
	if len(fleet) == 0 {
		fmt.Fprintln(stdout, "no active realities to migrate")
		return nil
	}

	// `A2` — narrow to named realities, so one lagging reality can be brought
	// forward without touching the other nine.
	//
	// The fleet was ALL-OR-NOTHING until now, and that is why this exists: a
	// board that wanted "dry-run first, on one reality" could not express it,
	// and the two alternatives were both worse. Editing `reality_registry.status`
	// to narrow the fleet is a live write to the meta database made in order to
	// make a live write safer; a fleet-wide first attempt is the caution
	// abandoned.
	selected, err := selectFleet(fleet, lf.reality)
	if err != nil {
		return err
	}
	if len(selected) != len(fleet) {
		fmt.Fprintf(stdout, "fleet narrowed by --reality: %d of %d\n", len(selected), len(fleet))
	}
	fleet = selected

	hostOverride, err := realityreg.ParseHostOverride(lf.hostOverride)
	if err != nil {
		return err
	}
	dsn := realityreg.DSNConfig{
		User:         lf.pgUser,
		Password:     lf.pgPass,
		Port:         lf.pgPort,
		SSLMode:      lf.ssl,
		HostOverride: hostOverride,
	}
	applier := live.NewSQLApplier(dsn, fleet, lf.sqlDir)
	defer applier.Close()

	collab := live.NewMetaCollaborator(metaPool, allow, uuid.New())

	out, err := live.RunMigration(ctx, live.Options{
		MigrationID: migrationID,
		Breaking:    breaking,
		Fleet:       fleet,
		Applier:     applier,
		Auditor:     collab,
		StateWriter: collab,
		Aborter:     collab,
		Concurrency: lf.concurrency,
		// Verifier nil → fail-closed for breaking migrations (no V1 suite).
	})
	if err != nil {
		return fmt.Errorf("dispatch: %w", err)
	}

	if out.Aborted {
		fmt.Fprintf(stdout, "ABORTED: %s (canary=%s) — fan-out not attempted\n", out.AbortReason, out.CanaryReality)
		return fmt.Errorf("migration aborted: %s", out.AbortReason)
	}
	applied, failed := 0, 0
	for _, r := range out.Results {
		if r.Succeeded {
			applied++
		} else {
			failed++
		}
	}
	fmt.Fprintf(stdout, "done: %d applied, %d failed (fleet=%d, breaking=%v)\n", applied, failed, len(fleet), breaking)
	if failed > 0 {
		return fmt.Errorf("%d realities failed migration", failed)
	}
	return nil
}
