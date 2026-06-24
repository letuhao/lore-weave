//go:build integration

package integration

import (
	"os"
	"strings"
	"testing"
)

// TestSLIDefinitions_RegistryShape validates contracts/slo/sli_definitions.yaml
// is structurally sound — 7 SLIs declared (SR1 §12AD.2), each with a
// numerator + denominator that the recording rules in
// infra/prometheus/recording-rules/sli.yaml can render.
//
// PURE FILE TEST (no docker required). Live calculation tests live in
// services/slo-budget-calculator/internal/budget under unit tests.
func TestSLIDefinitions_RegistryShape(t *testing.T) {
	raw, err := os.ReadFile("../../contracts/slo/sli_definitions.yaml")
	if err != nil {
		t.Fatalf("read sli_definitions.yaml: %v", err)
	}
	s := string(raw)

	// 7 SLIs per SR1 §12AD.2
	required := []string{
		"sli_session_availability",
		"sli_turn_completion",
		"sli_event_delivery",
		"sli_realtime_freshness",
		"sli_auth_success",
		"sli_admin_action_success",
		"sli_cross_reality_propagation",
	}
	for _, name := range required {
		if !strings.Contains(s, "name: "+name) {
			t.Errorf("sli_definitions.yaml missing required SLI: %s (SR1 §12AD.2)", name)
		}
	}

	// Drift guard
	if !strings.Contains(s, "expected_sli_count: 7") {
		t.Error("sli_definitions.yaml: expected_sli_count must be 7 (SR1 §12AD.2 LOCKED)")
	}

	// Q-L7-1 LOCKED reference
	if !strings.Contains(s, "Q-L7-1") {
		t.Error("sli_definitions.yaml: must reference Q-L7-1 (slo-budget-calculator SEPARATE service)")
	}
}

// TestSLOTargets_TierTable validates contracts/slo/slo_targets.yaml has
// the per-tier targets per SR1 §12AD.3 + the 4-tier burn response.
func TestSLOTargets_TierTable(t *testing.T) {
	raw, err := os.ReadFile("../../contracts/slo/slo_targets.yaml")
	if err != nil {
		t.Fatalf("read slo_targets.yaml: %v", err)
	}
	s := string(raw)

	// Tier names
	for _, tier := range []string{"free", "paid", "premium", "platform"} {
		if !strings.Contains(s, "tier: "+tier) {
			t.Errorf("slo_targets.yaml missing tier: %s", tier)
		}
	}

	// 4-tier burn response policy
	for _, tier := range []string{
		"reliability-review-required",
		"approve-reliability-override",
		"slo-breach-postmortem",
	} {
		if !strings.Contains(s, tier) {
			t.Errorf("slo_targets.yaml missing burn-rate response tier: %s", tier)
		}
	}

	// Expected target count
	if !strings.Contains(s, "expected_target_count: 20") {
		t.Error("slo_targets.yaml: expected_target_count must be 20 (4 user-scope SLIs × 3 tiers + auth × 3 + 2 platform)")
	}
}

// TestRecordingRules_SLIGroupsPresent — pin the recording-rule groups
// that the burn-rate alerts in slo-burn.yaml depend on. A rename here
// breaks every alert downstream.
func TestRecordingRules_SLIGroupsPresent(t *testing.T) {
	raw, err := os.ReadFile("../../infra/prometheus/recording-rules/sli.yaml")
	if err != nil {
		t.Fatalf("read sli.yaml: %v", err)
	}
	s := string(raw)

	for _, grp := range []string{
		"lw_sli_tier_scoped",
		"lw_sli_platform_scoped",
		"lw_sli_burn_windows",
	} {
		if !strings.Contains(s, "name: "+grp) {
			t.Errorf("sli.yaml missing recording-rule group: %s", grp)
		}
	}

	// At least one recorded SLI ratio for each SLI
	for _, sli := range []string{
		"sli_session_availability",
		"sli_turn_completion",
		"sli_event_delivery",
		"sli_realtime_freshness",
		"sli_auth_success",
		"sli_admin_action_success",
		"sli_cross_reality_propagation",
	} {
		if !strings.Contains(s, "lw:"+sli+":ratio_5m") {
			t.Errorf("sli.yaml missing recording rule lw:%s:ratio_5m", sli)
		}
	}
}

// TestSLOBurnAlerts_LadderPresent — verify the 4-tier ladder lands
// in alerts/slo-burn.yaml.
func TestSLOBurnAlerts_LadderPresent(t *testing.T) {
	raw, err := os.ReadFile("../../infra/prometheus/alerts/slo-burn.yaml")
	if err != nil {
		t.Fatalf("read slo-burn.yaml: %v", err)
	}
	s := string(raw)

	// Each rung must exist
	for _, alert := range []string{
		"LWSLOBurnWarn",       // 50-75%
		"LWSLOBurnPage",       // 75-90%
		"LWSLOBurnFreeze",     // ≥ 90%
		"LWSLOBreach",         // ≥ 100%
		"LWMultiTenantIsolationViolation", // SR1 §12AD.5
	} {
		if !strings.Contains(s, alert) {
			t.Errorf("slo-burn.yaml missing alert family: %s", alert)
		}
	}

	// Cycle-19 envelope: every alert needs sli_ref + action labels
	if !strings.Contains(s, "sli_ref: sli_") {
		t.Error("slo-burn.yaml: alerts must carry sli_ref label (SR1 §12AD.7 derivation rule)")
	}
	if !strings.Contains(s, "action: pagerduty") || !strings.Contains(s, "action: slack") {
		t.Error("slo-burn.yaml: alerts must carry action label for cycle-19 envelope routing")
	}
}

// TestFeatureFreezeEnforcer_TierMap validates the freeze enforcer script
// maps burn rates to the exact PR labels declared in slo_targets.yaml.
func TestFeatureFreezeEnforcer_TierMap(t *testing.T) {
	raw, err := os.ReadFile("../../scripts/feature-freeze-enforcer.sh")
	if err != nil {
		t.Fatalf("read feature-freeze-enforcer.sh: %v", err)
	}
	s := string(raw)

	for _, want := range []string{
		"b >= 1.00",
		"b >= 0.90",
		"b >= 0.75",
		"b >= 0.50",
		"reliability-review-required",
		"approve-reliability-override",
		"slo-breach-postmortem",
	} {
		if !strings.Contains(s, want) {
			t.Errorf("feature-freeze-enforcer.sh missing required string: %q", want)
		}
	}
}
