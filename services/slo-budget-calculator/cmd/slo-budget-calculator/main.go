// slo-budget-calculator — Q-L7-1 SEPARATE service from incident-bot +
// statuspage-updater. Reads contracts/slo/sli_definitions.yaml +
// contracts/slo/slo_targets.yaml, exposes /healthz + a JSON read API
// the alertmanager rule evaluation queries.
//
// V1 SKELETON: this main() is a scaffold. The full HTTP server with Prom
// client wiring is tracked as a follow-up deferral if/when burn-rate
// alerts need to consume budget rather than just burn ratio. The PURE
// budget package (internal/budget) is the load-bearing piece — alert
// expressions can use the recording rules directly until live wiring lands.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/loreweave/slo-budget-calculator/internal/config"
)

const (
	defaultSLIPath    = "contracts/slo/sli_definitions.yaml"
	defaultTargetPath = "contracts/slo/slo_targets.yaml"
)

func main() {
	var (
		sliPath    = flag.String("sli-config", envOr("LW_SLI_CONFIG", defaultSLIPath), "path to sli_definitions.yaml")
		targetPath = flag.String("target-config", envOr("LW_SLO_TARGET_CONFIG", defaultTargetPath), "path to slo_targets.yaml")
		addr       = flag.String("addr", envOr("LW_LISTEN", ":8090"), "listen address")
		dryRun     = flag.Bool("dry-run", false, "validate configs + exit 0; do NOT start HTTP server")
	)
	flag.Parse()

	repoRoot := findRepoRoot()
	if repoRoot != "" {
		// If a relative path resolves to nothing here but exists at repo
		// root, rewrite (so the service launches the same from any cwd).
		if !filepath.IsAbs(*sliPath) {
			cand := filepath.Join(repoRoot, *sliPath)
			if _, err := os.Stat(cand); err == nil {
				*sliPath = cand
			}
		}
		if !filepath.IsAbs(*targetPath) {
			cand := filepath.Join(repoRoot, *targetPath)
			if _, err := os.Stat(cand); err == nil {
				*targetPath = cand
			}
		}
	}

	slis, err := config.LoadSLIs(*sliPath)
	if err != nil {
		log.Fatalf("[slo-budget-calculator] load SLI registry: %v", err)
	}
	log.Printf("[slo-budget-calculator] loaded %d SLIs (expected %d)",
		len(slis.SLIs), slis.ExpectedSLICount)

	targets, err := config.LoadTargets(*targetPath)
	if err != nil {
		log.Fatalf("[slo-budget-calculator] load SLO targets: %v", err)
	}
	log.Printf("[slo-budget-calculator] loaded %d SLO targets (%d burn tiers)",
		len(targets.Targets), len(targets.BurnRateResponse))

	// Cross-check every target.sli_ref matches a declared SLI — surfaces
	// drift at startup rather than at first alert evaluation.
	sliSet := make(map[string]bool, len(slis.SLIs))
	for _, s := range slis.SLIs {
		sliSet[s.Name] = true
	}
	for _, t := range targets.Targets {
		if !sliSet[t.SLIRef] {
			log.Fatalf(
				"[slo-budget-calculator] target sli_ref=%q (tier=%s) not in SLI registry",
				t.SLIRef, t.Tier,
			)
		}
	}

	if *dryRun {
		log.Printf("[slo-budget-calculator] dry-run OK; %d SLIs × tiers = %d budgets",
			len(slis.SLIs), len(targets.Targets))
		return
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})
	mux.HandleFunc("/slo/targets", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		for _, row := range targets.Targets {
			fmt.Fprintf(w, "%s\t%s\t%v\t%s\n", row.SLIRef, row.Tier, row.Target, row.Window)
		}
	})

	log.Printf("[slo-budget-calculator] listening on %s (Q-L7-1 separate service)", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("[slo-budget-calculator] http server: %v", err)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// findRepoRoot walks up from cwd looking for a marker file. Returns ""
// if not found.
func findRepoRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, "contracts", "slo")); err == nil {
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
