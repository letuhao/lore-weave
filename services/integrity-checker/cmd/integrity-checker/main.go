// services/integrity-checker/cmd/integrity-checker — entry point for the
// L3.E daily + L3.F monthly projection integrity-checker.
//
// LOCKED Q-L3E-1: SEPARATE binary; daily + monthly are the SAME binary, the
// mode is config-driven (--config, `mode: daily|monthly`). Scheduling is
// EXTERNAL — Kubernetes CronJobs invoke this once per cadence; the process runs
// ONE sweep across all active realities and exits (no internal ticker).
//
// Run shape:
//   - No META_DATABASE_URL → skeleton mode: validate config, print banner, exit 0
//     (keeps `go build ./...` / CI smoke green without a DB).
//   - META_DATABASE_URL set + daily mode + daily_enabled → LIVE sweep: enumerate
//     active realities (meta reality_registry via contracts/realityreg), resolve
//     each shard DSN, and for each reality run pkg/live.Checker across the
//     configured tables (sample → replay-aggregate bin → byte-compare → persist
//     projection_drift_state). Exit non-zero if any reality errored.
//   - Monthly mode → the L3.F full-scan live wiring is not in this slice; logged
//   - skipped (DEFERRED 145 slice 2c remainder).
//
// Per-reality replay shells out to the world-service `replay-aggregate` binary
// (REPLAY_AGGREGATE_BIN_PATH, default "replay-aggregate" on PATH).
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/config"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/full_check"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/live"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/metrics"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/pgsource"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/replayloader"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/state_writer"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

const banner = `
[integrity-checker] L3.E + L3.F projection integrity checker
[integrity-checker] LOCKED Q-L3E-1: SEPARATE service (different ops cadence)
[integrity-checker] modes: daily (L3.E sampling) + monthly (L3.F full scan)
[integrity-checker] same binary, different cron — config-driven via mode:
`

// requiredMetrics is asserted at startup to surface metric-name drift early.
var requiredMetrics = []string{
	metrics.MetricProjectionLagSeconds,
	metrics.MetricProjectionDriftCount,
	metrics.MetricProjectionCheckDurationSeconds,
	metrics.MetricProjectionCheckRunsTotal,
}

// fullMode is the V1 degraded-mode source: always ModeFull. Real service-mode
// integration (pausing the sweep when the reality is degraded) is a follow-up.
type fullMode struct{}

func (fullMode) Mode() lifecycle.ServiceMode { return lifecycle.ModeFull }

func main() {
	configPath := flag.String("config", "", "path to integrity-checker config.yaml (empty = default)")
	flag.Parse()

	fmt.Print(banner)

	cfg, err := config.LoadFile(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: load config: %v\n", err)
		os.Exit(2)
	}
	if err := cfg.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: validate config: %v\n", err)
		os.Exit(2)
	}
	for _, m := range requiredMetrics {
		if m == "" {
			fmt.Fprintln(os.Stderr, "[integrity-checker] FATAL: empty metric name (constants drifted)")
			os.Exit(2)
		}
	}
	fmt.Printf("[integrity-checker] mode=%s tables=%d daily_enabled=%v monthly_enabled=%v\n",
		cfg.Mode, len(cfg.Tables), cfg.DailyEnabled, cfg.MonthlyEnabled)

	// No meta DB → skeleton mode (config validated; nothing to sweep).
	if os.Getenv("META_DATABASE_URL") == "" {
		fmt.Println("[integrity-checker] META_DATABASE_URL unset — skeleton OK, exit 0 (no live sweep)")
		return
	}

	// Signal-aware context so a killed pod stops cleanly mid-sweep.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	os.Exit(run(ctx, cfg))
}

// run executes one live sweep across active realities in the configured mode
// (daily sampling = L3.E, or monthly full-scan = L3.F). Returns the process exit
// code (0 = all realities checked; 3 = one or more errored).
func run(ctx context.Context, cfg config.Config) int {
	switch cfg.Mode {
	case types.CheckModeDaily:
		if !cfg.DailyEnabled {
			fmt.Println("[integrity-checker] daily_enabled=false — dark mode, exit 0")
			return 0
		}
	case types.CheckModeMonthly:
		if !cfg.MonthlyEnabled {
			fmt.Println("[integrity-checker] monthly_enabled=false — dark mode, exit 0")
			return 0
		}
	}

	metaPool, err := pgxpool.New(ctx, os.Getenv("META_DATABASE_URL"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: meta DB connect: %v\n", err)
		return 2
	}
	defer metaPool.Close()

	realities, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: enumerate realities: %v\n", err)
		return 2
	}
	dsnCfg, err := shardDSNConfig()
	if err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: shard DSN config: %v\n", err)
		return 2
	}
	binPath := os.Getenv("REPLAY_AGGREGATE_BIN_PATH")
	if binPath == "" {
		binPath = "replay-aggregate"
	}
	loader, err := replayloader.New(replayloader.ExecRunner{BinPath: binPath})
	if err != nil {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: replay loader: %v\n", err)
		return 2
	}

	fmt.Printf("[integrity-checker] %s sweep: %d active realit(ies)\n", cfg.Mode, len(realities))
	failed := 0
	for _, r := range realities {
		if ctx.Err() != nil {
			fmt.Fprintln(os.Stderr, "[integrity-checker] cancelled — stopping sweep")
			failed++
			break
		}
		var rerr error
		switch cfg.Mode {
		case types.CheckModeMonthly:
			rerr = checkRealityMonthly(ctx, r, dsnCfg, loader, cfg.Tables, cfg.FullCheckIntervalDays)
		default:
			rerr = checkReality(ctx, r, dsnCfg, loader, cfg.Tables)
		}
		if rerr != nil {
			fmt.Fprintf(os.Stderr, "[integrity-checker] reality %s ERROR: %v\n", r.ID, rerr)
			failed++
		}
	}
	if failed > 0 {
		fmt.Fprintf(os.Stderr, "[integrity-checker] sweep finished with %d reality error(s)\n", failed)
		return 3
	}
	fmt.Println("[integrity-checker] sweep OK — exit 0")
	return 0
}

// checkReality runs the daily checker against one reality's shard DB.
func checkReality(
	ctx context.Context,
	r realityreg.Reality,
	dsnCfg realityreg.DSNConfig,
	loader *replayloader.Loader,
	tables []types.TableConfig,
) error {
	rid, err := uuid.Parse(r.ID)
	if err != nil {
		return fmt.Errorf("invalid reality_id %q: %w", r.ID, err)
	}
	dsn, err := dsnCfg.DSN(r.DBHost, r.DBName)
	if err != nil {
		return fmt.Errorf("resolve shard DSN: %w", err)
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return fmt.Errorf("shard DB connect: %w", err)
	}
	defer pool.Close()

	sampler, err := pgsource.New(pool)
	if err != nil {
		return err
	}
	writer, err := state_writer.New(state_writer.Config{
		Persister: state_writer.NewPgPersister(pool),
		Clock:     time.Now,
	})
	if err != nil {
		return err
	}
	checker, err := live.NewChecker(live.Config{
		Sampler:  sampler,
		Replayer: loader,
		Writer:   writer,
		Mode:     fullMode{},
		Clock:    time.Now,
	})
	if err != nil {
		return err
	}

	it, err := checker.Run(ctx, rid, dsn, tables)
	if err != nil {
		return err
	}
	if it.Skipped {
		fmt.Printf("[integrity-checker] reality %s SKIPPED (%s)\n", r.ID, it.SkipReason)
		return nil
	}
	var drift, skipped int
	for _, rep := range it.Reports {
		drift += rep.DriftCount
		skipped += rep.Skipped
	}
	fmt.Printf("[integrity-checker] reality %s: tables=%d drift=%d skipped=%d\n",
		r.ID, len(it.Reports), drift, skipped)
	return nil
}

// checkRealityMonthly runs the L3.F monthly full-scan checker against one
// reality's shard DB: the row-centric full_check.Loop walks EVERY row of each
// configured table (cursor-batched via the pgsource scanner) and renders the
// same per-row verdict the daily checker uses (live.CheckRow). Persists with the
// monthly next-sweep cadence (FullCheckIntervalDays).
func checkRealityMonthly(
	ctx context.Context,
	r realityreg.Reality,
	dsnCfg realityreg.DSNConfig,
	loader *replayloader.Loader,
	tables []types.TableConfig,
	intervalDays int,
) error {
	rid, err := uuid.Parse(r.ID)
	if err != nil {
		return fmt.Errorf("invalid reality_id %q: %w", r.ID, err)
	}
	dsn, err := dsnCfg.DSN(r.DBHost, r.DBName)
	if err != nil {
		return fmt.Errorf("resolve shard DSN: %w", err)
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return fmt.Errorf("shard DB connect: %w", err)
	}
	defer pool.Close()

	// PgRowSampler is both the daily RowSampler and the monthly CursorSource
	// (NextBatch) — monthly uses the cursor-scan half.
	src, err := pgsource.New(pool)
	if err != nil {
		return err
	}
	writer, err := state_writer.New(state_writer.Config{
		Persister: state_writer.NewPgPersister(pool),
		Clock:     time.Now,
	})
	if err != nil {
		return err
	}
	loop, err := full_check.New(full_check.Config{
		CursorSource:          src,
		Replayer:              loader,
		StateWriter:           writer,
		Mode:                  fullMode{},
		Clock:                 time.Now,
		FullCheckIntervalDays: intervalDays,
	})
	if err != nil {
		return err
	}

	st, err := loop.Run(ctx, rid, dsn, tables)
	if err != nil {
		return err
	}
	if st.Skipped {
		fmt.Printf("[integrity-checker] reality %s SKIPPED (%s)\n", r.ID, st.SkipReason)
		return nil
	}
	var drift, skipped int
	for _, rep := range st.Reports {
		drift += rep.DriftCount
		skipped += rep.Skipped
	}
	fmt.Printf("[integrity-checker] reality %s (monthly): tables=%d drift=%d skipped=%d\n",
		r.ID, len(st.Reports), drift, skipped)
	return nil
}

// shardDSNConfig builds the per-reality shard DSN template from the SHARD_DB_*
// env (mirrors the publisher / workers). SHARD_DB_HOST_OVERRIDE remaps logical
// shard hosts to a local Postgres for dev (`*=localhost:5432`).
func shardDSNConfig() (realityreg.DSNConfig, error) {
	user, pass := os.Getenv("SHARD_DB_USER"), os.Getenv("SHARD_DB_PASSWORD")
	if user == "" || pass == "" {
		return realityreg.DSNConfig{}, fmt.Errorf("SHARD_DB_USER + SHARD_DB_PASSWORD required")
	}
	port := 0
	if p := os.Getenv("SHARD_DB_PORT"); p != "" {
		n, err := strconv.Atoi(p)
		if err != nil {
			return realityreg.DSNConfig{}, fmt.Errorf("invalid SHARD_DB_PORT %q: %w", p, err)
		}
		port = n
	}
	override, err := realityreg.ParseHostOverride(os.Getenv("SHARD_DB_HOST_OVERRIDE"))
	if err != nil {
		return realityreg.DSNConfig{}, err
	}
	return realityreg.DSNConfig{
		User:         user,
		Password:     pass,
		Port:         port,
		SSLMode:      os.Getenv("SHARD_DB_SSLMODE"),
		HostOverride: override,
	}, nil
}
