package api

// T2-polish-2a — Prometheus /metrics for glossary-service.
//
// Mirrors provider-registry's D-K17.2a-01 shape (same file layout,
// same init-time pre-seed, same process-local registry). The hot
// paths we instrument are the four internal endpoints knowledge-
// service hits during every chat turn or extraction job:
//
//   - /internal/books/{book_id}/select-for-context  (Mode 2/3 chat)
//   - /internal/books/{book_id}/extract-entities    (extraction bulk write)
//   - /internal/books/{book_id}/known-entities      (K13.0 anchor preload)
//   - /internal/books/{book_id}/entity-count        (K16.2 cost estimate)
//
// Operator use: `rate(glossary_service_*_total[5m])` for throughput,
// `sum by (outcome) (...)` for failure mode breakdown. Dashboards
// pre-populate because every (counter × outcome) label pair is
// instantiated at init time; no "series appears after first error"
// discovery surprise.

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Outcome labels — keep this list small and stable. Dashboards
// reference these strings directly, so renaming any value is a
// breaking operator change.
//
// Review-impl scope: only the outcomes that a handler currently
// Inc()s live here. Declaring unused outcomes (e.g. `forbidden`,
// `unauthorized`, `not_found`, `upstream_unavailable`) would pre-
// seed dead series the operator then sees as 16 permanently-zero
// labels per counter vec — a dashboard distraction. Add new
// outcomes in the same commit that introduces a call site that
// Inc()s them.
//
// Cross-service note: book-service's metrics.go uses `not_found`
// instead of `invalid_body` because its GET handlers have real
// pgx.ErrNoRows → 404 paths but no JSON body to decode. glossary-
// service is the inverse: POST `select_for_context` + `extract-
// entities` have real JSON-decode error paths but return 0 rather
// than 404 for missing books. Dashboards unioning both services
// will see partial overlap on `{outcome}`; that's intentional —
// forcing both to declare all 6 outcomes would re-introduce the
// dead-label pollution this cycle fixed.
const (
	OutcomeOK              = "ok"
	OutcomeValidationError = "validation_error"
	OutcomeInvalidBody     = "invalid_body"
	OutcomeQueryFailed     = "query_failed"
)

// metricsRegistry is process-local so Go runtime metrics don't ship
// by accident and tests can assert against a clean registry via a
// fresh Server instance. Same choice provider-registry made.
var metricsRegistry = prometheus.NewRegistry()

// SelectForContextTotal counts outcomes on /internal/books/{id}/
// select-for-context, the Mode-2/Mode-3 glossary tier. Dashboards
// pair this with knowledge-service's context-build metrics to
// localise latency or error spikes.
var SelectForContextTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "glossary_service_select_for_context_total",
		Help: "Outcomes for /internal/books/{id}/select-for-context requests.",
	},
	[]string{"outcome"},
)

// BulkExtractTotal counts outcomes on /internal/books/{id}/extract-
// entities — the per-chapter bulk entity write from knowledge-
// service's extraction runner.
var BulkExtractTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "glossary_service_bulk_extract_total",
		Help: "Outcomes for /internal/books/{id}/extract-entities bulk upsert requests.",
	},
	[]string{"outcome"},
)

// KnownEntitiesTotal counts outcomes on /internal/books/{id}/
// known-entities — the K13.0 anchor-preload endpoint. High-volume
// during extraction job startup.
var KnownEntitiesTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "glossary_service_known_entities_total",
		Help: "Outcomes for /internal/books/{id}/known-entities requests.",
	},
	[]string{"outcome"},
)

// EntityCountTotal counts outcomes on /internal/books/{id}/entity-
// count — the K16.2 cost-estimate lookup called from the extraction
// preview dialog.
var EntityCountTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "glossary_service_entity_count_total",
		Help: "Outcomes for /internal/books/{id}/entity-count requests.",
	},
	[]string{"outcome"},
)

func init() {
	metricsRegistry.MustRegister(SelectForContextTotal)
	metricsRegistry.MustRegister(BulkExtractTotal)
	metricsRegistry.MustRegister(KnownEntitiesTotal)
	metricsRegistry.MustRegister(EntityCountTotal)

	// Pre-seed every (counter × outcome) pair so the series appears
	// at zero on the first scrape. rate() queries against new series
	// return empty until the first non-zero sample lands — pre-
	// seeding removes that false "no data" window from dashboards.
	for _, cv := range []*prometheus.CounterVec{
		SelectForContextTotal, BulkExtractTotal,
		KnownEntitiesTotal, EntityCountTotal,
	} {
		for _, oc := range []string{
			OutcomeOK, OutcomeValidationError,
			OutcomeInvalidBody, OutcomeQueryFailed,
		} {
			cv.WithLabelValues(oc)
		}
	}
}

// metricsHandler serves Prometheus text format on /metrics. No auth
// — scrape is in-cluster, the route isn't exposed via the gateway.
// Same convention as every other Go service in loreweave.
func metricsHandler() http.Handler {
	return promhttp.HandlerFor(metricsRegistry, promhttp.HandlerOpts{})
}
