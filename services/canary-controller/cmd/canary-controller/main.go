// canary-controller — L7.K.4 (RAID cycle 38). SR05 §12AH.4 canary rollout
// executor + auto-abort. Q-L7K-1 LOCKED: GitHub Actions V1 (no ArgoCD).
//
// The control loop reads the in-progress major deploy from deploy_audit,
// observes the cohort-scoped SLI, and advances or aborts per the §12AH.4 table
// (10min/30min/2h/4h windows; auto-abort on cohort SLI burn > 2× baseline).
//
// V1 SKELETON: main() validates config + exposes /healthz + /readyz + a metrics
// stub and runs the tick loop against interface-bound dependencies. The LIVE
// bindings (deploy_audit via contracts/meta, Prometheus SLI query, GitHub
// Actions repository_dispatch executor, PagerDuty pager) land when the deploy
// pipeline first goes live — tracked as D-CANARY-LIVE-WIRING. The canary state
// machine (internal/canary + internal/controller, fully unit-tested) is the
// load-bearing piece.
//
// All credentials (GITHUB_TOKEN, PAGERDUTY_INTEGRATION_KEY, PROM_URL) are
// env-var sourced; the service fails to start with --require-providers when
// they are missing. NO secrets are ever hardcoded.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"
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

	// Credential presence check (env-var only; never embedded).
	missing := missingCreds()
	if len(missing) > 0 {
		if *requireProviders {
			log.Fatalf("[canary-controller] required credentials missing (env-var only, fail closed): %v", missing)
		}
		log.Printf("[canary-controller] WARNING: credentials missing %v; controller idle until wired (D-CANARY-LIVE-WIRING)", missing)
	}

	if *dryRun {
		log.Printf("[canary-controller] dry-run OK (Q-L7K-1 GitHub Actions V1; tick=%s)", *tick)
		return
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if len(missingCreds()) > 0 {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprintln(w, "not ready: deploy/SLI/pager creds missing")
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})
	// Metrics stub: lw_canary_sli_cohort + lw_canary_stage are emitted by the
	// live wiring (D-CANARY-LIVE-WIRING); the endpoint exists so Prometheus
	// scrape config can target it from day one.
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintln(w, "# canary-controller metrics (live wiring: D-CANARY-LIVE-WIRING)")
	})

	srv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go runLoop(context.Background(), *tick)

	log.Printf("[canary-controller] listening on %s (tick=%s)", *addr, *tick)
	if err := srv.ListenAndServe(); err != nil {
		log.Fatalf("[canary-controller] http server: %v", err)
	}
}

// runLoop ticks the controller. V1 has no live dependencies wired, so it logs a
// heartbeat; the real loop constructs controller.New(store, sli, exec, pager,
// time.Now) and calls Tick when D-CANARY-LIVE-WIRING lands.
func runLoop(ctx context.Context, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			// No-op until live deps are wired (D-CANARY-LIVE-WIRING).
		}
	}
}

// missingCreds returns the env-var names that are required for live operation
// but currently unset.
func missingCreds() []string {
	var miss []string
	for _, k := range []string{"GITHUB_TOKEN", "PAGERDUTY_INTEGRATION_KEY", "PROM_URL"} {
		if os.Getenv(k) == "" {
			miss = append(miss, k)
		}
	}
	return miss
}

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
