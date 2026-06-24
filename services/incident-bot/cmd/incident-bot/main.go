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
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/incident-bot/internal/breach"
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

	// GDPR Art.33 breach intake (072): an authenticated POST /internal/breach starts
	// the 72h clock, emits the breach lifecycle as events, and monitors the deadline.
	//
	// Transport (108 D-BREACH-BROKER-EMITTER): when REDIS_URL is set the events go to
	// a durable Redis stream (the 106 delivery consumer reads it); else the 072 stdout
	// StructuredEmitter (dev/no-broker). Durability (107 D-BREACH-DURABLE-STORE): with
	// the Redis broker, the monitor is REBUILT on boot by replaying the stream, so the
	// 72h reminders survive a restart — incident-bot still holds no DB (Q-L7-1).
	breachStream := envOr("LW_BREACH_STREAM", breach.DefaultBreachStream)
	var emitter breach.EventEmitter
	var monitor *breach.Monitor
	if redisURL := os.Getenv("REDIS_URL"); redisURL != "" {
		if re, mon, serr := setupRedisBreach(redisURL, breachStream); serr != nil {
			// DEGRADE, do NOT crash: incident-bot is multi-responsibility (severity /
			// statuspage / war-room / health). A breach-broker boot failure must not
			// take the whole service down — fall back to the in-process path so the
			// rest of incident-bot still boots (and the operator sees the WARNING).
			log.Printf("[incident-bot] WARNING: Redis breach broker unavailable (%v) — DEGRADING to stdout emitter + in-process monitor (reminders will NOT survive restart until Redis is reachable)", serr)
			emitter = breach.NewStructuredEmitter(os.Stdout)
			monitor = breach.NewMonitor(emitter, time.Now, time.Minute)
		} else {
			emitter, monitor = re, mon
		}
	} else {
		emitter = breach.NewStructuredEmitter(os.Stdout)
		monitor = breach.NewMonitor(emitter, time.Now, time.Minute)
		log.Printf("[incident-bot] GDPR breach: stdout emitter; monitor IN-PROCESS ONLY (set REDIS_URL for the durable broker + restart-replay)")
	}
	go monitor.Run(context.Background())
	internalToken := os.Getenv("INCIDENT_INTERNAL_TOKEN")
	if internalToken == "" {
		log.Printf("[incident-bot] WARNING: INCIDENT_INTERNAL_TOKEN unset — POST /internal/breach intake DISABLED (fail-closed)")
	}

	mux := http.NewServeMux()
	mux.Handle("/internal/breach", breach.NewHandler(emitter, monitor, time.Now, internalToken, 0))
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

// setupRedisBreach builds the Redis-backed breach emitter (108) + a deadline monitor
// rebuilt from the durable stream (107). It returns an error (rather than crashing) so
// a boot-time Redis failure DEGRADES breach to the in-process path instead of taking
// down the whole multi-responsibility service. The redis client lives for the process
// (closed by exit); it is closed here only on the error paths.
func setupRedisBreach(redisURL, stream string) (breach.EventEmitter, *breach.Monitor, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("REDIS_URL parse: %w", err)
	}
	rdb := redis.NewClient(opts)
	bootCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := rdb.Ping(bootCtx).Err(); err != nil {
		_ = rdb.Close()
		return nil, nil, fmt.Errorf("redis ping: %w", err)
	}
	em, err := breach.NewRedisEmitter(rdb, stream, breach.DefaultTrimHorizon, time.Now)
	if err != nil {
		_ = rdb.Close()
		return nil, nil, err
	}
	recs, err := breach.ReplayOpenBreaches(bootCtx, rdb, stream)
	if err != nil {
		_ = rdb.Close()
		return nil, nil, fmt.Errorf("replay: %w", err)
	}
	mon := breach.NewMonitor(em, time.Now, time.Minute)
	for _, rec := range recs {
		mon.Track(rec)
	}
	log.Printf("[incident-bot] GDPR breach: Redis broker stream %q; replayed %d open breach(es) into the deadline monitor (durable across restart)", stream, len(recs))
	return em, mon, nil
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
