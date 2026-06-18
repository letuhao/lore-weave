package meta

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestPkColumnFor_L1A4Tables — cycle 7 regression. All 8 new billing+SRE
// tables must round-trip through pkColumnFor with the documented PK column.
func TestPkColumnFor_L1A4Tables(t *testing.T) {
	cases := map[string]string{
		// Billing
		"user_cost_ledger":   "ledger_id",
		"user_daily_cost":    "user_ref_id", // composite PK; primary identity column
		"user_queue_metrics": "user_ref_id",
		// SRE
		"incidents":         "incident_id",
		"feature_flags":     "flag_name",
		"deploy_audit":      "deploy_id",
		"shard_utilization": "snapshot_id",
		"scaling_events":    "scaling_event_id",
	}
	for table, want := range cases {
		if got := pkColumnFor(table); got != want {
			t.Errorf("pkColumnFor(%q) = %q, want %q", table, got, want)
		}
	}
}

// TestAllowlist_L1A4Tables_Loaded — cycle 7 regression. The 8 new L1.A-4
// tables MUST appear in events_allowlist.yaml; defense-in-depth check.
func TestAllowlist_L1A4Tables_Loaded(t *testing.T) {
	// Find the events_allowlist.yaml — relative to this test file (cwd is
	// contracts/meta when `go test ./...` runs in the contracts/meta module).
	path, err := filepath.Abs("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("abs path: %v", err)
	}
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read allowlist: %v", err)
	}
	body := string(b)
	for _, table := range []string{
		"user_cost_ledger", "user_daily_cost", "user_queue_metrics",
		"incidents", "feature_flags", "deploy_audit",
		"shard_utilization", "scaling_events",
	} {
		marker := "table: " + table
		if !strings.Contains(body, marker) {
			t.Errorf("events_allowlist.yaml missing entry for %q", table)
		}
	}
}

// TestAllowlist_BillingTablesEmit — billing_ledger MUST emit an outbox event
// per Q-L1A-3 (full audit) so dashboards + budget enforcement work.
func TestAllowlist_BillingTablesEmit(t *testing.T) {
	path, _ := filepath.Abs("events_allowlist.yaml")
	b, _ := os.ReadFile(path)
	body := string(b)
	// user_cost_ledger entry must include billing.charge.recorded
	if !strings.Contains(body, "billing.charge.recorded") {
		t.Errorf("user_cost_ledger missing billing.charge.recorded outbox emission")
	}
	if !strings.Contains(body, "billing.daily.capped") {
		t.Errorf("user_daily_cost missing billing.daily.capped outbox emission")
	}
}

// TestAllowlist_AuditTablesEventsEmpty — defense-in-depth: audit tables
// MUST NEVER outbox (would infinite-loop the audit chain). Audit tables
// already shipped in cycle 4 — this test pins the invariant from cycle 7's
// perspective (billing has the same audit responsibility now).
func TestAllowlist_AuditTablesEventsEmpty(t *testing.T) {
	path, _ := filepath.Abs("events_allowlist.yaml")
	b, _ := os.ReadFile(path)
	body := string(b)
	for _, auditTable := range []string{
		"meta_write_audit", "meta_read_audit", "admin_action_audit",
		"service_to_service_audit", "prompt_audit",
	} {
		idx := strings.Index(body, "table: "+auditTable)
		if idx < 0 {
			t.Errorf("allowlist missing %q", auditTable)
			continue
		}
		// Take the next 5 lines after the marker; events: [] must appear
		end := idx + 800
		if end > len(body) {
			end = len(body)
		}
		segment := body[idx:end]
		if !strings.Contains(segment, "events: []") {
			t.Errorf("%q must have events: [] (never outbox); segment: %s", auditTable, segment[:300])
		}
	}
}
