package observability

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
)

// Kind is the metric/log/trace classifier from SR12 §12AO.
type Kind string

const (
	KindCounter   Kind = "counter"
	KindGauge     Kind = "gauge"
	KindHistogram Kind = "histogram"
	KindSummary   Kind = "summary"
	KindLog       Kind = "log"
	KindTrace     Kind = "trace"
)

// Layer is the L1..L7 layer label (foundation taxonomy).
type Layer string

const (
	LayerL1 Layer = "L1"
	LayerL2 Layer = "L2"
	LayerL3 Layer = "L3"
	LayerL4 Layer = "L4"
	LayerL5 Layer = "L5"
	LayerL6 Layer = "L6"
	LayerL7 Layer = "L7"
)

// Entry mirrors one element under `metrics:` in inventory.yaml.
//
// Field names align with the YAML keys; unknown YAML keys are
// rejected by LoadAndValidate when strict mode is requested.
type Entry struct {
	Name              string   `yaml:"name"`
	Kind              Kind     `yaml:"kind"`
	Layer             Layer    `yaml:"layer"`
	ShippedCycle      int      `yaml:"shipped_cycle"`
	Labels            []string `yaml:"labels"`
	Description       string   `yaml:"description"`
	Owner             string   `yaml:"owner"`
	Source            string   `yaml:"source"`
	CardinalityNotes  string   `yaml:"cardinality_notes,omitempty"`
}

// CardinalityBudget mirrors the optional top-level `cardinality_budget`
// block. Currently informational; the metrics_cardinality_test (cycle 6)
// pins the v1_target_series assertion.
type CardinalityBudget struct {
	PerRealityMetricCount    int `yaml:"per_reality_metric_count"`
	V1Realities              int `yaml:"v1_realities"`
	V1TargetSeries           int `yaml:"v1_target_series"`
	V1Plus30dRealities       int `yaml:"v1_plus_30d_realities"`
	V1Plus30dTargetSeries    int `yaml:"v1_plus_30d_target_series"`
	V3Realities              int `yaml:"v3_realities"`
	V3TargetSeries           int `yaml:"v3_target_series"`
}

// Inventory is the top-level inventory.yaml structure.
type Inventory struct {
	Version           int               `yaml:"version"`
	Metrics           []Entry           `yaml:"metrics"`
	CardinalityBudget CardinalityBudget `yaml:"cardinality_budget,omitempty"`
}

// Errors. Surface via errors.Is for stable matching in tests.
var (
	ErrInvalidEntry        = errors.New("observability: invalid inventory entry")
	ErrUnsupportedVersion  = errors.New("observability: unsupported inventory version")
	ErrDuplicateMetricName = errors.New("observability: duplicate metric name")
	ErrUnknownYAMLKey      = errors.New("observability: unknown YAML key (strict mode)")
)

// metricNameRE pins the lw_<domain>_<metric>_<unit> naming convention
// from SR12 §12AO.
//
// Exceptions: the cycle-6 inventory contains exporter-sourced metrics
// like `pg_stat_replication_lag_bytes` and `redis_memory_used_bytes`
// that follow upstream Prometheus exporter conventions, NOT our lw_*
// pattern. Validate accepts both: if the name starts with `lw_` we
// enforce the LoreWeave convention; otherwise we accept any
// well-formed Prometheus metric name (lowercase + underscores).
var (
	metricNameLW = regexp.MustCompile(`^lw_[a-z][a-z0-9]*(_[a-z0-9]+)+$`)
	// Bare metric names: lowercase + underscore (Prometheus instrument names).
	metricNamePrometheus = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)
	// Recording-rule names: Prometheus reserves `:` for recording rules
	// (https://prometheus.io/docs/practices/rules/ — "level:metric:operations").
	// The L7.I SLO recording rules ship as `lw:sli_<x>:ratio_5m`, which are
	// valid rule names but not valid instrument names — accept the `:` form.
	metricNameRecordingRule = regexp.MustCompile(`^[a-z][a-z0-9_]*(:[a-z0-9_]+)+$`)
)

// Validate inspects one Entry for required fields + sane values.
//
// Called by LoadAndValidate per entry; exposed for ad-hoc programmatic
// construction (tests, embedded use).
func (e Entry) Validate() error {
	if strings.TrimSpace(e.Name) == "" {
		return fmt.Errorf("%w: name empty", ErrInvalidEntry)
	}
	if strings.HasPrefix(e.Name, "lw_") {
		if !metricNameLW.MatchString(e.Name) {
			return fmt.Errorf("%w: name=%q does not match lw_<domain>_<metric>_<unit> (SR12 §12AO naming)", ErrInvalidEntry, e.Name)
		}
	} else if strings.Contains(e.Name, ":") {
		// Recording-rule name (contains `:`) — validate against the rule grammar.
		if !metricNameRecordingRule.MatchString(e.Name) {
			return fmt.Errorf("%w: name=%q is not a valid recording-rule name (lowercase + _ segments joined by :)", ErrInvalidEntry, e.Name)
		}
	} else if !metricNamePrometheus.MatchString(e.Name) {
		return fmt.Errorf("%w: name=%q has invalid characters (lowercase + _ only)", ErrInvalidEntry, e.Name)
	}
	switch e.Kind {
	case KindCounter, KindGauge, KindHistogram, KindSummary, KindLog, KindTrace:
	default:
		return fmt.Errorf("%w: name=%q kind=%q unknown", ErrInvalidEntry, e.Name, e.Kind)
	}
	switch e.Layer {
	case LayerL1, LayerL2, LayerL3, LayerL4, LayerL5, LayerL6, LayerL7:
	default:
		return fmt.Errorf("%w: name=%q layer=%q unknown (expected L1..L7)", ErrInvalidEntry, e.Name, e.Layer)
	}
	if e.ShippedCycle <= 0 {
		return fmt.Errorf("%w: name=%q shipped_cycle=%d must be > 0", ErrInvalidEntry, e.Name, e.ShippedCycle)
	}
	if strings.TrimSpace(e.Description) == "" {
		return fmt.Errorf("%w: name=%q description empty", ErrInvalidEntry, e.Name)
	}
	if strings.TrimSpace(e.Owner) == "" {
		return fmt.Errorf("%w: name=%q owner empty (governance — SR12 §12AO)", ErrInvalidEntry, e.Name)
	}
	if strings.TrimSpace(e.Source) == "" {
		return fmt.Errorf("%w: name=%q source empty (provenance — SR12 §12AO)", ErrInvalidEntry, e.Name)
	}
	// Label set sanity — Prometheus labels are lowercase + underscore.
	for _, lbl := range e.Labels {
		if !metricNamePrometheus.MatchString(lbl) {
			return fmt.Errorf("%w: name=%q label=%q invalid (lowercase + _ only)", ErrInvalidEntry, e.Name, lbl)
		}
	}
	return nil
}
