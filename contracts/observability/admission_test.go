package observability

import (
	"errors"
	"testing"
)

func newTestInventory(t *testing.T) Inventory {
	t.Helper()
	return Inventory{
		Version: 1,
		Metrics: []Entry{
			{
				Name: "lw_test_registered_total", Kind: KindCounter, Layer: LayerL4,
				ShippedCycle: 19, Labels: []string{"reality_id", "outcome"},
				Description: "x", Owner: "t", Source: "t",
			},
		},
	}
}

func TestAdmission_Warn_AcceptsRegistered(t *testing.T) {
	inv := newTestInventory(t)
	a := NewAdmission(inv, AdmissionWarn, nil)
	if err := a.EmitMetric("lw_test_registered_total", map[string]string{"reality_id": "r1"}, 1); err != nil {
		t.Fatalf("registered emission err = %v, want nil", err)
	}
	emitted, warned, rejected := a.Stats()
	if emitted != 1 || warned != 0 || rejected != 0 {
		t.Errorf("stats = (%d,%d,%d), want (1,0,0)", emitted, warned, rejected)
	}
}

func TestAdmission_Warn_AcceptsUnregisteredButCounts(t *testing.T) {
	inv := newTestInventory(t)
	captured := []Breach{}
	bw := func(b Breach) { captured = append(captured, b) }
	a := NewAdmission(inv, AdmissionWarn, bw)
	if err := a.EmitMetric("lw_test_NOTREGISTERED_total", nil, 1); err != nil {
		t.Fatalf("warn mode unregistered emission err = %v, want nil", err)
	}
	emitted, warned, rejected := a.Stats()
	if emitted != 1 || warned != 1 || rejected != 0 {
		t.Errorf("stats = (%d,%d,%d), want (1,1,0)", emitted, warned, rejected)
	}
	if len(captured) != 1 || captured[0].Reason != "unregistered_metric" {
		t.Errorf("captured breaches = %+v", captured)
	}
}

func TestAdmission_Reject_RejectsUnregistered(t *testing.T) {
	inv := newTestInventory(t)
	a := NewAdmission(inv, AdmissionReject, nil)
	err := a.EmitMetric("lw_test_NOTREGISTERED_total", nil, 1)
	if !errors.Is(err, ErrUnregisteredMetric) {
		t.Errorf("err = %v, want ErrUnregisteredMetric", err)
	}
	emitted, warned, rejected := a.Stats()
	if emitted != 1 || warned != 0 || rejected != 1 {
		t.Errorf("stats = (%d,%d,%d), want (1,0,1)", emitted, warned, rejected)
	}
}

func TestAdmission_SetMode_FlipsAtRuntime(t *testing.T) {
	inv := newTestInventory(t)
	a := NewAdmission(inv, AdmissionWarn, nil)
	// First emit unregistered — warn (nil).
	if err := a.EmitMetric("lw_foo_bar_total", nil, 1); err != nil {
		t.Errorf("warn-mode err = %v, want nil", err)
	}
	// Flip to reject.
	prev := a.SetMode(AdmissionReject)
	if prev != AdmissionWarn {
		t.Errorf("SetMode prev = %v, want AdmissionWarn", prev)
	}
	if err := a.EmitMetric("lw_foo_bar_total", nil, 1); !errors.Is(err, ErrUnregisteredMetric) {
		t.Errorf("after flip err = %v, want ErrUnregisteredMetric", err)
	}
}

func TestAdmission_StrictLabels_RejectsUnknownLabel(t *testing.T) {
	inv := newTestInventory(t)
	a := NewAdmission(inv, AdmissionReject, nil).WithStrictLabels()
	err := a.EmitMetric("lw_test_registered_total", map[string]string{"user_id": "u1"}, 1)
	if !errors.Is(err, ErrUnregisteredLabel) {
		t.Errorf("err = %v, want ErrUnregisteredLabel", err)
	}
}

func TestBudgetBreachBuffer_RingEvictsOldest(t *testing.T) {
	b := NewBudgetBreachBuffer(2)
	b.Write(BudgetBreachRow{MetricName: "m1"})
	b.Write(BudgetBreachRow{MetricName: "m2"})
	b.Write(BudgetBreachRow{MetricName: "m3"}) // evicts m1
	rows := b.Drain()
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2", len(rows))
	}
	if rows[0].MetricName != "m2" || rows[1].MetricName != "m3" {
		t.Errorf("rows = %+v, want [m2 m3]", rows)
	}
	if b.DroppedCount() != 1 {
		t.Errorf("DroppedCount = %d, want 1", b.DroppedCount())
	}
}

func TestBudgetBreachBuffer_AsBreachWriter(t *testing.T) {
	inv := newTestInventory(t)
	b := NewBudgetBreachBuffer(8)
	a := NewAdmission(inv, AdmissionReject, b.AsBreachWriter())
	_ = a.EmitMetric("lw_nope_x_total", map[string]string{"r": "1"}, 1)
	rows := b.Drain()
	if len(rows) != 1 || rows[0].MetricName != "lw_nope_x_total" || rows[0].Reason != "unregistered_metric" {
		t.Errorf("rows = %+v", rows)
	}
}

func TestTraceConvention_AcceptsValidNames(t *testing.T) {
	tc := NewTraceConvention()
	cases := []string{"publisher.xadd", "world.provision.canary_run", "roleplay.session.heartbeat"}
	for _, c := range cases {
		if err := tc.Register(c); err != nil {
			t.Errorf("Register(%q) = %v, want nil", c, err)
		}
		if !tc.Known(c) {
			t.Errorf("Known(%q) = false, want true", c)
		}
	}
}

func TestTraceConvention_RejectsBadNames(t *testing.T) {
	tc := NewTraceConvention()
	for _, c := range []string{"NotSnake", "no.UPPER.case", "single", "double..dot", "x.", ".x"} {
		if err := tc.Register(c); !errors.Is(err, ErrInvalidEntry) {
			t.Errorf("Register(%q) err = %v, want ErrInvalidEntry", c, err)
		}
	}
}
