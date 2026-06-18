package observability

import (
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// AdmissionMode controls whether unregistered metric emissions are
// dropped silently with a warning (V1) or hard-rejected (V1+30d) per
// SR12 §12AO.
type AdmissionMode int

const (
	// AdmissionWarn — V1 behavior. Emit a warning log + increment the
	// rejected counter, but return nil to the caller so the metric
	// pipeline downstream still records the value. Useful during the
	// 30-day adoption window after inventory.yaml lands.
	AdmissionWarn AdmissionMode = iota
	// AdmissionReject — V1+30d behavior. Return ErrUnregisteredMetric
	// and DROP the emission. Callers SHOULD wire a budget-breach writer
	// for postmortem visibility.
	AdmissionReject
)

// ErrUnregisteredMetric is returned by Admission.EmitMetric when the
// metric name is not present in the inventory and mode = AdmissionReject.
var ErrUnregisteredMetric = errors.New("observability: metric not in inventory (admission rejected)")

// ErrUnregisteredLabel is returned by Admission.EmitMetric when an
// emission carries a label that is not declared in the entry's Labels
// slice. Label cardinality is the #1 Prometheus footgun (a typo on
// `user_id` blows up the series count); strict label admission is
// optional but recommended.
var ErrUnregisteredLabel = errors.New("observability: emission carries label not in inventory entry")

// BreachWriter is the callback fired on every admission rejection.
// Production wires this to budget_breach_writer.go; tests use a stub.
//
// Implementations MUST be non-blocking (use a buffered channel or
// fire-and-forget goroutine); a slow writer must not back-pressure the
// metric emission path.
type BreachWriter func(breach Breach)

// Breach is the payload passed to BreachWriter on rejection.
type Breach struct {
	MetricName string
	Labels     map[string]string
	Reason     string // "unregistered_metric" | "unregistered_label"
	Mode       AdmissionMode
	At         time.Time
}

// Admission is the runtime admission-control surface.
//
// Construct with NewAdmission(inventory, mode, breachWriter). The
// inventory snapshot is taken at construction; replace the Admission
// instance to swap inventories at runtime (admission is read-only).
type Admission struct {
	lookup       map[string]Entry
	mode         atomic.Int32 // AdmissionMode — atomic to allow runtime flip
	breach       BreachWriter
	strictLabels bool

	// counters for postmortem visibility
	emitted  atomic.Uint64
	rejected atomic.Uint64
	warned   atomic.Uint64
}

// NewAdmission constructs an Admission. inventory MUST already be
// loaded + validated (LoadAndValidate). mode is read atomically and
// may be flipped at runtime via SetMode. breachWriter may be nil
// (no-op) — in which case rejections are silent except for the
// returned error.
func NewAdmission(inv Inventory, mode AdmissionMode, breachWriter BreachWriter) *Admission {
	a := &Admission{
		lookup: inv.AdmissionLookup(),
		breach: breachWriter,
	}
	a.mode.Store(int32(mode))
	return a
}

// WithStrictLabels enables per-emission label-set verification. When
// enabled, EmitMetric rejects if the caller passes a label name that
// is NOT in the inventory entry's Labels slice. Default is off (label
// admission is informational; the existing prom-exporter label-cap
// configuration is the load-bearing cap).
func (a *Admission) WithStrictLabels() *Admission { a.strictLabels = true; return a }

// SetMode atomically flips the admission mode at runtime. Used by the
// 30-day adoption window flip (warn → reject). Returns the previous
// mode for symmetry.
func (a *Admission) SetMode(mode AdmissionMode) AdmissionMode {
	prev := AdmissionMode(a.mode.Swap(int32(mode)))
	return prev
}

// Mode returns the currently configured admission mode.
func (a *Admission) Mode() AdmissionMode { return AdmissionMode(a.mode.Load()) }

// Stats returns (emitted, warned, rejected) counters for postmortem.
func (a *Admission) Stats() (emitted, warned, rejected uint64) {
	return a.emitted.Load(), a.warned.Load(), a.rejected.Load()
}

// Inventory returns a snapshot of the registered inventory entries.
// Used by L6.F pkg/metrics wrappers that want to enforce a Kind check
// (Counter() vs Gauge()) before pushing to the underlying Prometheus
// client. The snapshot is taken at construction time — the slice is
// stable for the lifetime of the Admission.
//
// Returned slice is owned by the caller (safe to read; do not mutate).
func (a *Admission) Inventory() []Entry {
	out := make([]Entry, 0, len(a.lookup))
	for _, e := range a.lookup {
		out = append(out, e)
	}
	return out
}

// EmitMetric is the admission-control entry point. Call it BEFORE
// pushing the metric to the underlying Prometheus client.
//
// Behavior matrix (SR12 §12AO):
//
//	  mode = AdmissionWarn   + registered   → return nil, emit counted
//	  mode = AdmissionWarn   + unregistered → return nil, BreachWriter fired, warned++
//	  mode = AdmissionReject + registered   → return nil, emit counted
//	  mode = AdmissionReject + unregistered → return ErrUnregisteredMetric, breach fired, rejected++
//
// When strictLabels is on, an unknown label promotes to
// ErrUnregisteredLabel under both modes (warn still emits the breach
// row).
func (a *Admission) EmitMetric(name string, labels map[string]string, value float64) error {
	a.emitted.Add(1)
	entry, ok := a.lookup[name]
	if !ok {
		return a.handleBreach(name, labels, "unregistered_metric", ErrUnregisteredMetric)
	}
	if a.strictLabels {
		if err := verifyLabels(entry, labels); err != nil {
			return a.handleBreach(name, labels, "unregistered_label", err)
		}
	}
	_ = value // emission to the underlying Prometheus client is the
	// caller's responsibility; this surface is admission-control ONLY.
	return nil
}

func (a *Admission) handleBreach(name string, labels map[string]string, reason string, err error) error {
	breach := Breach{MetricName: name, Labels: labels, Reason: reason, Mode: a.Mode(), At: time.Now().UTC()}
	if a.breach != nil {
		a.breach(breach)
	}
	if a.Mode() == AdmissionReject {
		a.rejected.Add(1)
		return err
	}
	a.warned.Add(1)
	return nil
}

func verifyLabels(entry Entry, labels map[string]string) error {
	if len(labels) == 0 {
		return nil
	}
	allowed := make(map[string]struct{}, len(entry.Labels))
	for _, l := range entry.Labels {
		allowed[l] = struct{}{}
	}
	for k := range labels {
		if _, ok := allowed[k]; !ok {
			return fmt.Errorf("%w: name=%q label=%q (entry allows %v)", ErrUnregisteredLabel, entry.Name, k, entry.Labels)
		}
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────────
// Trace/log conventions (SR12 §12AO §3-§4) — minimal façade
// ─────────────────────────────────────────────────────────────────────

// TraceConvention enforces span-name conventions at boot. Callers
// register their span names; conventions library validates.
type TraceConvention struct {
	mu    sync.RWMutex
	names map[string]struct{}
}

// NewTraceConvention returns an empty convention registry.
func NewTraceConvention() *TraceConvention {
	return &TraceConvention{names: make(map[string]struct{})}
}

// Register declares an expected span name. Returns ErrInvalidEntry if
// the name does not match the snake_case + dot-separated convention.
//
// Examples accepted: `world.provision.canary_run`, `publisher.xadd`
// Examples rejected: `WorldProvision`, `world provision`, `world..run`
func (tc *TraceConvention) Register(name string) error {
	if !traceSpanRE.MatchString(name) {
		return fmt.Errorf("%w: trace span name=%q does not match snake_case.dot pattern", ErrInvalidEntry, name)
	}
	tc.mu.Lock()
	tc.names[name] = struct{}{}
	tc.mu.Unlock()
	return nil
}

// Known returns true if the span name was previously Registered.
func (tc *TraceConvention) Known(name string) bool {
	tc.mu.RLock()
	defer tc.mu.RUnlock()
	_, ok := tc.names[name]
	return ok
}
