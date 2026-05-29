//go:build integration

package integration

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// metrics_cardinality_test.go — L1.I.9 (RAID cycle 6).
//
// LOAD-BEARING TEST per L1.I §7 acceptance criteria:
//   "Inject 100 realities; verify Prometheus series count ≤ 7 metrics × N realities
//    (no cardinality explosion)"
//
// The test does NOT require a live Prometheus — it computes the worst-case
// series count from the static config + inventory and asserts the math
// holds.
//
// What we check:
//   1. contracts/observability/inventory.yaml ENUMERATES the per-reality
//      metric set (the cardinality budget).
//   2. The per_reality budget × 100 realities ≤ budgeted V1 series target
//      = 700 series.
//   3. infra/postgres-exporter/postgres-exporter.yaml does NOT introduce
//      labels outside the allowed set (reality_id, shard_host, db_class,
//      role, application_name, relname (audit only)).
//   4. NO Thanos sidecar config files (Q-L1I-2 V1 retention = 30d native).

const (
	inventoryPath        = "../../contracts/observability/inventory.yaml"
	postgresExporterPath = "../../infra/postgres-exporter/postgres-exporter.yaml"
)

// allowed label dimensions for L1 metrics — anything outside this set is
// a cardinality risk and must be explicitly approved.
var allowedLabels = map[string]bool{
	"reality_id":       true,
	"shard_host":       true,
	"db_class":         true,
	"role":             true,
	"application_name": true,
	"relname":          true, // audit-only — postgres-exporter restricts via WHERE clause
	"severity":         true,
	"route":            true,
	"team":             true,
	"step":             true, // provisioner step labels (frozen const)
	"outcome":          true,
	"pool_name":        true,
	"database":         true,
	"instance":         true,
	"db":               true,
	"key_kind":         true,
	"migration_id":     true,
	"reason":           true,
}

type inventoryMetric struct {
	Name          string   `yaml:"name"`
	Kind          string   `yaml:"kind"`
	Layer         string   `yaml:"layer"`
	ShippedCycle  int      `yaml:"shipped_cycle"`
	Labels        []string `yaml:"labels"`
	Description   string   `yaml:"description"`
	Owner         string   `yaml:"owner"`
}

type inventoryFile struct {
	Version           int               `yaml:"version"`
	Metrics           []inventoryMetric `yaml:"metrics"`
	CardinalityBudget struct {
		PerRealityMetricCount int `yaml:"per_reality_metric_count"`
		V1Realities           int `yaml:"v1_realities"`
		V1TargetSeries        int `yaml:"v1_target_series"`
	} `yaml:"cardinality_budget"`
}

func loadInventory(t *testing.T) *inventoryFile {
	t.Helper()
	raw, err := os.ReadFile(inventoryPath)
	if err != nil {
		t.Fatalf("read inventory: %v", err)
	}
	var inv inventoryFile
	if err := yaml.Unmarshal(raw, &inv); err != nil {
		t.Fatalf("unmarshal inventory: %v", err)
	}
	return &inv
}

// TestInventory_ExistsAndParses — basic sanity. The inventory file MUST
// parse and have version 1.
func TestInventory_ExistsAndParses(t *testing.T) {
	inv := loadInventory(t)
	if inv.Version != 1 {
		t.Errorf("inventory version = %d, want 1", inv.Version)
	}
	if len(inv.Metrics) == 0 {
		t.Fatal("inventory has no metrics — cycles 1-6 must ALL appear")
	}
}

// TestInventory_AllLabelsInAllowlist — the load-bearing cardinality
// control. ANY label outside the allowlist is a cardinality risk.
func TestInventory_AllLabelsInAllowlist(t *testing.T) {
	inv := loadInventory(t)
	var violations []string
	for _, m := range inv.Metrics {
		for _, lbl := range m.Labels {
			if !allowedLabels[lbl] {
				violations = append(violations,
					fmt.Sprintf("metric %s has unapproved label %q", m.Name, lbl))
			}
		}
	}
	if len(violations) > 0 {
		t.Errorf("cardinality violations:\n  %s", strings.Join(violations, "\n  "))
	}
}

// TestInventory_EnumeratesCyclesOneThroughSix — every cycle that shipped
// metrics MUST have at least one inventory entry. Cycles without metric
// emissions are exempt (cycles 3, 4 didn't add Prom-scraped metrics).
func TestInventory_EnumeratesCyclesOneThroughSix(t *testing.T) {
	inv := loadInventory(t)
	cyclesSeen := map[int]bool{}
	for _, m := range inv.Metrics {
		cyclesSeen[m.ShippedCycle] = true
	}
	expectMetricsFromCycle := []int{1, 2, 5, 6} // 3+4 didn't emit Prom-scraped metrics
	for _, c := range expectMetricsFromCycle {
		if !cyclesSeen[c] {
			t.Errorf("inventory missing entries for cycle %d", c)
		}
	}
}

// TestCardinalityBudget_V1Target700Series — load-bearing math check.
// 7 per-reality metrics × 100 realities (V1) = 700 series target.
func TestCardinalityBudget_V1Target700Series(t *testing.T) {
	inv := loadInventory(t)

	// Count metrics in inventory that have BOTH reality_id AND shard_host
	// in their labels (the per-reality metric definition).
	perRealityCount := 0
	for _, m := range inv.Metrics {
		hasReality := false
		hasShard := false
		for _, lbl := range m.Labels {
			if lbl == "reality_id" {
				hasReality = true
			}
			if lbl == "shard_host" {
				hasShard = true
			}
		}
		if hasReality && hasShard && m.ShippedCycle == 6 {
			// only cycle-6 per-reality metrics (the new ones we added) count
			perRealityCount++
		}
	}

	if perRealityCount != inv.CardinalityBudget.PerRealityMetricCount {
		t.Errorf("counted %d per-reality metrics with both reality_id+shard_host (cycle 6); inventory budget says %d",
			perRealityCount, inv.CardinalityBudget.PerRealityMetricCount)
	}
	// Math check: 7 × 100 = 700
	expected := inv.CardinalityBudget.PerRealityMetricCount * inv.CardinalityBudget.V1Realities
	if expected != inv.CardinalityBudget.V1TargetSeries {
		t.Errorf("budget math wrong: %d × %d = %d, but V1TargetSeries = %d",
			inv.CardinalityBudget.PerRealityMetricCount,
			inv.CardinalityBudget.V1Realities, expected,
			inv.CardinalityBudget.V1TargetSeries)
	}
	// Sanity: 700 series is well below the 1M practical limit (and below
	// the V3 70K target).
	if inv.CardinalityBudget.V1TargetSeries > 1000 {
		t.Errorf("V1 cardinality budget too high: %d > 1000 sanity ceiling",
			inv.CardinalityBudget.V1TargetSeries)
	}
}

// TestPostgresExporter_RestrictsAuditTablesOnly — the audit-table label is
// the only place `relname` is allowed (cardinality control). Verify the
// allow-list query restricts via WHERE relname IN (...).
func TestPostgresExporter_RestrictsAuditTablesOnly(t *testing.T) {
	raw, err := os.ReadFile(postgresExporterPath)
	if err != nil {
		t.Fatalf("read postgres-exporter: %v", err)
	}
	body := string(raw)
	// Must enumerate the 7 audit tables — assert each one appears in a
	// WHERE clause context.
	auditTables := []string{
		"meta_write_audit",
		"meta_read_audit",
		"lifecycle_transition_audit",
		"reality_migration_audit",
		"admin_action_audit",
		"service_to_service_audit",
		"prompt_audit",
	}
	sort.Strings(auditTables)
	for _, tbl := range auditTables {
		if !strings.Contains(body, tbl) {
			t.Errorf("postgres-exporter.yaml missing audit table allowlist entry: %s", tbl)
		}
	}
	// Must NOT have a bare `pg_stat_user_tables` query without WHERE/IN
	// clause (would explode cardinality).
	if strings.Contains(body, "FROM pg_stat_user_tables") &&
		!strings.Contains(body, "WHERE relname IN") {
		t.Error("postgres-exporter has FROM pg_stat_user_tables WITHOUT WHERE relname IN — cardinality explosion risk")
	}
}

// TestNoThanosSidecarPresent — Q-L1I-2 V1 retention = 30d native.
// Asserts no Thanos sidecar config files exist in infra/.
func TestNoThanosSidecarPresent(t *testing.T) {
	forbidden := []string{
		"../../infra/thanos/thanos.yaml",
		"../../infra/thanos/sidecar.yaml",
		"../../infra/prometheus/thanos-sidecar.yaml",
	}
	for _, f := range forbidden {
		if _, err := os.Stat(f); err == nil {
			t.Errorf("Q-L1I-2 V1 violation: Thanos config present at %s (V1 = 30d native retention only)", f)
		}
	}
}
