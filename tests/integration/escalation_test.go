//go:build integration

package integration

import (
	"os"
	"strings"
	"testing"
)

// TestPagerDutyServicesMatchAlertmanagerChannels — L7.C.1 invariant.
// The 5 PagerDuty services declared in infra/pagerduty/services.yaml MUST
// match the 5 services declared in cycle-34 infra/alertmanager/channels.yaml.
// This is the cross-cycle wiring contract.
func TestPagerDutyServicesMatchAlertmanagerChannels(t *testing.T) {
	pdRaw, err := os.ReadFile("../../infra/pagerduty/services.yaml")
	if err != nil {
		t.Fatalf("read pagerduty services.yaml: %v", err)
	}
	chRaw, err := os.ReadFile("../../infra/alertmanager/channels.yaml")
	if err != nil {
		t.Fatalf("read alertmanager channels.yaml: %v", err)
	}
	pdSvc := string(pdRaw)
	chSvc := string(chRaw)

	// 5 service names + their env-var bindings must appear in both.
	for _, pair := range []struct {
		Name string
		Env  string
	}{
		{"sev0", "PAGERDUTY_INTEGRATION_KEY_SEV0"},
		{"sev1", "PAGERDUTY_INTEGRATION_KEY_SEV1"},
		{"sre", "PAGERDUTY_INTEGRATION_KEY_SRE"},
		{"security", "PAGERDUTY_INTEGRATION_KEY_SECURITY"},
		{"data", "PAGERDUTY_INTEGRATION_KEY_DATA"},
	} {
		if !strings.Contains(pdSvc, "name: "+pair.Name) {
			t.Errorf("services.yaml missing service: %s", pair.Name)
		}
		if !strings.Contains(pdSvc, "env: "+pair.Env) {
			t.Errorf("services.yaml missing env binding: %s", pair.Env)
		}
		if !strings.Contains(chSvc, "name: "+pair.Name) {
			t.Errorf("channels.yaml missing service: %s (cycle 34 carry-forward)", pair.Name)
		}
		if !strings.Contains(chSvc, "env: "+pair.Env) {
			t.Errorf("channels.yaml missing env binding: %s (cycle 34 carry-forward)", pair.Env)
		}
	}
	if !strings.Contains(pdSvc, "expected_service_count: 5") {
		t.Error("services.yaml drift guard missing: expected_service_count: 5")
	}
}

// TestEscalationPolicy_5Policies pins the 5 PagerDuty escalation policies
// + their layer structure per SR2 §12AE.4 + oncall-sla.md TTA targets.
func TestEscalationPolicy_5Policies(t *testing.T) {
	raw, err := os.ReadFile("../../infra/pagerduty/escalation_policy.yaml")
	if err != nil {
		t.Fatalf("read escalation_policy.yaml: %v", err)
	}
	s := string(raw)

	// 5 policies present
	for _, p := range []string{
		"sev0-immediate",
		"sev1-15min-tta",
		"sre-primary-rotation",
		"security-oncall",
		"data-oncall",
	} {
		if !strings.Contains(s, "id: "+p) {
			t.Errorf("escalation_policy.yaml missing policy: %s", p)
		}
	}

	// Drift guard
	if !strings.Contains(s, "expected_policy_count: 5") {
		t.Error("escalation_policy.yaml missing drift guard expected_policy_count: 5")
	}

	// TTA layer-2 delays must match oncall-sla.md targets.
	// SEV0 layer 2 = 5min, SEV1 layer 2 = 15min, SRE layer 2 = 30min,
	// security layer 2 = 5min, data layer 2 = 5min.
	for _, want := range []string{
		"escalation_delay_in_minutes: 5",   // sev0 layer 2 / security / data
		"escalation_delay_in_minutes: 15",  // sev1 layer 2
		"escalation_delay_in_minutes: 30",  // sre default layer 2
	} {
		if !strings.Contains(s, want) {
			t.Errorf("escalation_policy.yaml missing TTA layer delay: %s", want)
		}
	}

	// Layer-3 founder escalation MUST be present in all SEV0-ish policies
	// (founder-direct). The actual user reference is var.founder_user_id in
	// the Terraform; here we just confirm the yaml lists founder-direct
	// for sev0/sev1/security/data.
	founderDirectCount := strings.Count(s, "id: founder-direct")
	if founderDirectCount < 4 {
		t.Errorf("escalation_policy.yaml: founder-direct appears %d times; expected >= 4 (sev0/sev1/security/data + sre)", founderDirectCount)
	}
}

// TestRotationSchedule_Phases pins the 3 rotation schedules (V1 / V1+30d / V2+)
// + exactly 1 active.
func TestRotationSchedule_Phases(t *testing.T) {
	raw, err := os.ReadFile("../../infra/pagerduty/rotation_schedule.yaml")
	if err != nil {
		t.Fatalf("read rotation_schedule.yaml: %v", err)
	}
	s := string(raw)

	for _, phase := range []string{"phase: v1", "phase: v1plus30d", "phase: v2plus"} {
		if !strings.Contains(s, phase) {
			t.Errorf("rotation_schedule.yaml missing phase declaration: %s", phase)
		}
	}
	if !strings.Contains(s, "expected_schedule_count: 3") {
		t.Error("rotation_schedule.yaml drift guard missing: expected_schedule_count: 3")
	}
	if !strings.Contains(s, "expected_active_schedule: solo-dev-247") {
		t.Error("rotation_schedule.yaml: expected_active_schedule != solo-dev-247 (V1 phase)")
	}

	// Active flag — exactly 1 schedule has active: true
	activeTrue := strings.Count(s, "active: true")
	activeFalse := strings.Count(s, "active: false")
	if activeTrue != 1 {
		t.Errorf("rotation_schedule.yaml: %d schedules active: true; expected 1", activeTrue)
	}
	if activeFalse != 2 {
		t.Errorf("rotation_schedule.yaml: %d schedules active: false; expected 2 (V1+30d + V2+)", activeFalse)
	}
}

// TestOncallRoutingExtension_ReceiverCoverage pins the cross-cycle wiring:
// every alertmanager receiver in main.yaml maps to a PagerDuty escalation
// policy in escalation_policy.yaml.
func TestOncallRoutingExtension_ReceiverCoverage(t *testing.T) {
	extRaw, err := os.ReadFile("../../infra/alertmanager/oncall_routing_extension.yaml")
	if err != nil {
		t.Fatalf("read oncall_routing_extension.yaml: %v", err)
	}
	policyRaw, err := os.ReadFile("../../infra/pagerduty/escalation_policy.yaml")
	if err != nil {
		t.Fatalf("read escalation_policy.yaml: %v", err)
	}
	mainRaw, err := os.ReadFile("../../infra/alertmanager/main.yaml")
	if err != nil {
		t.Fatalf("read main.yaml: %v", err)
	}
	ext := string(extRaw)
	policy := string(policyRaw)
	main := string(mainRaw)

	// 5 receivers in extension + each maps to a policy + each receiver in main.yaml
	for _, recv := range []string{
		"pagerduty-sev0",
		"pagerduty-sev1",
		"pagerduty-sre",
		"pagerduty-security",
		"pagerduty-data",
	} {
		if !strings.Contains(ext, recv) {
			t.Errorf("oncall_routing_extension.yaml missing receiver: %s", recv)
		}
		if !strings.Contains(main, "name: "+recv) {
			t.Errorf("main.yaml (cycle 34) missing receiver: %s", recv)
		}
	}
	for _, p := range []string{
		"sev0-immediate",
		"sev1-15min-tta",
		"sre-primary-rotation",
		"security-oncall",
		"data-oncall",
	} {
		if !strings.Contains(ext, p) {
			t.Errorf("oncall_routing_extension.yaml missing policy reference: %s", p)
		}
		if !strings.Contains(policy, "id: "+p) {
			t.Errorf("escalation_policy.yaml missing policy id: %s", p)
		}
	}
	if !strings.Contains(ext, "expected_receiver_count: 5") {
		t.Error("oncall_routing_extension.yaml drift guard missing: expected_receiver_count: 5")
	}
}

// TestOncallSLAInternal — Q-L7C-2 invariant pin.
// Required separately from cycle-34 alert_routing_test (that test pins
// existence + LOCKED banner; this test pins TTA-table alignment with the
// escalation policy delays declared in this cycle).
func TestOncallSLAInternal_TTAAlignment(t *testing.T) {
	slaRaw, err := os.ReadFile("../../docs/governance/oncall-sla.md")
	if err != nil {
		t.Fatalf("read oncall-sla.md: %v", err)
	}
	sla := string(slaRaw)

	// Internal-only banner from cycle 34.
	if !strings.Contains(sla, "internal-only") {
		t.Error("oncall-sla.md missing internal-only marker (Q-L7C-2)")
	}

	// TTA targets that must be referenced (the canonical numbers the
	// escalation policies map to via layer-2 delays).
	for _, target := range []string{
		"5 min",   // SEV0 business hours
		"15 min",  // SEV1 business hours
		"30 min",  // SEV2 business hours
	} {
		if !strings.Contains(sla, target) {
			t.Errorf("oncall-sla.md missing TTA target: %s", target)
		}
	}
}

// TestRunbookFrontmatter_27StubsPresent pins the L7.B 27-runbook gate.
// Walks docs/sre/runbooks/ and counts non-template .md files.
func TestRunbookFrontmatter_27StubsPresent(t *testing.T) {
	entries, err := os.ReadDir("../../docs/sre/runbooks")
	if err != nil {
		t.Fatalf("read docs/sre/runbooks: %v", err)
	}
	count := 0
	stubsByCategory := map[string]int{}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		sub, err := os.ReadDir("../../docs/sre/runbooks/" + e.Name())
		if err != nil {
			continue
		}
		for _, f := range sub {
			if f.IsDir() {
				continue
			}
			name := f.Name()
			if !strings.HasSuffix(name, ".md") {
				continue
			}
			count++
			stubsByCategory[e.Name()]++
		}
	}
	if count != 27 {
		t.Errorf("docs/sre/runbooks/: %d runbooks; SR3 §12AF.4 V1 launch gate requires exactly 27", count)
	}
	// Per layer-plan L7.B.5-L7.B.15:
	expected := map[string]int{
		"auth":         3,
		"ws":           3,
		"meta":         3,
		"publisher":    2,
		"projection":   2,
		"llm-provider": 3,
		"canon":        2,
		"admin":        2,
		"reality":      3,
		"deploy":       2,
		"capacity":     2,
	}
	for cat, want := range expected {
		if got := stubsByCategory[cat]; got != want {
			t.Errorf("runbook category %s: got %d; want %d (per L7.B layer plan)", cat, got, want)
		}
	}
}
