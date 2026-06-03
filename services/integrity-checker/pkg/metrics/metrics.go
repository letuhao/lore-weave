// Package metrics is the L3.J Prometheus metric emitter for the
// integrity-checker service.
//
// The [Emitter] interface is the sink the orchestrators (pkg/live,
// pkg/full_check) call; [PromEmitter] is the production binding over a
// client_golang registry, and [InMemEmitter] is the test fake. The
// integrity-checker is a run-once K8s CronJob (no scrape endpoint), so
// [PromEmitter.Push] ships the accumulated series to a Pushgateway on sweep
// completion (main.go, gated on PUSHGATEWAY_URL) rather than serving /metrics.
//
// Every metric NAME constant below MUST have a matching row in
// contracts/observability/inventory.yaml — the L1.K observability-inventory-lint
// (cycle 7) greps these literals out of source and fails on any drift, so the
// constants are also what pin the inventory rows in place.
//
// L3.J metrics:
//
//   - lw_projection_lag_seconds (gauge)      — wall-clock lag = NOW() -
//     projection.applied_at. Per (reality, table).
//   - lw_projection_drift_count (gauge)      — reaffirms cycle-13 entry;
//     this service is the new owner (replaces the cron skeleton).
//   - lw_projection_check_duration_seconds (histogram) — wall-time of one
//     (reality, table, mode) check. Per (mode={daily|monthly}, table).
//     Helps SRE see "monthly check is taking 6h" early.
//   - lw_projection_check_runs_total (counter) — per (mode, outcome).
//     outcome ∈ {ok, error}.
//
// Cardinality bounds (verified by metrics_cardinality_test in cycle 6):
//   - reality_id × 10 tables = ≤ 10K series at V1+30d horizon
//   - mode ∈ {daily, monthly} → ×2 multiplier
//   - outcome ∈ {ok, error} on the counter only → ×2 on a single series
package metrics

import (
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/push"
)

// pushTimeout bounds the Pushgateway HTTP call so an unreachable/slow gateway can
// never block the CronJob's shutdown (the default push client has NO timeout).
const pushTimeout = 10 * time.Second

// Metric names. EXPORTED so observability-inventory-lint.sh can grep them
// out of source. ALSO used as string keys by the live-wired prometheus
// registry binding at startup (deferred to D-PUBLISHER-LIVE-WIRING).
//
// CRITICAL: every entry here MUST have a matching row in
// contracts/observability/inventory.yaml. Cycle-7 lint enforces.
const (
	// MetricProjectionLagSeconds — gauge, labels: [reality_id, table]
	MetricProjectionLagSeconds = "lw_projection_lag_seconds"

	// MetricProjectionDriftCount — gauge, labels: [reality_id, table]
	// Re-declared in cycle 15 (was cycle 13); same name, new owner.
	MetricProjectionDriftCount = "lw_projection_drift_count"

	// MetricProjectionCheckDurationSeconds — histogram, labels: [mode, table]
	MetricProjectionCheckDurationSeconds = "lw_projection_check_duration_seconds"

	// MetricProjectionCheckRunsTotal — counter, labels: [mode, outcome]
	MetricProjectionCheckRunsTotal = "lw_projection_check_runs_total"
)

// CheckOutcome enumerates the values for the `outcome` label on
// MetricProjectionCheckRunsTotal. Bounded set = bounded cardinality.
type CheckOutcome string

// Bounded set of outcomes. Cycle-7 lint guards cardinality.
const (
	OutcomeOK    CheckOutcome = "ok"
	OutcomeError CheckOutcome = "error"
)

// IsValid reports whether o is one of the known values.
func (o CheckOutcome) IsValid() bool {
	return o == OutcomeOK || o == OutcomeError
}

// Emitter is the abstract sink the orchestrator calls. Production binds it to a
// prometheus.Registry (PromEmitter); tests inject InMemEmitter.
//
// All four methods are stable across daily + monthly modes; the `mode` label is
// set by the caller.
type Emitter interface {
	SetProjectionLagSeconds(realityID, table string, lagSeconds float64)
	SetProjectionDriftCount(realityID, table string, count float64)
	ObserveCheckDuration(mode, table string, seconds float64)
	IncCheckRun(mode string, outcome CheckOutcome)
}

// PromEmitter is the production [Emitter]: a process-local prometheus.Registry
// (so Go runtime metrics don't ship by accident + tests get a clean instance —
// the loreweave convention, mirrors services/canary-controller). The
// integrity-checker is a run-once K8s CronJob, so there is no scrape endpoint;
// [PromEmitter.Push] ships the accumulated series to a Pushgateway on sweep
// completion. Label sets match the inventory.yaml rows pinned by the constants
// above (cycle-7 observability-inventory-lint enforces).
type PromEmitter struct {
	registry *prometheus.Registry
	lag      *prometheus.GaugeVec
	drift    *prometheus.GaugeVec
	duration *prometheus.HistogramVec
	runs     *prometheus.CounterVec
}

// NewPromEmitter builds + registers the four L3.J collectors on a fresh registry.
func NewPromEmitter() *PromEmitter {
	reg := prometheus.NewRegistry()
	e := &PromEmitter{
		registry: reg,
		lag: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: MetricProjectionLagSeconds,
			Help: "Projection wall-clock lag (NOW() - applied_at) per reality+table.",
		}, []string{"reality_id", "table"}),
		drift: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: MetricProjectionDriftCount,
			Help: "Drifted rows found in the last check per reality+table.",
		}, []string{"reality_id", "table"}),
		duration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name: MetricProjectionCheckDurationSeconds,
			Help: "Wall-time of one (reality, table) integrity check per mode+table.",
			// Span daily (sub-second, 20 rows) AND monthly full-scan (minutes-to-
			// hours): DefBuckets top out at 10s, which would collapse every monthly
			// check into +Inf. Exponential 0.05s → ~14.5h gives resolution across
			// both modes (the metric's stated goal is spotting a slow monthly run).
			Buckets: prometheus.ExponentialBuckets(0.05, 4, 11),
		}, []string{"mode", "table"}),
		runs: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: MetricProjectionCheckRunsTotal,
			Help: "Integrity check runs per mode+outcome (ok|error).",
		}, []string{"mode", "outcome"}),
	}
	reg.MustRegister(e.lag, e.drift, e.duration, e.runs)
	return e
}

// SetProjectionLagSeconds records the lag gauge for one reality+table.
func (e *PromEmitter) SetProjectionLagSeconds(realityID, table string, lagSeconds float64) {
	e.lag.WithLabelValues(realityID, table).Set(lagSeconds)
}

// SetProjectionDriftCount records the drift gauge for one reality+table.
func (e *PromEmitter) SetProjectionDriftCount(realityID, table string, count float64) {
	e.drift.WithLabelValues(realityID, table).Set(count)
}

// ObserveCheckDuration records a duration histogram sample for one mode+table.
func (e *PromEmitter) ObserveCheckDuration(mode, table string, seconds float64) {
	e.duration.WithLabelValues(mode, table).Observe(seconds)
}

// IncCheckRun increments the run-outcome counter for one mode+outcome.
func (e *PromEmitter) IncCheckRun(mode string, outcome CheckOutcome) {
	e.runs.WithLabelValues(mode, string(outcome)).Inc()
}

// Push ships all accumulated series to the Pushgateway at `url` under job
// "integrity-checker". Uses PUT semantics (replaces the job group), so each
// CronJob run overwrites the prior run's series rather than accumulating stale
// reality/table label combinations. Call ONCE after the sweep completes.
func (e *PromEmitter) Push(url string) error {
	return push.New(url, "integrity-checker").
		Client(&http.Client{Timeout: pushTimeout}).
		Gatherer(e.registry).
		Push()
}

// Compile-time check that PromEmitter satisfies the Emitter contract.
var _ Emitter = (*PromEmitter)(nil)

// InMemEmitter is the test fake. Records every emission for assertion.
type InMemEmitter struct {
	Lag       map[string]float64 // "reality|table" → value
	Drift     map[string]float64 // "reality|table" → value
	Durations []DurationSample
	Runs      map[string]int // "mode|outcome" → count
}

// DurationSample captures one ObserveCheckDuration call.
type DurationSample struct {
	Mode    string
	Table   string
	Seconds float64
}

// NewInMemEmitter returns an empty in-memory emitter.
func NewInMemEmitter() *InMemEmitter {
	return &InMemEmitter{
		Lag:   make(map[string]float64),
		Drift: make(map[string]float64),
		Runs:  make(map[string]int),
	}
}

// SetProjectionLagSeconds records a lag-seconds gauge value.
func (e *InMemEmitter) SetProjectionLagSeconds(realityID, table string, lagSeconds float64) {
	e.Lag[realityID+"|"+table] = lagSeconds
}

// SetProjectionDriftCount records a drift-count gauge value.
func (e *InMemEmitter) SetProjectionDriftCount(realityID, table string, count float64) {
	e.Drift[realityID+"|"+table] = count
}

// ObserveCheckDuration records a histogram sample.
func (e *InMemEmitter) ObserveCheckDuration(mode, table string, seconds float64) {
	e.Durations = append(e.Durations, DurationSample{Mode: mode, Table: table, Seconds: seconds})
}

// IncCheckRun increments the run-outcome counter.
func (e *InMemEmitter) IncCheckRun(mode string, outcome CheckOutcome) {
	e.Runs[mode+"|"+string(outcome)]++
}
