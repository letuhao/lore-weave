// Package metrics is the canary-controller's Prometheus surface
// (D-CANARY-LIVE-WIRING / 064). The deploy-progress dashboard reads these four
// series. Collectors live on a process-local registry so Go runtime metrics
// don't ship by accident and tests can assert against a clean instance — the
// same convention every other loreweave Go service follows.
package metrics

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Metrics holds the canary-controller collectors.
type Metrics struct {
	registry     *prometheus.Registry
	stage        prometheus.Gauge
	observedBurn prometheus.Gauge
	abortTotal   prometheus.Counter
	freezeActive prometheus.Gauge
}

// New builds + registers the collectors. lw_canary_stage starts at -1 (no
// active canary); the rest at 0.
func New() *Metrics {
	reg := prometheus.NewRegistry()
	m := &Metrics{
		registry: reg,
		stage: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "lw_canary_stage",
			Help: "Current canary stage (0..4) of the active major deploy; -1 when none.",
		}),
		observedBurn: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "lw_canary_controller_observed_burn",
			// DISTINCT from the services' lw_canary_sli_cohort{stage,service} the
			// controller QUERIES (prometheus_source) — emitting that same family
			// here (bare, no labels) would collide with the real cohort series +
			// corrupt the deploy-progress dashboard. This is the controller's own
			// "what I last observed" diagnostic gauge.
			Help: "Last cohort SLI burn the canary-controller observed for the active canary; reset to 0 when no canary is active or the deploy ends (diagnostic; the authoritative per-cohort series is lw_canary_sli_cohort{stage,service}).",
		}),
		abortTotal: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "lw_canary_abort_total",
			Help: "Total canary auto-aborts (SLI burn breach or stage-0 error).",
		}),
		freezeActive: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "lw_deploy_freeze_active",
			Help: "1 when a deploy freeze is active, else 0. Freeze source wired with the deploy pipeline (D-CANARY-LIVE-SMOKE); stays 0 in V1.",
		}),
	}
	reg.MustRegister(m.stage, m.observedBurn, m.abortTotal, m.freezeActive)
	m.stage.Set(-1)
	return m
}

// SetStage records the active canary's current stage (-1 = none).
func (m *Metrics) SetStage(stage int) { m.stage.Set(float64(stage)) }

// SetObservedBurn records the last cohort burn the controller observed.
func (m *Metrics) SetObservedBurn(v float64) { m.observedBurn.Set(v) }

// IncAbort counts one auto-abort.
func (m *Metrics) IncAbort() { m.abortTotal.Inc() }

// SetFreeze records whether a deploy freeze is active.
func (m *Metrics) SetFreeze(active bool) {
	if active {
		m.freezeActive.Set(1)
		return
	}
	m.freezeActive.Set(0)
}

// Handler serves the Prometheus text format. No auth — scrape is in-cluster
// only, same convention as every other Go service.
func (m *Metrics) Handler() http.Handler {
	return promhttp.HandlerFor(m.registry, promhttp.HandlerOpts{})
}
