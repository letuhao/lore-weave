// Package metrics is the service-side metric library wrapper that
// enforces the L6.F observability admission runtime (SR12 §12AO).
//
// LoreWeave services do NOT call Prometheus client APIs directly.
// They instantiate one *Lib at boot via NewLib(inventory, mode, breach)
// and emit via Lib.Counter / Lib.Gauge / Lib.Histogram. The wrapper:
//
//   1. Looks the metric up in the cycle-19 inventory snapshot.
//   2. Honors the admission mode flag — AdmissionWarn (V1) emits a
//      warning + still records; AdmissionReject (V1+30d) DROPS the
//      emission silently and fires a Breach for postmortem.
//   3. Caches the underlying Prometheus collector behind the inventory
//      key so subsequent emissions are O(1).
//
// L6.F runtime split:
//
//   * contracts/observability/admission.go  — admission decision (cycle 19)
//   * pkg/metrics/admission_lib.go          — Prom-client integration (cycle 30)
//
// The library has NO `prometheus/client_golang` import on purpose —
// the recorder is an interface so:
//   (a) tests can swap in an in-memory recorder (no global registry),
//   (b) services can plug whatever Prometheus client they already use
//       (the existing services/world-service uses prometheus, the Go
//       publishers use prometheus + promauto; both wire the same Lib),
//   (c) Q-L6F-1 flag-flip path (V1 → V1+30d, time-based per LOCKED) is
//       atomic at the admission layer and the wrapper does not bypass.
//
// Q-L6F-1 LOCKED: foundation ships V1+30d as a flag-flip at config;
// admin can flip earlier. The wrapper reads the live mode from the
// underlying *observability.Admission on every emission (atomic load),
// so flipping the mode at runtime takes effect immediately for the
// NEXT emission — no re-registration of the Lib needed. The flip is
// triggered by calling Admission.SetMode(AdmissionReject); see
// contracts/observability/migration.md for the operator runbook.
package metrics

import (
	"errors"
	"fmt"
	"sync"

	"github.com/loreweave/foundation/contracts/observability"
)

// Recorder is the minimal Prometheus-client-shape interface the wrapper
// uses. Production services adapt their existing prometheus client to
// this; tests use the bundled InMemRecorder.
//
// All methods MUST be safe for concurrent use. Label-set MUST be passed
// in the same order as declared in inventory.yaml; mismatched labels
// are rejected by the admission layer when strict labels is on.
type Recorder interface {
	// AddCounter increments a counter by `delta` (delta >= 0).
	AddCounter(name string, labels map[string]string, delta float64) error
	// SetGauge sets a gauge to `value`.
	SetGauge(name string, labels map[string]string, value float64) error
	// ObserveHistogram pushes one observation into a histogram.
	ObserveHistogram(name string, labels map[string]string, value float64) error
}

// Lib is the service-facing metric emission surface. One instance per
// service binary. Construct with NewLib once at boot.
//
// The Lib is safe for concurrent use; internal state is a read-mostly
// snapshot guarded by sync.RWMutex.
type Lib struct {
	adm        *observability.Admission
	rec        Recorder
	mu         sync.RWMutex
	registered map[string]observability.Entry // metric name → resolved entry
}

// Errors.
var (
	// ErrUnknownKind is returned when the inventory entry's Kind does
	// not match the called method (e.g., Counter() on a gauge).
	ErrUnknownKind = errors.New("metrics: inventory kind does not match emission method")
	// ErrNilDeps is returned by NewLib when the admission or recorder
	// argument is nil. Foundational mis-wiring is loud, not silent.
	ErrNilDeps = errors.New("metrics: nil admission or recorder")
	// ErrAdmissionRejected wraps observability.ErrUnregisteredMetric so
	// callers can errors.Is against either.
	ErrAdmissionRejected = errors.New("metrics: admission rejected emission")
)

// NewLib constructs a metric library bound to a specific admission
// gate + recorder. The admission gate carries the current mode
// (Warn/Reject) and the inventory snapshot; the recorder is the actual
// Prometheus collector adapter.
//
// Returns ErrNilDeps if either argument is nil.
func NewLib(adm *observability.Admission, rec Recorder) (*Lib, error) {
	if adm == nil || rec == nil {
		return nil, ErrNilDeps
	}
	return &Lib{
		adm:        adm,
		rec:        rec,
		registered: make(map[string]observability.Entry),
	}, nil
}

// Counter emits a counter delta. Equivalent to prometheus's
// counter.Add. Returns nil on success or when the admission layer is
// in Warn mode (warn-and-drop semantics preserve service uptime).
//
// In Reject mode (V1+30d), emissions of unregistered metrics return
// the wrapped admission error AND skip the recorder call (drop).
func (l *Lib) Counter(name string, labels map[string]string, delta float64) error {
	return l.emit(name, observability.KindCounter, labels, delta)
}

// Gauge sets a gauge to `value`. Same admission semantics as Counter.
func (l *Lib) Gauge(name string, labels map[string]string, value float64) error {
	return l.emit(name, observability.KindGauge, labels, value)
}

// Histogram pushes one observation. Same admission semantics as
// Counter. Use Histogram for latency / size distributions.
func (l *Lib) Histogram(name string, labels map[string]string, value float64) error {
	return l.emit(name, observability.KindHistogram, labels, value)
}

// emit is the inner admission-then-record path shared by all three
// surfaces. It is intentionally short — the hot path matters.
//
// Order of operations (matters for SR12 §12AO):
//
//   1. Admission.EmitMetric → decides admit/warn/reject.
//   2. If admitted (nil err) → recorder.X (actual Prom push).
//   3. If rejected → wrap and return; recorder NOT called.
//   4. If warned (nil err in Warn mode) → recorder.X still called,
//      breach already fired by Admission.
//
// Note: when an admitted metric's recorder call fails, we return that
// recorder error without re-firing admission (the breach pertains to
// inventory mismatch, not recorder I/O).
func (l *Lib) emit(name string, expected observability.Kind, labels map[string]string, value float64) error {
	// SR12 §12AO warn-and-drop semantics: the wrapper MUST NOT push
	// unregistered emissions to the underlying Prometheus client under
	// EITHER mode. Otherwise warn-mode would silently inflate the
	// Prometheus scrape with unauditable series — defeating the whole
	// purpose of the inventory.
	//
	// Sequence:
	//   1. lookup() resolves the inventory Entry (cached).
	//   2. If absent → call adm.EmitMetric for breach accounting +
	//      mode-aware error decision (warn returns nil, reject returns
	//      ErrUnregisteredMetric). DROP the value in both cases.
	//   3. If present → run admission (label-strict check), then kind
	//      check, then record.
	entry, ok := l.lookup(name)
	if !ok {
		// Unregistered — admission decides warn vs reject; recorder
		// is NEVER invoked for unregistered emissions.
		if err := l.adm.EmitMetric(name, labels, value); err != nil {
			return fmt.Errorf("%w: %v", ErrAdmissionRejected, err)
		}
		return nil
	}

	// Registered path — kind cross-check first (caller bug, not an
	// inventory miss).
	if entry.Kind != expected {
		return fmt.Errorf("%w: name=%q expected=%s actual=%s", ErrUnknownKind, name, expected, entry.Kind)
	}

	// Run the admission gate for label-strict checks + emission counter.
	if err := l.adm.EmitMetric(name, labels, value); err != nil {
		return fmt.Errorf("%w: %v", ErrAdmissionRejected, err)
	}

	switch expected {
	case observability.KindCounter:
		return l.rec.AddCounter(name, labels, value)
	case observability.KindGauge:
		return l.rec.SetGauge(name, labels, value)
	case observability.KindHistogram:
		return l.rec.ObserveHistogram(name, labels, value)
	default:
		return fmt.Errorf("%w: kind=%s not supported by Lib", ErrUnknownKind, expected)
	}
}

// lookup caches inventory entries to avoid hashing the admission
// internal map on every emission. Lazily populated.
func (l *Lib) lookup(name string) (observability.Entry, bool) {
	l.mu.RLock()
	e, ok := l.registered[name]
	l.mu.RUnlock()
	if ok {
		return e, true
	}
	// Slow path: query admission's lookup (one-time per metric).
	all := l.adm.Inventory()
	for _, entry := range all {
		if entry.Name == name {
			l.mu.Lock()
			l.registered[name] = entry
			l.mu.Unlock()
			return entry, true
		}
	}
	return observability.Entry{}, false
}

// ─────────────────────────────────────────────────────────────────────
// InMemRecorder — test recorder used by admission_lib_test.go AND by
// integration tests; safe for concurrent use.
// ─────────────────────────────────────────────────────────────────────

// InMemRecorder is a Recorder implementation that keeps every emission
// in memory. Use in tests; production wires a prometheus-client
// adapter instead.
type InMemRecorder struct {
	mu     sync.Mutex
	counts map[string]float64
	gauges map[string]float64
	hists  map[string][]float64
}

// NewInMemRecorder constructs an empty InMemRecorder.
func NewInMemRecorder() *InMemRecorder {
	return &InMemRecorder{
		counts: make(map[string]float64),
		gauges: make(map[string]float64),
		hists:  make(map[string][]float64),
	}
}

// AddCounter implements Recorder.
func (r *InMemRecorder) AddCounter(name string, _ map[string]string, delta float64) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.counts[name] += delta
	return nil
}

// SetGauge implements Recorder.
func (r *InMemRecorder) SetGauge(name string, _ map[string]string, value float64) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.gauges[name] = value
	return nil
}

// ObserveHistogram implements Recorder.
func (r *InMemRecorder) ObserveHistogram(name string, _ map[string]string, value float64) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.hists[name] = append(r.hists[name], value)
	return nil
}

// CounterValue returns the accumulated counter for `name` (test helper).
func (r *InMemRecorder) CounterValue(name string) float64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.counts[name]
}

// GaugeValue returns the most-recent gauge value (test helper).
func (r *InMemRecorder) GaugeValue(name string) float64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.gauges[name]
}

// HistogramObservations returns a copy of all observed values (test helper).
func (r *InMemRecorder) HistogramObservations(name string) []float64 {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]float64, len(r.hists[name]))
	copy(out, r.hists[name])
	return out
}
