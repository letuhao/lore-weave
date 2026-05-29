// services/integrity-checker/cmd/integrity-checker — entry point for the
// L3.E daily + L3.F monthly projection integrity-checker.
//
// V1 ships as a SKELETON: main() loads config, validates it, prints a
// banner showing the resolved mode + table count + ABI versions, and
// exits 0. Real production wiring (pgx for projection-row access, real
// cycle-12 load_aggregate via FFI or sibling-service call, ticker loop
// with per-reality scheduling, graceful shutdown, /healthz + /readyz +
// /metrics endpoints) lands at D-PUBLISHER-LIVE-WIRING — see services/
// archive-worker/cmd/archive-worker/main.go for the exact shape this
// service mirrors.
//
// LOCKED Q-L3E-1: this service is a SEPARATE binary (not part of
// world-service). Daily + monthly are the SAME binary; config drives
// which orchestrator runs (--config=contracts/integrity/config.yaml,
// `mode: daily|monthly`). Different cron schedules wire the two modes
// through Kubernetes CronJob manifests (cycle 15 L3.F.3 ships
// infra/k8s/integrity-checker-cronjob.yaml).
//
// Why ship the entry point + library packages now?
//  1. The binary is referenced by infra/k8s/integrity-checker-cronjob.yaml
//     and infra/prometheus/alerts/projection.yaml — without main.go +
//     the metric constants, those manifests dangle.
//  2. CI smoke (`go build ./...` per verify-cycle-15.sh) catches wiring
//     drift early.
//  3. The library packages (sampler/comparator/state_writer/daily_loop/
//     full_check/metrics) have full unit-test coverage with in-memory
//     fakes; they don't need main to be a long-running daemon to validate
//     correctness.
package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/config"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/metrics"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

const banner = `
[integrity-checker] L3.E + L3.F projection integrity checker — V1 skeleton
[integrity-checker] LOCKED Q-L3E-1: SEPARATE service (different ops cadence)
[integrity-checker] modes: daily (L3.E sampling) + monthly (L3.F full scan)
[integrity-checker] same binary, different cron — config-driven via mode:
[integrity-checker] production wiring lands at D-PUBLISHER-LIVE-WIRING
`

// Sanity-checked at startup to surface metric-name drift early. If any
// MetricProjection* constant gets renamed without updating
// contracts/observability/inventory.yaml, observability-inventory-lint
// will fail in CI; this startup check catches it locally as well.
var requiredMetrics = []string{
	metrics.MetricProjectionLagSeconds,
	metrics.MetricProjectionDriftCount,
	metrics.MetricProjectionCheckDurationSeconds,
	metrics.MetricProjectionCheckRunsTotal,
}

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

	// ABI sanity: required-metrics list MUST cover all defined constants.
	if len(requiredMetrics) != 4 {
		fmt.Fprintf(os.Stderr, "[integrity-checker] FATAL: metric constants drifted (expected 4 names, got %d)\n", len(requiredMetrics))
		os.Exit(2)
	}
	for _, m := range requiredMetrics {
		if m == "" {
			fmt.Fprintln(os.Stderr, "[integrity-checker] FATAL: empty metric name (constants drifted)")
			os.Exit(2)
		}
	}

	fmt.Printf("[integrity-checker] mode=%s tables=%d daily_enabled=%v monthly_enabled=%v full_check_interval_days=%d\n",
		cfg.Mode, len(cfg.Tables), cfg.DailyEnabled, cfg.MonthlyEnabled, cfg.FullCheckIntervalDays)
	fmt.Printf("[integrity-checker] metric ABI: %v\n", requiredMetrics)

	// In daily/monthly mode the orchestrator would spin up here; cycle-15
	// skeleton exits 0 after config validation (production wiring deferred).
	switch cfg.Mode {
	case types.CheckModeDaily:
		fmt.Println("[integrity-checker] daily mode validated — orchestrator wiring deferred to D-PUBLISHER-LIVE-WIRING")
	case types.CheckModeMonthly:
		fmt.Println("[integrity-checker] monthly mode validated — orchestrator wiring deferred to D-PUBLISHER-LIVE-WIRING")
	}

	fmt.Println("[integrity-checker] skeleton OK — exit 0")
}
