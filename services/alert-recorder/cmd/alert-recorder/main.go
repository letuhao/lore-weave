// alert-recorder — Q-L7-1 SEPARATE service from slo-budget-calculator +
// incident-bot. Receives alertmanager webhooks + persists
// `alert_outcomes` + `alert_silences` for SR2 §12AE.8 audit trail.
//
// V1 SKELETON: in-memory store. Pgx adapter binding to MetaWrite is the
// follow-up (D-ALERT-RECORDER-LIVE-WIRING).
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/loreweave/alert-recorder/internal/inbox"
	"github.com/loreweave/alert-recorder/internal/store"
)

func main() {
	var (
		addr = flag.String("addr", envOr("LW_LISTEN", ":8091"), "listen address")
	)
	flag.Parse()

	mem := store.NewMemoryStore()
	h := inbox.NewHandler(mem)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, "ready")
	})
	mux.Handle("/v1/alerts/inbox", h)
	mux.HandleFunc("/v1/alerts/silences", func(w http.ResponseWriter, r *http.Request) {
		// Silence webhook stub. Real admission-policy enforcement reads
		// infra/alertmanager/silence_admission_policy.yaml at startup and
		// validates incoming silence requests against it. Returning 200 here
		// keeps the alertmanager wire-up testable.
		w.WriteHeader(http.StatusOK)
		fmt.Fprintln(w, `{"status":"received"}`)
	})

	log.Printf("[alert-recorder] listening on %s (Q-L7-1 separate service)", *addr)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("[alert-recorder] http: %v", err)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
