// services/migration-orchestrator/cmd/migrate-drill — W1.2 live drill.
//
// Exercises the PRODUCTION migrate wiring (pkg/live: pgx SQLApplier + DSN
// resolver + MetaWrite-backed audit/state) against the real scale rig
// (meta-pg + pg-shard-0). Same flow the `migrate` CLI runs — this drives
// live.RunMigration directly so it can assert on the real meta tables.
//
// Modes:
//
//	apply  Non-breaking GOOD migration over the fleet → every reality applied,
//	       instance_schema_migrations marked (failure_reason NULL), one
//	       migration_succeeded per reality in reality_migration_audit, and the
//	       I8 audit present (meta_write_audit gained rows for BOTH meta tables).
//	abort  Breaking BROKEN migration → the canary apply fails → the orchestrator
//	       aborts (canary_apply_failed) → fan-out is NEVER attempted: 0 fanout
//	       migration_started, N-1 migration_aborted rows. I8 audit present.
//	bite   The buggy flow that ignores the canary result and fans out anyway →
//	       N-1 fanout migration_started rows appear → proves the abort guard in
//	       `apply`/`abort` is non-vacuous (without it, fan-out happens).
//	smoke  apply → abort → bite.
//
// Verdict: 0 PASS · 1 FAIL · 2 NOTRUN(setup). Re-runnable (resets each run).
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/live"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/runner"
)

const (
	shardHostLogical = "pg-shard-0.internal"
	dbPrefix         = "w1m_"
	goodSQL          = `CREATE TABLE IF NOT EXISTS w1d_probe (id int PRIMARY KEY)`
	badSQL           = `CREATE TABLE w1d_probe (@@@ deliberately invalid @@@)`
)

var (
	metaDSN      = "postgres://foundation:foundation@127.0.0.1:55510/w1_migrate?sslmode=disable"
	shardAdmin   = "postgres://foundation:foundation@127.0.0.1:55511/foundation?sslmode=disable"
	shardOverPP  = "127.0.0.1:55511"
	allowlist    = "contracts/meta/events_allowlist.yaml"
	numRealities = 5
)

func main() {
	mode := flag.String("mode", "smoke", "apply | abort | bite | smoke")
	flag.StringVar(&metaDSN, "meta-dsn", metaDSN, "meta DB DSN")
	flag.StringVar(&shardAdmin, "shard-admin-dsn", shardAdmin, "shard-0 admin DSN (CREATE DATABASE)")
	flag.StringVar(&shardOverPP, "shard-hostport", shardOverPP, "shard-0 host:port for the DSN resolver")
	flag.StringVar(&allowlist, "allowlist", allowlist, "events allowlist path")
	flag.IntVar(&numRealities, "realities", numRealities, "fleet size")
	flag.Parse()
	os.Exit(run(*mode))
}

func run(mode string) int {
	ctx := context.Background()
	meta1, err := pgxpool.New(ctx, metaDSN)
	if err != nil {
		return notrun("meta pool: %v", err)
	}
	defer meta1.Close()
	shard, err := pgxpool.New(ctx, shardAdmin)
	if err != nil {
		return notrun("shard admin pool: %v", err)
	}
	defer shard.Close()
	if err := meta1.Ping(ctx); err != nil {
		return notrun("meta ping: %v (scale rig up?)", err)
	}
	if err := shard.Ping(ctx); err != nil {
		return notrun("shard ping: %v (scale rig up?)", err)
	}

	switch mode {
	case "apply":
		return cmdApply(ctx, meta1, shard)
	case "abort":
		return cmdAbort(ctx, meta1, shard)
	case "bite":
		return cmdBite(ctx, meta1, shard)
	case "smoke":
		if c := cmdApply(ctx, meta1, shard); c != 0 {
			return c
		}
		if c := cmdAbort(ctx, meta1, shard); c != 0 {
			return c
		}
		return cmdBite(ctx, meta1, shard)
	default:
		return notrun("unknown mode %q", mode)
	}
}

// cmdApply — non-breaking good migration applies to the whole fleet + I8.
func cmdApply(ctx context.Context, meta1, shard *pgxpool.Pool) int {
	fleet, err := reset(ctx, meta1, shard, numRealities)
	if err != nil {
		return notrun("reset: %v", err)
	}
	dir, err := writeSQL("w1d_apply", goodSQL)
	if err != nil {
		return notrun("write sql: %v", err)
	}
	collab, applier := collaborators(meta1, fleet, dir)
	defer applier.Close()

	mwaBefore := scalar(ctx, meta1, `SELECT count(*) FROM meta_write_audit`)
	out, err := live.RunMigration(ctx, live.Options{
		MigrationID: "w1d_apply", Breaking: false, Fleet: fleet,
		Applier: applier, Auditor: collab, StateWriter: collab,
	})
	if err != nil {
		return fail("apply: RunMigration: %v", err)
	}

	applied := 0
	for _, r := range out.Results {
		if r.Succeeded {
			applied++
		}
	}
	ismApplied := scalar(ctx, meta1, `SELECT count(*) FROM instance_schema_migrations WHERE migration_id='w1d_apply' AND failure_reason IS NULL`)
	succAudit := scalar(ctx, meta1, `SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_apply' AND event_type='migration_succeeded'`)
	mwaAfter := scalar(ctx, meta1, `SELECT count(*) FROM meta_write_audit`)
	mwaIsm := scalar(ctx, meta1, `SELECT count(*) FROM meta_write_audit WHERE table_name='instance_schema_migrations'`)
	mwaAudit := scalar(ctx, meta1, `SELECT count(*) FROM meta_write_audit WHERE table_name='reality_migration_audit'`)
	probes := probeCount(ctx, fleet)

	n := int64(len(fleet))
	fmt.Printf(`{"mode":"apply","applied":%d,"ism_applied":%d,"succeeded_audit":%d,"probes":%d,"mwa_delta":%d,"mwa_ism":%d,"mwa_audit":%d}`+"\n",
		applied, ismApplied, succAudit, probes, mwaAfter-mwaBefore, mwaIsm, mwaAudit)

	if int64(applied) != n || ismApplied != n || probes != n {
		return fail("apply: expected %d applied/marked/probed, got applied=%d ism=%d probes=%d", n, applied, ismApplied, probes)
	}
	if succAudit != n {
		return fail("apply: expected %d migration_succeeded audit rows, got %d", n, succAudit)
	}
	// I8: the audit + state writes went through MetaWrite, so meta_write_audit
	// MUST have gained rows for BOTH tables (else the writes bypassed MetaWrite).
	if mwaIsm < n || mwaAudit < n {
		return fail("apply: I8 — meta_write_audit missing rows (ism=%d audit=%d, want >= %d each)", mwaIsm, mwaAudit, n)
	}
	return pass("apply: %d realities migrated through the live wiring; instance_schema_migrations marked; %d meta_write_audit rows (I8 holds for both meta tables)", n, mwaIsm+mwaAudit)
}

// cmdAbort — breaking broken migration aborts at the canary; fan-out never runs.
func cmdAbort(ctx context.Context, meta1, shard *pgxpool.Pool) int {
	fleet, err := reset(ctx, meta1, shard, numRealities)
	if err != nil {
		return notrun("reset: %v", err)
	}
	dir, err := writeSQL("w1d_abort", badSQL)
	if err != nil {
		return notrun("write sql: %v", err)
	}
	collab, applier := collaborators(meta1, fleet, dir)
	defer applier.Close()

	out, err := live.RunMigration(ctx, live.Options{
		MigrationID: "w1d_abort", Breaking: true, Fleet: fleet,
		Applier: applier, Auditor: collab, StateWriter: collab, Aborter: collab,
		Verifier: func(context.Context, string, string) (bool, string) { return true, "" }, // gate is never reached (apply fails first)
	})
	if err != nil {
		return fail("abort: RunMigration: %v", err)
	}

	// The DB run_id is a single UUID per run, so we distinguish canary vs
	// fan-out by the event mix: only the canary should ever be STARTED; the
	// rest must be ABORTED (never started), and none applied/succeeded.
	started := scalar(ctx, meta1, `SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_abort' AND event_type='migration_started'`)
	failedAudit := scalar(ctx, meta1, `SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_abort' AND event_type='migration_failed'`)
	abortedAudit := scalar(ctx, meta1, `SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_abort' AND event_type='migration_aborted'`)
	succAudit := scalar(ctx, meta1, `SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_abort' AND event_type='migration_succeeded'`)
	probes := probeCount(ctx, fleet)
	mwaAudit := scalar(ctx, meta1, `SELECT count(*) FROM meta_write_audit WHERE table_name='reality_migration_audit'`)

	n := int64(len(fleet))
	fmt.Printf(`{"mode":"abort","aborted":%t,"reason":%q,"started":%d,"failed":%d,"aborted_audit":%d,"succeeded":%d,"probes":%d,"mwa_audit":%d}`+"\n",
		out.Aborted, out.AbortReason, started, failedAudit, abortedAudit, succAudit, probes, mwaAudit)

	if !out.Aborted || out.AbortReason != "canary_apply_failed" {
		return fail("abort: expected canary_apply_failed, got aborted=%v reason=%q", out.Aborted, out.AbortReason)
	}
	// ONLY the canary was started (1). The N-1 others were aborted, never started.
	if started != 1 {
		return fail("abort: expected exactly 1 migration_started (canary only), got %d — fan-out was attempted", started)
	}
	if abortedAudit != n-1 {
		return fail("abort: expected %d migration_aborted, got %d", n-1, abortedAudit)
	}
	if succAudit != 0 || probes != 0 {
		return fail("abort: a broken migration left work behind — succeeded=%d probes=%d (want 0/0)", succAudit, probes)
	}
	if mwaAudit < started+failedAudit+abortedAudit {
		return fail("abort: I8 — meta_write_audit (%d) < audit rows written (%d) — some bypassed MetaWrite", mwaAudit, started+failedAudit+abortedAudit)
	}
	return pass("abort: canary apply failed → abort, %d realities NEVER attempted (0 fan-out, 0 probes); audit via MetaWrite (I8)", n-1)
}

// cmdBite — the buggy flow that ignores the canary result and fans out anyway.
// Proves the abort guard is non-vacuous: WITHOUT it, the rest ARE attempted.
func cmdBite(ctx context.Context, meta1, shard *pgxpool.Pool) int {
	fleet, err := reset(ctx, meta1, shard, numRealities)
	if err != nil {
		return notrun("reset: %v", err)
	}
	dir, err := writeSQL("w1d_bite", badSQL)
	if err != nil {
		return notrun("write sql: %v", err)
	}
	collab, applier := collaborators(meta1, fleet, dir)
	defer applier.Close()

	r, err := runner.New(&runner.Config{
		Concurrency: 4, Applier: applier, Auditor: collab, StateWriter: collab,
		Sleeper: runner.NewRealSleeper(),
	})
	if err != nil {
		return notrun("runner: %v", err)
	}
	ids := fleetIDs(fleet)
	canary := ids[0] // lexicographically smallest, matches the selector
	// canary (broken) — ignored
	_ = r.Run(ctx, []runner.Job{{RealityID: canary, MigrationID: "w1d_bite", RunID: "canary-w1d_bite"}})
	// fan out ANYWAY (the bug)
	var jobs []runner.Job
	for _, id := range ids[1:] {
		jobs = append(jobs, runner.Job{RealityID: id, MigrationID: "w1d_bite", RunID: "fanout-w1d_bite-" + id})
	}
	_ = r.Run(ctx, jobs)

	// Count migration_started rows for the FANOUT realities (every reality
	// except the canary). The guard's whole job is to keep this 0 on abort.
	fanoutStarted := scalar(ctx, meta1,
		`SELECT count(*) FROM reality_migration_audit WHERE migration_id='w1d_bite' AND event_type='migration_started' AND reality_id <> $1`, canary)

	n := int64(len(fleet))
	fmt.Printf(`{"mode":"bite","fanout_started":%d,"expected":%d}`+"\n", fanoutStarted, n-1)
	if fanoutStarted != n-1 {
		return fail("bite VACUOUS: the buggy ignore-canary flow did NOT fan out (started=%d, want %d) — the abort guard's check cannot fail", fanoutStarted, n-1)
	}
	return pass("bite: ignoring the canary result fanned out to all %d realities — the abort guard (apply/abort modes) is non-vacuous", n-1)
}

// ── wiring + setup helpers ───────────────────────────────────────────────────

func collaborators(meta1 *pgxpool.Pool, fleet []realityreg.Reality, sqlDir string) (*live.MetaCollaborator, *live.SQLApplier) {
	allow, err := meta.LoadAllowlist(allowlist)
	if err != nil {
		die("load allowlist %s: %v", allowlist, err)
	}
	dsn := realityreg.DSNConfig{
		User: "foundation", Password: "foundation", SSLMode: "disable",
		HostOverride: map[string]string{shardHostLogical: shardOverPP, "*": shardOverPP},
	}
	applier := live.NewSQLApplier(dsn, fleet, sqlDir)
	collab := live.NewMetaCollaborator(meta1, allow, uuid.New())
	return collab, applier
}

// reset truncates the meta tables, seeds N active realities, and (re)creates
// their per-reality DBs on the shard. Returns the fleet (from the registry).
func reset(ctx context.Context, meta1, shard *pgxpool.Pool, n int) ([]realityreg.Reality, error) {
	for _, t := range []string{"reality_migration_audit", "instance_schema_migrations", "meta_write_audit", "reality_registry"} {
		if _, err := meta1.Exec(ctx, "TRUNCATE "+t+" CASCADE"); err != nil {
			return nil, fmt.Errorf("truncate %s: %w", t, err)
		}
	}
	ids := make([]string, n)
	for i := range n {
		ids[i] = uuid.New().String()
	}
	sort.Strings(ids)
	for i, id := range ids {
		dbName := fmt.Sprintf("%s%03d", dbPrefix, i)
		if _, err := meta1.Exec(ctx, `INSERT INTO reality_registry
			(reality_id, db_host, db_name, status, locale,
			 session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
			VALUES ($1, $2, $3, 'active', 'en', 10, 10, 20, 0)`,
			id, shardHostLogical, dbName); err != nil {
			return nil, fmt.Errorf("seed registry %s: %w", id, err)
		}
		if _, err := shard.Exec(ctx, fmt.Sprintf("DROP DATABASE IF EXISTS %s WITH (FORCE)", dbName)); err != nil {
			return nil, fmt.Errorf("drop %s: %w", dbName, err)
		}
		if _, err := shard.Exec(ctx, "CREATE DATABASE "+dbName); err != nil {
			return nil, fmt.Errorf("create %s: %w", dbName, err)
		}
	}
	return realityreg.ActiveRealities(ctx, meta1)
}

func fleetIDs(fleet []realityreg.Reality) []string {
	ids := make([]string, len(fleet))
	for i, r := range fleet {
		ids[i] = r.ID
	}
	sort.Strings(ids)
	return ids
}

// writeSQL writes <migrationID>.up.sql into a fresh temp dir and returns it.
func writeSQL(migrationID, sql string) (string, error) {
	dir, err := os.MkdirTemp("", "w1-migrate-*")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dir, migrationID+".up.sql"), []byte(sql), 0o600); err != nil {
		return "", err
	}
	return dir, nil
}

// probeCount returns how many per-reality DBs have the w1d_probe table (i.e.
// the migration actually applied there). Uses a fresh pool per reality DB.
func probeCount(ctx context.Context, fleet []realityreg.Reality) int64 {
	var n int64
	for _, r := range fleet {
		dsn := fmt.Sprintf("postgres://foundation:foundation@%s/%s?sslmode=disable", shardOverPP, r.DBName)
		p, err := pgxpool.New(ctx, dsn)
		if err != nil {
			continue
		}
		var present bool
		_ = p.QueryRow(ctx, `SELECT to_regclass('w1d_probe') IS NOT NULL`).Scan(&present)
		p.Close()
		if present {
			n++
		}
	}
	return n
}

func scalar(ctx context.Context, pool *pgxpool.Pool, q string, args ...any) int64 {
	var n int64
	_ = pool.QueryRow(ctx, q, args...).Scan(&n)
	return n
}

func pass(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "PASS: "+format+"\n", a...)
	return 0
}
func fail(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "FAIL: "+format+"\n", a...)
	return 1
}
func notrun(format string, a ...any) int {
	fmt.Fprintf(os.Stderr, "NOTRUN(setup): "+format+"\n", a...)
	return 2
}
func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "migrate-drill: "+format+"\n", a...)
	os.Exit(2)
}
