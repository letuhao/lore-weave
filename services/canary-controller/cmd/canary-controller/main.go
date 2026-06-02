// canary-controller — L7.K.4 (RAID cycle 38). SR05 §12AH.4 canary rollout
// executor + auto-abort. Q-L7K-1 LOCKED: GitHub Actions V1 (no ArgoCD).
//
// The control loop reads the in-progress major deploy from deploy_audit,
// observes the cohort-scoped SLI, and advances or aborts per the §12AH.4 table
// (10min/30min/2h/4h windows; auto-abort on cohort SLI burn > 2× baseline).
//
// LIVE WIRING (064 / D-CANARY-LIVE-WIRING): main() builds the four real
// adapters from env and runs controller.Tick on the tick interval —
//   - DeployStore: pgx + contracts/meta MetaWrite() against deploy_audit
//   - SLISource:   Prometheus instant-query (lw_canary_sli_cohort)
//   - Executor:    GitHub Actions repository_dispatch (canary-promote/-rollback)
//   - Pager:       PagerDuty Events API v2
//
// The actual traffic-shift workflow + the deploy pipeline that writes major
// canary rows + the services that emit cohort SLIs are stubs until launch
// (063 / D-CANARY-LIVE-SMOKE), so the READ path is inert until they land — with
// no active canary the loop just holds. The WRITE path is NOT merely inert: the
// first stage advance / rollback issues a MetaWrite UPDATE that REQUIRES the
// app_canary_role GRANT on deploy_audit (migration 023 revokes UPDATE from
// app_service_role and only PROMISES the grant "when canary-controller ships";
// it is still unwritten — DEFERRED 064 / flagged at POST-REVIEW). Until that
// grant exists and the controller's DB role has it, a real canary row makes the
// write FAIL at runtime, not silently. When creds are missing the controller
// stays idle (serving health + metrics); --require-providers makes that fatal.
//
// All credentials (GITHUB_TOKEN, GITHUB_REPO, PAGERDUTY_INTEGRATION_KEY,
// PROM_URL, LW_META_DSN, META_ALLOWLIST_PATH) are env-var sourced; the service
// never embeds secrets and never logs their values.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
	"github.com/loreweave/foundation/services/canary-controller/internal/executor"
	"github.com/loreweave/foundation/services/canary-controller/internal/metrics"
	"github.com/loreweave/foundation/services/canary-controller/internal/pager"
	"github.com/loreweave/foundation/services/canary-controller/internal/sli"
	"github.com/loreweave/foundation/services/canary-controller/internal/store"
)

const defaultTickInterval = 30 * time.Second

func main() {
	var (
		addr             = flag.String("addr", envOr("LW_LISTEN", ":8095"), "listen address")
		tick             = flag.Duration("tick", envDur("LW_CANARY_TICK", defaultTickInterval), "control-loop tick interval")
		dryRun           = flag.Bool("dry-run", false, "validate config + exit 0")
		requireProviders = flag.Bool("require-providers", false, "fail closed if deploy/SLI/pager credentials are missing")
	)
	flag.Parse()

	m := metrics.New()

	ctrl, closeFn, err := buildController(context.Background(), m)
	if err != nil {
		if *requireProviders {
			log.Fatalf("[canary-controller] cannot wire live dependencies (fail closed): %v", err)
		}
		log.Printf("[canary-controller] WARNING: controller idle until wired (D-CANARY-LIVE-WIRING): %v", err)
	}
	defer closeFn()

	if *dryRun {
		// deps-constructed reflects env/allowlist validation + adapter
		// construction only — pgxpool.New is lazy, so this is NOT a DB/Prom/
		// GitHub reachability check.
		log.Printf("[canary-controller] dry-run OK (Q-L7K-1 GitHub Actions V1; tick=%s; deps-constructed=%t)", *tick, ctrl != nil)
		return
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if ctrl == nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprintln(w, "not ready: controller not wired (deploy/SLI/pager creds missing)")
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})
	mux.Handle("/metrics", m.Handler())

	srv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if ctrl != nil {
		go runLoop(ctx, ctrl, m, *tick)
	} else {
		log.Printf("[canary-controller] idle (no live deps); serving health + metrics only")
	}

	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()

	log.Printf("[canary-controller] listening on %s (tick=%s, wired=%t)", *addr, *tick, ctrl != nil)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("[canary-controller] http server: %v", err)
	}
}

// buildController wires the live dependencies from env. Returns (nil, noop, err)
// when any required credential/config is missing or invalid — main decides
// whether that is fatal (--require-providers) or idle. The returned func closes
// the DB pool (a no-op when unwired).
func buildController(ctx context.Context, m *metrics.Metrics) (*controller.Controller, func(), error) {
	noop := func() {}

	promURL := os.Getenv("PROM_URL")
	ghToken := os.Getenv("GITHUB_TOKEN")
	ghRepo := os.Getenv("GITHUB_REPO")
	pdKey := os.Getenv("PAGERDUTY_INTEGRATION_KEY")
	metaDSN := os.Getenv("LW_META_DSN")
	allowPath := os.Getenv("META_ALLOWLIST_PATH")

	var missing []string
	for _, kv := range []struct{ k, v string }{
		{"PROM_URL", promURL}, {"GITHUB_TOKEN", ghToken}, {"GITHUB_REPO", ghRepo},
		{"PAGERDUTY_INTEGRATION_KEY", pdKey}, {"LW_META_DSN", metaDSN}, {"META_ALLOWLIST_PATH", allowPath},
	} {
		if kv.v == "" {
			missing = append(missing, kv.k)
		}
	}
	if len(missing) > 0 {
		return nil, noop, fmt.Errorf("missing env: %v", missing)
	}

	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return nil, noop, fmt.Errorf("load allowlist: %w", err)
	}
	// Fail-fast: the audited UPDATE path writes deploy_audit AND its same-TX
	// meta_write_audit row; a misconfigured allowlist would otherwise fail-closed
	// only at the first stage advance.
	for _, tbl := range []string{"deploy_audit", "meta_write_audit"} {
		if !allow.AllowsTable(tbl) {
			return nil, noop, fmt.Errorf("allowlist %s missing required table %q", allowPath, tbl)
		}
	}

	pool, err := pgxpool.New(ctx, metaDSN)
	if err != nil {
		return nil, noop, fmt.Errorf("meta DB connect: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: sysClock{}, UUIDGen: randUUID{},
		// No Scrubber: deploy_audit is low-PII ops data (triggered_by uuid only);
		// the audited NewValues are canary_stage + a stage/at/reason history JSON.
		// No Outbox: the deploy_audit UPDATE event has no consumer in V1
		// (D-CANARY-OUTBOX-EMIT); nil-Outbox skips emission (sanctioned).
	}

	exec, err := executor.NewGitHubExecutor("", ghRepo, ghToken)
	if err != nil {
		// Post-pool error paths close the pool HERE and return `noop` (NOT
		// pool.Close) so main's `defer closeFn()` does not double-close. (pgxpool
		// Close is idempotent, but keep the discipline explicit — see main_test.)
		pool.Close()
		return nil, noop, err
	}

	deployStore := store.NewPgDeployStore(pool, cfg)
	sliSource := meteredSLI{inner: sli.NewPrometheusSource(promURL, time.Now), m: m}
	pd := pager.NewPagerDutyPager("", pdKey)

	ctrl, err := controller.New(deployStore, sliSource, exec, pd, time.Now)
	if err != nil {
		pool.Close()
		return nil, noop, err
	}
	return ctrl, pool.Close, nil
}

// runLoop ticks the controller on the interval, updating metrics from each
// TickResult. Stops on ctx cancellation.
func runLoop(ctx context.Context, ctrl *controller.Controller, m *metrics.Metrics, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			res, ok, err := ctrl.Tick(ctx)
			applyTickResult(m, res, ok, err)
			switch {
			case err != nil:
				log.Printf("[canary-controller] tick error: %v", err)
			case ok:
				log.Printf("[canary-controller] tick: deploy=%s action=%s stage=%d reason=%q",
					res.DeployID, res.Action, res.Stage, res.Reason)
			}
		}
	}
}

// applyTickResult maps one controller.Tick outcome onto the metrics. Pure (no
// I/O) so the abort-count + gauge-reset rules are unit-testable without a live
// controller.
//
//   - The abort DECISION is counted regardless of execution outcome: on an abort
//     whose rollback/mark/page FAILED, Tick returns an error but res.Action is
//     still ActionAbort, and a failed-rollback abort is the highest-signal event
//     (a stuck rollback re-aborting each tick re-increments — that honestly
//     reflects repeated abort attempts).
//   - On a transient error the live gauges are left untouched (the next clean
//     tick corrects them).
//   - No active canary, OR a terminal action (abort/complete) this tick, clears
//     the live gauges (stage -1 + observed-burn 0) so the dashboard does not keep
//     showing the stage/burn of a deploy that just ended until the next tick
//     filters the row out.
func applyTickResult(m *metrics.Metrics, res controller.TickResult, ok bool, err error) {
	if ok && res.Action == canary.ActionAbort {
		m.IncAbort()
	}
	if err != nil {
		return
	}
	if !ok || res.Action == canary.ActionAbort || res.Action == canary.ActionComplete {
		m.SetStage(-1)
		m.SetObservedBurn(0)
		return
	}
	m.SetStage(int(res.Stage))
}

// meteredSLI wraps a SLISource so each observed cohort burn lands in
// lw_canary_sli_cohort without coupling the Prometheus adapter to metrics.
type meteredSLI struct {
	inner controller.SLISource
	m     *metrics.Metrics
}

func (w meteredSLI) Observe(ctx context.Context, deployID string, stage canary.Stage) (canary.Observation, error) {
	obs, err := w.inner.Observe(ctx, deployID, stage)
	if err == nil {
		w.m.SetObservedBurn(obs.CohortBurn)
	}
	return obs, err
}

// sysClock + randUUID are the production meta.Clock / meta.UUIDGen.
type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envDur(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return fallback
}
