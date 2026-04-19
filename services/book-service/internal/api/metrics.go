package api

// T2-polish-2b — Prometheus /metrics for book-service.
//
// Mirrors the glossary-service / provider-registry metrics shape.
// Scope is the three internal read endpoints knowledge-service hits
// on its hot paths:
//
//   - /internal/books/{id}/projection         (ownership + metadata)
//   - /internal/books/{id}/chapters           (chapter list, K16.2 cost estimate)
//   - /internal/books/{id}/chapters/{cid}     (chapter text, D-K18.3-01 passage ingest)
//
// PATCH /internal/imports/{id} is not instrumented because it is
// low-volume and not on knowledge-service's hot path. Per the
// T2-polish-2a review-impl rule: only declare outcomes / counters
// that a call site actually uses. Add instrumentation in the same
// commit that adds the call site.
//
// Dashboards pair these with glossary-service and provider-registry
// rates to localise latency / error spikes to a specific microservice.

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Outcome labels — only declare what the handlers actually Inc(),
// not the full provider-registry set. Trimmed after the T2-polish-2a
// review caught dead-label pollution.
//
// Cross-service note: glossary-service's metrics.go uses
// `invalid_body` instead of `not_found` because its handlers have
// real JSON-decode error paths but return 0 rather than 404 for
// missing books. book-service is the inverse: `not_found` is a real
// outcome (pgx.ErrNoRows surfaces on every `/projection` lookup for
// a deleted book) but there's no JSON body to decode on a GET.
// Dashboards that union both services will see partial overlap on
// the `{outcome}` label; that's intentional — forcing both to
// declare all 6 outcomes would re-introduce the dead-label
// dashboard pollution T2-polish-2a fixed.
const (
	OutcomeOK              = "ok"
	OutcomeValidationError = "validation_error"
	OutcomeNotFound        = "not_found"
	OutcomeQueryFailed     = "query_failed"
)

// metricsRegistry is process-local so Go runtime metrics don't ship
// by accident and tests can assert against clean state via a fresh
// Server instance.
var metricsRegistry = prometheus.NewRegistry()

// ProjectionTotal counts outcomes on /internal/books/{id}/projection.
// Hit by glossary-service + knowledge-service on every ownership check.
var ProjectionTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "book_service_projection_total",
		Help: "Outcomes for /internal/books/{id}/projection requests.",
	},
	[]string{"outcome"},
)

// ChaptersListTotal counts outcomes on /internal/books/{id}/chapters.
// Used by the knowledge-service K16.2 cost-estimate path (optionally
// with from_sort/to_sort range filtering from T2-close-6).
var ChaptersListTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "book_service_chapters_list_total",
		Help: "Outcomes for /internal/books/{id}/chapters requests.",
	},
	[]string{"outcome"},
)

// ChapterFetchTotal counts outcomes on /internal/books/{id}/chapters/
// {chapter_id}. Called by the D-K18.3-01 passage ingest path once per
// `chapter.saved` event — high-volume during bulk imports.
var ChapterFetchTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "book_service_chapter_fetch_total",
		Help: "Outcomes for /internal/books/{id}/chapters/{chapter_id} requests.",
	},
	[]string{"outcome"},
)

func init() {
	metricsRegistry.MustRegister(ProjectionTotal)
	metricsRegistry.MustRegister(ChaptersListTotal)
	metricsRegistry.MustRegister(ChapterFetchTotal)

	// Pre-seed every (counter × outcome) pair so the series appears
	// at zero on first scrape. rate() queries against new series
	// return empty until the first non-zero sample lands — pre-
	// seeding removes that false "no data" window from dashboards.
	for _, cv := range []*prometheus.CounterVec{
		ProjectionTotal, ChaptersListTotal, ChapterFetchTotal,
	} {
		for _, oc := range []string{
			OutcomeOK, OutcomeValidationError,
			OutcomeNotFound, OutcomeQueryFailed,
		} {
			cv.WithLabelValues(oc)
		}
	}
}

// metricsHandler serves the Prometheus text format on /metrics. No
// auth — scrape is in-cluster only. Same convention as every other
// Go service in loreweave.
func metricsHandler() http.Handler {
	return promhttp.HandlerFor(metricsRegistry, promhttp.HandlerOpts{})
}
