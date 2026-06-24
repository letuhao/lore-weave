package observability

import (
	"errors"
	"path/filepath"
	"runtime"
	"testing"
)

// TestLoadAndValidate_RealInventoryYAML pins that the shipped
// inventory.yaml (cycle 6 + carry-forward) parses + validates.
//
// Lax mode is used because the cycle-6 file may contain optional
// fields not yet enumerated in the strict schema (forward-compat).
func TestLoadAndValidate_RealInventoryYAML(t *testing.T) {
	_, thisFile, _, _ := runtime.Caller(0)
	invPath := filepath.Join(filepath.Dir(thisFile), "inventory.yaml")
	inv, err := LoadAndValidate(invPath, ModeLax)
	if err != nil {
		t.Fatalf("LoadAndValidate(%s, lax): %v", invPath, err)
	}
	if inv.Version != 1 {
		t.Errorf("Version = %d, want 1", inv.Version)
	}
	// Spot-check critical cycle-1..18 metrics exist.
	mustFind := []string{
		"pg_stat_replication_lag_bytes",   // cycle 1
		"lw_provisioner_steps_total",      // cycle 5
		"lw_outbox_enqueued_total",        // cycle 10
		"lw_projection_lag_seconds",       // cycle 15
		"lw_dependency_circuit_state",     // cycle 18
		"lw_service_mode",                 // cycle 18
	}
	for _, n := range mustFind {
		if _, ok := inv.Find(n); !ok {
			t.Errorf("inventory missing metric %q", n)
		}
	}
}

func TestParseAndValidate_RejectsUnsupportedVersion(t *testing.T) {
	bad := []byte(`version: 99` + "\n" + `metrics: []` + "\n")
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrUnsupportedVersion) {
		t.Errorf("err = %v, want ErrUnsupportedVersion", err)
	}
}

func TestParseAndValidate_RejectsDuplicateName(t *testing.T) {
	bad := []byte(`
version: 1
metrics:
  - name: lw_test_a_total
    kind: counter
    layer: L4
    shipped_cycle: 19
    labels: []
    description: 'x'
    owner: t
    source: t
  - name: lw_test_a_total
    kind: counter
    layer: L4
    shipped_cycle: 19
    labels: []
    description: 'y'
    owner: t
    source: t
`)
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrDuplicateMetricName) {
		t.Errorf("err = %v, want ErrDuplicateMetricName", err)
	}
}

func TestParseAndValidate_StrictRejectsUnknownKey(t *testing.T) {
	bad := []byte(`
version: 1
metrics:
  - name: lw_test_a_total
    kind: counter
    layer: L4
    shipped_cycle: 19
    labels: []
    description: 'x'
    owner: t
    source: t
    yolo_unknown_field: oops
`)
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrUnknownYAMLKey) {
		t.Errorf("err = %v, want ErrUnknownYAMLKey", err)
	}
	// Lax mode must accept the same input.
	if _, err := ParseAndValidate(bad, ModeLax); err != nil {
		t.Errorf("lax mode err = %v, want nil", err)
	}
}

func TestEntry_Validate_RejectsBadFields(t *testing.T) {
	base := Entry{
		Name:         "lw_test_x_total",
		Kind:         KindCounter,
		Layer:        LayerL4,
		ShippedCycle: 19,
		Labels:       []string{"reality_id", "outcome"},
		Description:  "d",
		Owner:        "o",
		Source:       "s",
	}
	cases := []struct {
		name   string
		mutate func(*Entry)
	}{
		{"empty name", func(e *Entry) { e.Name = "" }},
		{"bad name (lw_ but single segment)", func(e *Entry) { e.Name = "lw_foo" }},
		{"bad name (uppercase)", func(e *Entry) { e.Name = "lw_Test_X" }},
		{"bad kind", func(e *Entry) { e.Kind = "weirdmetric" }},
		{"bad layer", func(e *Entry) { e.Layer = "L99" }},
		{"zero shipped_cycle", func(e *Entry) { e.ShippedCycle = 0 }},
		{"empty description", func(e *Entry) { e.Description = "" }},
		{"empty owner", func(e *Entry) { e.Owner = "" }},
		{"empty source", func(e *Entry) { e.Source = "" }},
		{"bad label (uppercase)", func(e *Entry) { e.Labels = []string{"BadLabel"} }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			e := base
			c.mutate(&e)
			err := e.Validate()
			if !errors.Is(err, ErrInvalidEntry) {
				t.Errorf("err = %v, want ErrInvalidEntry", err)
			}
		})
	}
}

func TestEntry_Validate_AcceptsExporterMetric(t *testing.T) {
	// Cycle-6 inventory contains non-lw_ exporter metrics like
	// pg_stat_replication_lag_bytes — those must validate.
	e := Entry{
		Name:         "pg_stat_replication_lag_bytes",
		Kind:         KindGauge,
		Layer:        LayerL1,
		ShippedCycle: 1,
		Labels:       []string{"application_name", "shard_host"},
		Description:  "x",
		Owner:        "sre",
		Source:       "postgres-exporter",
	}
	if err := e.Validate(); err != nil {
		t.Errorf("exporter metric Validate() = %v, want nil", err)
	}
}
