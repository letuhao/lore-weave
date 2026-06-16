// statuspage-updater — L7.L.3 (RAID cycle 37). Q-L7-1 LOCKED: SEPARATE
// service from incident-bot + postmortem-bot.
//
// Listens to incident events (the shared contracts/incidents wire shapes
// incident-bot emits) and auto-updates the public status page (Statuspage.io,
// Q-L7L-1). Acceptance: status-page entry within 30s of declaration.
//
// V1 SKELETON: main() validates config + credentials + exposes health. The
// live event-stream consumer + live Statuspage.io round-trip are tracked as
// D-STATUSPAGE-LIVE-SMOKE; the updater package (unit-tested) is load-bearing.
//
// Credentials (STATUSPAGE_API_KEY, STATUSPAGE_PAGE_ID) are env-var sourced;
// the service fails to start with --require-providers if they are missing.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/loreweave/foundation/services/statuspage-updater/internal/config"
)

const (
	defaultComponentsPath = "infra/statuspage/components.yaml"
	defaultBannerPath     = "infra/statuspage/banner-config.yaml"
)

func main() {
	var (
		componentsPath   = flag.String("components", envOr("LW_STATUSPAGE_COMPONENTS", defaultComponentsPath), "components.yaml path")
		bannerPath       = flag.String("banner-config", envOr("LW_STATUSPAGE_BANNER", defaultBannerPath), "banner-config.yaml path")
		addr             = flag.String("addr", envOr("LW_LISTEN", ":8094"), "listen address")
		dryRun           = flag.Bool("dry-run", false, "validate config + exit 0")
		requireProviders = flag.Bool("require-providers", false, "fail closed if Statuspage.io credentials are missing")
	)
	flag.Parse()

	if root := findRepoRoot(); root != "" {
		*componentsPath = resolve(root, *componentsPath)
		*bannerPath = resolve(root, *bannerPath)
	}

	comps, err := config.LoadComponents(*componentsPath)
	if err != nil {
		log.Fatalf("[statuspage-updater] load components: %v", err)
	}
	banner, err := config.LoadBannerConfig(*bannerPath)
	if err != nil {
		log.Fatalf("[statuspage-updater] load banner config: %v", err)
	}
	log.Printf("[statuspage-updater] loaded %d components + %d-row banner policy", len(comps.Components), len(banner.BannerPolicy))

	credsMissing := os.Getenv("STATUSPAGE_API_KEY") == "" || os.Getenv("STATUSPAGE_PAGE_ID") == ""
	if credsMissing {
		if *requireProviders {
			log.Fatalf("[statuspage-updater] STATUSPAGE_API_KEY + STATUSPAGE_PAGE_ID required (env-var only, fail closed)")
		}
		log.Printf("[statuspage-updater] WARNING: Statuspage.io creds missing; updater disabled")
	}

	if *dryRun {
		log.Printf("[statuspage-updater] dry-run OK (Q-L7-1 separate service, Q-L7L-1 Statuspage.io)")
		return
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if os.Getenv("STATUSPAGE_API_KEY") == "" || os.Getenv("STATUSPAGE_PAGE_ID") == "" {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprintln(w, "not ready: statuspage creds missing")
			return
		}
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})

	log.Printf("[statuspage-updater] listening on %s", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("[statuspage-updater] http server: %v", err)
	}
}

func resolve(root, p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	cand := filepath.Join(root, p)
	if _, err := os.Stat(cand); err == nil {
		return cand
	}
	return p
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func findRepoRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, "infra", "statuspage")); err == nil {
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
