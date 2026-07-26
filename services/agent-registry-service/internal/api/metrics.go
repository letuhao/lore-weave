package api

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Prometheus metrics (REG-X-03). Unauthed /metrics, in-cluster scrape only —
// same convention as every other Go service.
var (
	registryWrites = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "agent_registry_writes_total",
			Help: "Registry mutation count by kind and action.",
		},
		[]string{"kind", "action"},
	)
	catalogResolveSeconds = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "agent_registry_catalog_resolve_seconds",
			Help:    "effective-catalog resolution latency.",
			Buckets: prometheus.DefBuckets,
		},
	)
)

func init() {
	prometheus.MustRegister(registryWrites, catalogResolveSeconds)
}

func metricsHandler() http.Handler {
	return promhttp.Handler()
}
