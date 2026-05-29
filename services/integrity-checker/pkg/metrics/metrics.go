// Package metrics is the L3.J Prometheus metric emitter for the
// integrity-checker service.
//
// V1 ships as METRIC NAMES + EMISSION POINTS only. The actual prometheus
// registry binding (prometheus.NewCounterVec etc.) lands at live wiring
// alongside main.go's /metrics endpoint (D-PUBLISHER-LIVE-WIRING).
//
// Why ship the constants + emission helper now? Two reasons:
//   1. The L1.K observability-inventory-lint.sh (cycle 7) reads literal
//      "lw_*" strings from .go / .rs source files and demands matching
//      inventory.yaml entries. The lint catches the inverse — code-emitted
//      symbols missing from inventory — so the constants here are what
//      pin the cycle-15 inventory rows in place.
//   2. The daily_loop / full_check / state_writer packages all need
//      symbolic names to emit; centralizing them here makes future
//      renames trivial (the cycle-7 lint will catch ANY rename).
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

// Emitter is the abstract sink the orchestrator calls. Production binds
// it to prometheus.Registry; tests inject InMemEmitter.
//
// All four methods are stable across daily + monthly modes; the `mode`
// label is set by the caller.
type Emitter interface {
	SetProjectionLagSeconds(realityID, table string, lagSeconds float64)
	SetProjectionDriftCount(realityID, table string, count float64)
	ObserveCheckDuration(mode, table string, seconds float64)
	IncCheckRun(mode string, outcome CheckOutcome)
}

// InMemEmitter is the test fake. Records every emission for assertion.
type InMemEmitter struct {
	Lag           map[string]float64 // "reality|table" → value
	Drift         map[string]float64 // "reality|table" → value
	Durations     []DurationSample
	Runs          map[string]int // "mode|outcome" → count
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
