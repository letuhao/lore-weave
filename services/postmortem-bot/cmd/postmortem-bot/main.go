// postmortem-bot — L7.D.9 (RAID cycle 37). Q-L7-1 LOCKED: SEPARATE service.
//
// Triggered on IncidentClosedV1; creates docs/sre/postmortems/<id>.md from
// the SR04 template. Validates root causes against the SR4 12-enum taxonomy.
//
// V1 SKELETON: main() validates the template + enum are present + loadable and
// exposes health endpoints. The live event-stream consumer is tracked as
// D-INCIDENT-LIVE-SMOKE; the generator package (unit-tested) is load-bearing.
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"github.com/loreweave/foundation/services/postmortem-bot/internal/generator"
)

const (
	defaultTemplatePath = "docs/sre/postmortems/TEMPLATE.md"
	defaultEnumPath     = "contracts/postmortems/root_cause_enum.yaml"
	defaultOutDir       = "docs/sre/postmortems"
)

func main() {
	var (
		tmplPath = flag.String("template", envOr("LW_POSTMORTEM_TEMPLATE", defaultTemplatePath), "postmortem template path")
		enumPath = flag.String("root-cause-enum", envOr("LW_ROOT_CAUSE_ENUM", defaultEnumPath), "root cause enum path")
		addr     = flag.String("addr", envOr("LW_LISTEN", ":8093"), "listen address")
		dryRun   = flag.Bool("dry-run", false, "validate config + exit 0")
	)
	flag.Parse()

	if root := findRepoRoot(); root != "" {
		*tmplPath = resolve(root, *tmplPath)
		*enumPath = resolve(root, *enumPath)
	}

	if _, err := os.Stat(*tmplPath); err != nil {
		log.Fatalf("[postmortem-bot] template not found: %v", err)
	}
	enum, err := generator.LoadRootCauseEnum(*enumPath)
	if err != nil {
		log.Fatalf("[postmortem-bot] load root-cause enum: %v", err)
	}
	log.Printf("[postmortem-bot] loaded root-cause enum: %d classes", enum.Count())

	if *dryRun {
		log.Printf("[postmortem-bot] dry-run OK (Q-L7-1 separate service)")
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

	log.Printf("[postmortem-bot] listening on %s", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("[postmortem-bot] http server: %v", err)
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
		if _, err := os.Stat(filepath.Join(dir, "contracts", "postmortems")); err == nil {
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
