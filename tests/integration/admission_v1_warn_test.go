//go:build integration

package integration

import (
	"errors"
	"testing"

	"github.com/loreweave/foundation/contracts/observability"
	"github.com/loreweave/foundation/pkg/metrics"
)

// TestAdmission_V1WarnAndV1Plus30dReject — L6.F integration smoke.
//
// Wires the cycle-19 *observability.Admission with the cycle-30
// pkg/metrics.Lib + BudgetBreachBuffer end-to-end and asserts the
// two acceptance criteria from the layer plan (line 169-173):
//
//   * V1 mode (warn) — unregistered metric emits a warning + drops;
//     service uptime preserved (no error returned).
//   * V1+30d mode (reject) — same emission returns
//     ErrAdmissionRejected, drops, breach row recorded.
//
// Q-L6F-1 LOCKED: foundation ships V1+30d as a runtime flag-flip;
// admin can flip earlier. Test verifies the flip without re-construction.
func TestAdmission_V1WarnAndV1Plus30dReject(t *testing.T) {
	inv := observability.Inventory{
		Version: 1,
		Metrics: []observability.Entry{{
			Name:         "lw_test_registered_total",
			Kind:         observability.KindCounter,
			Layer:        observability.LayerL6,
			ShippedCycle: 30,
			Labels:       []string{},
			Description:  "test counter",
			Owner:        "foundation",
			Source:       "integration test",
		}},
	}
	buf := observability.NewBudgetBreachBuffer(16)
	adm := observability.NewAdmission(inv, observability.AdmissionWarn, buf.AsBreachWriter())
	rec := metrics.NewInMemRecorder()
	lib, err := metrics.NewLib(adm, rec)
	if err != nil {
		t.Fatalf("NewLib: %v", err)
	}

	// ── V1 mode: unregistered metric — no error, no record.
	if err := lib.Counter("lw_orphan_metric", nil, 1); err != nil {
		t.Fatalf("V1 warn mode must NOT return error: %v", err)
	}
	if rec.CounterValue("lw_orphan_metric") != 0 {
		t.Fatalf("V1 warn mode must DROP unregistered emission")
	}

	// Registered metric still records.
	if err := lib.Counter("lw_test_registered_total", nil, 5); err != nil {
		t.Fatalf("V1 mode registered emission failed: %v", err)
	}
	if rec.CounterValue("lw_test_registered_total") != 5 {
		t.Fatalf("registered counter not recorded")
	}

	// Breach buffer captured the warn-mode unregistered emission.
	if buf.Size() != 1 {
		t.Fatalf("expected 1 breach row from warn drop; got %d", buf.Size())
	}

	// ── Flip to V1+30d (reject) — Q-L6F-1 runtime flip.
	adm.SetMode(observability.AdmissionReject)

	if err := lib.Counter("lw_orphan_metric", nil, 1); !errors.Is(err, metrics.ErrAdmissionRejected) {
		t.Fatalf("V1+30d reject mode must return ErrAdmissionRejected; got %v", err)
	}
	if rec.CounterValue("lw_orphan_metric") != 0 {
		t.Fatalf("V1+30d reject mode must DROP unregistered emission")
	}

	// Registered metric ALSO still works post-flip (the gate doesn't
	// punish inventoried metrics).
	if err := lib.Counter("lw_test_registered_total", nil, 2); err != nil {
		t.Fatalf("V1+30d registered emission failed: %v", err)
	}
	if rec.CounterValue("lw_test_registered_total") != 7 {
		t.Fatalf("counter total after flip = %v, want 7", rec.CounterValue("lw_test_registered_total"))
	}

	emitted, warned, rejected := adm.Stats()
	if emitted != 4 || warned != 1 || rejected != 1 {
		t.Fatalf("stats emitted=%d warned=%d rejected=%d; want 4/1/1", emitted, warned, rejected)
	}
}
