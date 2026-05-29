// incident-bot — L7.D.1 (RAID cycle 37). Q-L7-1 LOCKED: SEPARATE service
// from statuspage-updater + postmortem-bot + slo-budget-calculator.
//
// Responsibilities (SR02 §12AE):
//   - classify an inbound alert/declaration to a severity (severity_classifier)
//   - create the war-room channel + invite IC/fixer/teams (war_room)
//   - decide + emit the status-page comms obligation (statuspage)
//   - drive the GDPR Art.33 72h flow for personal-data breaches (gdpr_breach_flow)
//   - track IC role separation + decision log (ic_role)
//
// V1 SKELETON: this main() is the wiring scaffold + config validation +
// health endpoints. The live alert ingress (Alertmanager webhook) + live
// Slack/Statuspage round-trips are tracked as D-INCIDENT-LIVE-SMOKE; the
// load-bearing decision logic lives in the unit-tested internal packages.
//
// No secrets are hardcoded. Provider credentials (SLACK_BOT_TOKEN,
// STATUSPAGE_API_KEY, PAGERDUTY_INTEGRATION_KEY_SEV0) are env-var sourced;
// the corresponding subsystem is disabled (not crashed) if its credential is
// absent in dry-run, but a non-dry-run start with --require-providers fails
// closed if any required credential is missing.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/loreweave/foundation/contracts/incidents"
)

const defaultMatrixPath = "contracts/incidents/severity_matrix.yaml"

func main() {
	var (
		matrixPath       = flag.String("severity-matrix", envOr("LW_SEVERITY_MATRIX", defaultMatrixPath), "path to severity_matrix.yaml")
		addr             = flag.String("addr", envOr("LW_LISTEN", ":8092"), "listen address")
		dryRun           = flag.Bool("dry-run", false, "validate config + exit 0; do NOT start HTTP server")
		requireProviders = flag.Bool("require-providers", false, "fail closed if any provider credential env var is missing")
	)
	flag.Parse()

	if root := findRepoRoot(); root != "" && !filepath.IsAbs(*matrixPath) {
		if cand := filepath.Join(root, *matrixPath); fileExists(cand) {
			*matrixPath = cand
		}
	}

	matrix, err := incidents.LoadSeverityMatrix(*matrixPath)
	if err != nil {
		log.Fatalf("[incident-bot] load severity matrix: %v", err)
	}
	log.Printf("[incident-bot] loaded severity matrix: %d severities", len(matrix.Severities))

	// Provider credential presence check (fail-closed only when required).
	missing := missingProviderCreds()
	if len(missing) > 0 {
		if *requireProviders {
			log.Fatalf("[incident-bot] missing required provider credentials: %v (env-var only — fail closed)", missing)
		}
		log.Printf("[incident-bot] WARNING: provider creds missing %v; those subsystems disabled", missing)
	}

	if *dryRun {
		log.Printf("[incident-bot] dry-run OK (Q-L7-1 separate service)")
		return
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if len(missingProviderCreds()) > 0 {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprintln(w, "not ready: provider creds missing")
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})

	log.Printf("[incident-bot] listening on %s", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("[incident-bot] http server: %v", err)
	}
}

// missingProviderCreds lists which provider credential env vars are unset.
func missingProviderCreds() []string {
	required := []string{"SLACK_BOT_TOKEN", "STATUSPAGE_API_KEY", "PAGERDUTY_INTEGRATION_KEY_SEV0"}
	var missing []string
	for _, k := range required {
		if os.Getenv(k) == "" {
			missing = append(missing, k)
		}
	}
	return missing
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func findRepoRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for i := 0; i < 8; i++ {
		if fileExists(filepath.Join(dir, "contracts", "incidents")) {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return ""
		}
		dir = parent
	}
	return ""
}
