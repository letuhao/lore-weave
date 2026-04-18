package api

// D-K17.2a-01 — Prometheus metrics for provider-registry.
//
// Scope: outcome counters on the hot proxy + invoke paths. The call
// sites increment via the small API below so adding a new outcome
// is one constant and one call-site change.
//
// This is the service's first metrics surface — the /metrics route
// is also registered here so ops can scrape even before an adapter
// or dashboard exists.

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Outcome labels used on the proxy + invoke + embed counters. Keep
// the list small and stable — dashboard queries reference these by
// string.
const (
	OutcomeOK                = "ok"
	OutcomeInvalidJSON       = "invalid_json"
	OutcomeTooLarge          = "too_large"
	OutcomeEmptyModel        = "empty_model"
	OutcomeMissingCredential = "missing_credential"
	OutcomeDecryptFailed     = "decrypt_failed"
	OutcomeModelNotFound     = "model_not_found"
	OutcomeQueryFailed       = "query_failed"
	OutcomeValidationError   = "validation_error"
	OutcomeProviderError     = "provider_error"
	OutcomeTimeout           = "timeout"
	OutcomeAuthFailed        = "auth_failed"
)

// registry is a process-local CollectorRegistry so we don't ship
// the default Go process metrics by accident, and so test code can
// reset state via a new Server instance. Keep it package-level; the
// promhttp handler below references it directly.
var metricsRegistry = prometheus.NewRegistry()

// ProxyRequestsTotal counts outcomes on the transparent proxy path
// (`doProxy` callers). An outcome change without a corresponding
// increment here would be invisible to dashboards — the K17.2a
// review called that out explicitly.
var ProxyRequestsTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "provider_registry_proxy_requests_total",
		Help: "Outcomes for proxy requests through provider-registry.",
	},
	[]string{"outcome"},
)

// InvokeRequestsTotal mirrors the structure for the /invoke endpoint
// (public invocation) and /internal/invoke (service-to-service).
var InvokeRequestsTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "provider_registry_invoke_requests_total",
		Help: "Outcomes for invokeModel / internalInvokeModel requests.",
	},
	[]string{"outcome"},
)

// EmbedRequestsTotal for the /internal/embed endpoint.
var EmbedRequestsTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "provider_registry_embed_requests_total",
		Help: "Outcomes for internalEmbed requests.",
	},
	[]string{"outcome"},
)

// VerifyRequestsTotal for the /v1/model-registry/user-models/{id}/verify path.
var VerifyRequestsTotal = prometheus.NewCounterVec(
	prometheus.CounterOpts{
		Name: "provider_registry_verify_requests_total",
		Help: "Outcomes for user-model verification requests.",
	},
	[]string{"outcome"},
)

func init() {
	metricsRegistry.MustRegister(ProxyRequestsTotal)
	metricsRegistry.MustRegister(InvokeRequestsTotal)
	metricsRegistry.MustRegister(EmbedRequestsTotal)
	metricsRegistry.MustRegister(VerifyRequestsTotal)

	// Pre-seed all outcome labels so zero counters show up on first
	// scrape. Dashboards like to compute `rate()` immediately without
	// waiting for the first non-zero increment to instantiate the
	// series. Pre-seeding on a handful of known outcomes is cheap
	// and matches the knowledge-service pattern.
	for _, cv := range []*prometheus.CounterVec{
		ProxyRequestsTotal, InvokeRequestsTotal,
		EmbedRequestsTotal, VerifyRequestsTotal,
	} {
		for _, oc := range []string{
			OutcomeOK, OutcomeInvalidJSON, OutcomeTooLarge,
			OutcomeEmptyModel, OutcomeMissingCredential,
			OutcomeDecryptFailed, OutcomeModelNotFound,
			OutcomeQueryFailed, OutcomeValidationError,
			OutcomeProviderError, OutcomeTimeout, OutcomeAuthFailed,
		} {
			cv.WithLabelValues(oc)
		}
	}
}

// metricsHandler serves the Prometheus text format on /metrics.
// No auth — same convention as every other Go service's /metrics.
// Scrapers run inside the cluster; the route is not exposed via the
// gateway.
func metricsHandler() http.Handler {
	return promhttp.HandlerFor(metricsRegistry, promhttp.HandlerOpts{})
}
