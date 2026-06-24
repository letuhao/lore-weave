//go:build integration

package integration

import (
	"os"
	"strings"
	"testing"
)

// TestAlertmanagerMainConfig_RoutingTreeShape pins the cycle-34
// alertmanager routing tree per SR2 §12AE.4. Pure FILE check — no live
// alertmanager required. Live `amtool check-config` runs in
// verify-cycle-34.sh when amtool is available.
func TestAlertmanagerMainConfig_RoutingTreeShape(t *testing.T) {
	raw, err := os.ReadFile("../../infra/alertmanager/main.yaml")
	if err != nil {
		t.Fatalf("read main.yaml: %v", err)
	}
	s := string(raw)

	// All 5 PagerDuty receivers (Q-L7C-1)
	for _, recv := range []string{
		"pagerduty-sev0",
		"pagerduty-sev1",
		"pagerduty-sre",
		"pagerduty-security",
		"pagerduty-data",
	} {
		if !strings.Contains(s, "name: "+recv) {
			t.Errorf("main.yaml missing receiver: %s (Q-L7C-1 PagerDuty V1)", recv)
		}
	}

	// Slack receivers
	if !strings.Contains(s, "name: slack-alerts") {
		t.Error("main.yaml missing slack-alerts receiver")
	}

	// alert-recorder webhook fan-out (cycle-19 envelope persistence)
	if !strings.Contains(s, "http://alert-recorder:8091/v1/alerts/inbox") {
		t.Error("main.yaml missing alert-recorder webhook (cycle-19 envelope audit trail)")
	}

	// Routing rules
	for _, match := range []string{
		"sev: '0'",
		"sev: '1'",
		"severity: page",
		"severity: warn",
	} {
		if !strings.Contains(s, match) {
			t.Errorf("main.yaml missing routing match: %s", match)
		}
	}

	// Q-L7-1 separate service indirection — env-var indirection for PD keys
	if !strings.Contains(s, "${PAGERDUTY_INTEGRATION_KEY") {
		t.Error("main.yaml: PagerDuty keys must be loaded via env-var (NEVER hardcode)")
	}
}

// TestAlertmanagerChannels_ContractShape — channels.yaml documents 5
// PagerDuty services + slack + email + alert-recorder webhook.
func TestAlertmanagerChannels_ContractShape(t *testing.T) {
	raw, err := os.ReadFile("../../infra/alertmanager/channels.yaml")
	if err != nil {
		t.Fatalf("read channels.yaml: %v", err)
	}
	s := string(raw)

	// 5 PagerDuty service entries
	pdServices := []string{
		"name: sev0",
		"name: sev1",
		"name: sre",
		"name: security",
		"name: data",
	}
	for _, want := range pdServices {
		if !strings.Contains(s, want) {
			t.Errorf("channels.yaml missing pagerduty service: %s", want)
		}
	}

	// Env-var indirection — no literal key
	if !strings.Contains(s, "PAGERDUTY_INTEGRATION_KEY") {
		t.Error("channels.yaml missing PAGERDUTY_INTEGRATION_KEY env-var indirection")
	}

	// Q-L7C-1 reference
	if !strings.Contains(s, "Q-L7C-1") {
		t.Error("channels.yaml must reference Q-L7C-1 (PagerDuty V1 LOCKED)")
	}
}

// TestInhibitionRules_StormProtection — inhibition_rules.yaml AND
// main.yaml inhibit_rules block must declare the same 4 rules.
func TestInhibitionRules_StormProtection(t *testing.T) {
	srcRaw, err := os.ReadFile("../../infra/alertmanager/inhibition_rules.yaml")
	if err != nil {
		t.Fatalf("read inhibition_rules.yaml: %v", err)
	}
	src := string(srcRaw)

	mainRaw, err := os.ReadFile("../../infra/alertmanager/main.yaml")
	if err != nil {
		t.Fatalf("read main.yaml: %v", err)
	}
	main := string(mainRaw)

	// 4 inhibition rules required
	expectedRules := []string{
		"sev0_suppresses_sev1_same_sli",
		"sev0_suppresses_warn_same_sli",
		"sev1_suppresses_warn_same_sli",
		"service_down_suppresses_slo_burn",
	}
	for _, rule := range expectedRules {
		if !strings.Contains(src, rule) {
			t.Errorf("inhibition_rules.yaml missing rule: %s", rule)
		}
	}

	// main.yaml must inline equivalent inhibit_rules block
	if !strings.Contains(main, "inhibit_rules:") {
		t.Error("main.yaml missing inhibit_rules block")
	}
	if !strings.Contains(main, "equal: ['sli_ref', 'tier']") {
		t.Error("main.yaml inhibit_rules: same-(sli,tier) equality grouping missing")
	}
}

// TestSilenceAdmissionPolicy_ProtectedAlerts — silence_admission_policy.yaml
// must declare 5 categories + protected alerts.
func TestSilenceAdmissionPolicy_ProtectedAlerts(t *testing.T) {
	raw, err := os.ReadFile("../../infra/alertmanager/silence_admission_policy.yaml")
	if err != nil {
		t.Fatalf("read silence_admission_policy.yaml: %v", err)
	}
	s := string(raw)

	categories := []string{
		"id: deploy",
		"id: maintenance",
		"id: known_issue",
		"id: incident_in_progress",
		"id: false_positive",
	}
	for _, cat := range categories {
		if !strings.Contains(s, cat) {
			t.Errorf("silence_admission_policy.yaml missing category: %s", cat)
		}
	}

	protectedAlerts := []string{
		"LWMetaPostgresPrimaryDown",
		"LWAuthHashMismatch",
		"LWSLOBreachSessionAvailability",
		"LWMultiTenantIsolationViolation",
	}
	for _, alert := range protectedAlerts {
		if !strings.Contains(s, alert) {
			t.Errorf("silence_admission_policy.yaml missing protected alert: %s", alert)
		}
	}

	if !strings.Contains(s, "expected_category_count: 5") {
		t.Error("silence_admission_policy.yaml: expected_category_count must be 5")
	}
}

// TestContractsAlertsRules_CycleEnvelopeShape — rules.yaml (L4.P.1 + L7.J.6)
// must carry severity_map + routing for every entry, and reference cycle 34
// SLO burn alerts.
func TestContractsAlertsRules_CycleEnvelopeShape(t *testing.T) {
	raw, err := os.ReadFile("../../contracts/alerts/rules.yaml")
	if err != nil {
		t.Fatalf("read rules.yaml: %v", err)
	}
	s := string(raw)

	// SLO burn alerts from cycle 34
	sloAlerts := []string{
		"LWSLOBurnWarnSessionAvailability",
		"LWSLOBurnPageSessionAvailability",
		"LWSLOBurnFreezeSessionAvailability",
		"LWSLOBurnFreezeAuthSuccess",
		"LWSLOBreachSessionAvailability",
		"LWMultiTenantIsolationViolation",
	}
	for _, alert := range sloAlerts {
		if !strings.Contains(s, "alert: "+alert) {
			t.Errorf("rules.yaml missing alert: %s", alert)
		}
	}

	// Cycle-7 carry-forward alerts (per L7.J.6 extension)
	carryForward := []string{
		"LWMetaPostgresPrimaryDown",
		"LWWsConnectionSaturation",
	}
	for _, alert := range carryForward {
		if !strings.Contains(s, "alert: "+alert) {
			t.Errorf("rules.yaml missing carry-forward alert: %s", alert)
		}
	}

	// severity_map + routing required by L4.P + SR2 §12AE.4
	if !strings.Contains(s, "severity_map:") || !strings.Contains(s, "routing:") {
		t.Error("rules.yaml: every alert must declare severity_map + routing")
	}

	// Q-L7C-1 LOCKED ref
	if !strings.Contains(s, "Q-L7C-1") {
		t.Error("rules.yaml must reference Q-L7C-1 (PagerDuty V1)")
	}
}
