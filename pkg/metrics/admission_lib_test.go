package metrics

import (
	"errors"
	"testing"

	"github.com/loreweave/foundation/contracts/observability"
)

// minimalInventory returns a tiny valid Inventory for tests. Two
// metrics: one counter, one gauge — covers Counter() + Gauge() paths
// and the "unknown to inventory" reject path.
func minimalInventory() observability.Inventory {
	return observability.Inventory{
		Version: 1,
		Metrics: []observability.Entry{
			{
				Name:         "lw_test_emitted_total",
				Kind:         observability.KindCounter,
				Layer:        observability.LayerL6,
				ShippedCycle: 30,
				Labels:       []string{"reality_id"},
				Description:  "test counter",
				Owner:        "foundation",
				Source:       "test",
			},
			{
				Name:         "lw_test_active_gauge",
				Kind:         observability.KindGauge,
				Layer:        observability.LayerL6,
				ShippedCycle: 30,
				Labels:       []string{},
				Description:  "test gauge",
				Owner:        "foundation",
				Source:       "test",
			},
		},
	}
}

func newTestLib(t *testing.T, mode observability.AdmissionMode) (*Lib, *InMemRecorder, *observability.Admission) {
	t.Helper()
	inv := minimalInventory()
	adm := observability.NewAdmission(inv, mode, nil)
	rec := NewInMemRecorder()
	lib, err := NewLib(adm, rec)
	if err != nil {
		t.Fatalf("NewLib: %v", err)
	}
	return lib, rec, adm
}

func TestNewLib_NilDeps(t *testing.T) {
	if _, err := NewLib(nil, NewInMemRecorder()); !errors.Is(err, ErrNilDeps) {
		t.Fatalf("expected ErrNilDeps for nil admission; got %v", err)
	}
	inv := minimalInventory()
	adm := observability.NewAdmission(inv, observability.AdmissionWarn, nil)
	if _, err := NewLib(adm, nil); !errors.Is(err, ErrNilDeps) {
		t.Fatalf("expected ErrNilDeps for nil recorder; got %v", err)
	}
}

func TestCounter_RegisteredMetricRecorded(t *testing.T) {
	lib, rec, _ := newTestLib(t, observability.AdmissionWarn)
	if err := lib.Counter("lw_test_emitted_total", map[string]string{"reality_id": "r1"}, 3); err != nil {
		t.Fatalf("Counter: %v", err)
	}
	if got := rec.CounterValue("lw_test_emitted_total"); got != 3 {
		t.Fatalf("counter value = %v, want 3", got)
	}
}

// L6.F.4 acceptance: V1 mode (warn) — unregistered metric emits a
// warning + DROPS the emission at the admission layer; the recorder is
// NOT invoked. (Earlier draft erroneously recorded warn-mode unregistered
// emissions; revised to match SR12 §12AO "warn-and-drop" semantics —
// the value is dropped under BOTH warn and reject modes; warn only
// suppresses the error to keep service uptime.)
func TestCounter_UnregisteredMetric_WarnMode_DropsAndNoError(t *testing.T) {
	lib, rec, adm := newTestLib(t, observability.AdmissionWarn)
	err := lib.Counter("lw_unknown_thing", nil, 1)
	if err != nil {
		t.Fatalf("warn mode should NOT return error for unregistered metric; got %v", err)
	}
	if got := rec.CounterValue("lw_unknown_thing"); got != 0 {
		t.Fatalf("warn mode: unregistered metric should NOT reach recorder; got %v", got)
	}
	_, warned, rejected := adm.Stats()
	if warned != 1 || rejected != 0 {
		t.Fatalf("stats warn=%d rejected=%d; want warn=1 rejected=0", warned, rejected)
	}
}

// L6.F.4 acceptance: V1+30d mode (reject) — unregistered metric
// returns ErrAdmissionRejected AND skips the recorder.
func TestCounter_UnregisteredMetric_RejectMode_DropsWithError(t *testing.T) {
	lib, rec, adm := newTestLib(t, observability.AdmissionReject)
	err := lib.Counter("lw_unknown_thing", nil, 1)
	if !errors.Is(err, ErrAdmissionRejected) {
		t.Fatalf("reject mode: expected ErrAdmissionRejected; got %v", err)
	}
	if got := rec.CounterValue("lw_unknown_thing"); got != 0 {
		t.Fatalf("reject mode: recorder must not be called; got %v", got)
	}
	_, _, rejected := adm.Stats()
	if rejected != 1 {
		t.Fatalf("expected rejected=1; got %d", rejected)
	}
}

// Q-L6F-1 LOCKED — time-based flag flip; admin can flip earlier. The
// runtime SetMode call MUST take effect on the next emission without
// re-constructing the Lib.
func TestSetMode_RuntimeFlipTakesEffectImmediately(t *testing.T) {
	lib, rec, adm := newTestLib(t, observability.AdmissionWarn)

	// Warn mode: unregistered → no error, no record.
	if err := lib.Counter("lw_unknown", nil, 1); err != nil {
		t.Fatalf("warn mode unexpected err: %v", err)
	}
	if rec.CounterValue("lw_unknown") != 0 {
		t.Fatalf("warn mode should not record unregistered metric")
	}

	// Flip to reject — same emission now errors + drops.
	adm.SetMode(observability.AdmissionReject)
	if err := lib.Counter("lw_unknown", nil, 1); !errors.Is(err, ErrAdmissionRejected) {
		t.Fatalf("post-flip emission should error; got %v", err)
	}
	if rec.CounterValue("lw_unknown") != 0 {
		t.Fatalf("reject mode must not record")
	}
}

func TestGauge_RegisteredMetricRecorded(t *testing.T) {
	lib, rec, _ := newTestLib(t, observability.AdmissionWarn)
	if err := lib.Gauge("lw_test_active_gauge", nil, 42); err != nil {
		t.Fatalf("Gauge: %v", err)
	}
	if got := rec.GaugeValue("lw_test_active_gauge"); got != 42 {
		t.Fatalf("gauge = %v, want 42", got)
	}
}

// Kind-mismatch guard: calling Gauge() on a counter inventory entry
// must error with ErrUnknownKind and skip the recorder.
func TestKindMismatch_GaugeOnCounter_Errors(t *testing.T) {
	lib, rec, _ := newTestLib(t, observability.AdmissionWarn)
	err := lib.Gauge("lw_test_emitted_total", nil, 1)
	if !errors.Is(err, ErrUnknownKind) {
		t.Fatalf("expected ErrUnknownKind; got %v", err)
	}
	if rec.GaugeValue("lw_test_emitted_total") != 0 {
		t.Fatalf("kind-mismatch must not write to recorder")
	}
}

// BreachWriter integration smoke — wire a BudgetBreachBuffer + verify
// the breach row is captured on admission rejection.
func TestBreachWriter_RejectionWritesToBuffer(t *testing.T) {
	inv := minimalInventory()
	buf := observability.NewBudgetBreachBuffer(8)
	adm := observability.NewAdmission(inv, observability.AdmissionReject, buf.AsBreachWriter())
	lib, _ := NewLib(adm, NewInMemRecorder())

	_ = lib.Counter("lw_uninventoried_metric", map[string]string{"a": "b"}, 1)

	rows := buf.Drain()
	if len(rows) != 1 {
		t.Fatalf("expected 1 breach row; got %d", len(rows))
	}
	if rows[0].MetricName != "lw_uninventoried_metric" {
		t.Fatalf("breach metric=%q; want lw_uninventoried_metric", rows[0].MetricName)
	}
	if rows[0].Reason != "unregistered_metric" {
		t.Fatalf("breach reason=%q; want unregistered_metric", rows[0].Reason)
	}
}

// Concurrency smoke: many goroutines calling Counter() must not race
// on lookup cache.
func TestLib_ConcurrentEmissions(t *testing.T) {
	lib, rec, _ := newTestLib(t, observability.AdmissionWarn)
	const N = 200
	done := make(chan struct{}, N)
	for i := 0; i < N; i++ {
		go func() {
			_ = lib.Counter("lw_test_emitted_total", map[string]string{"reality_id": "r1"}, 1)
			done <- struct{}{}
		}()
	}
	for i := 0; i < N; i++ {
		<-done
	}
	if got := rec.CounterValue("lw_test_emitted_total"); got != float64(N) {
		t.Fatalf("counter value = %v, want %d", got, N)
	}
}
