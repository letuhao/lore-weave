package incidents

import (
	"path/filepath"
	"testing"
	"time"
)

func TestSeverity_IsValid(t *testing.T) {
	for _, s := range []Severity{SEV0, SEV1, SEV2, SEV3} {
		if !s.IsValid() {
			t.Errorf("%s should be valid", s)
		}
	}
	for _, bad := range []Severity{"", "SEV4", "sev0", "P1"} {
		if Severity(bad).IsValid() {
			t.Errorf("%q should be invalid", bad)
		}
	}
}

func TestSeverity_Ordering(t *testing.T) {
	if !SEV0.AtLeastAsSevereAs(SEV1) {
		t.Error("SEV0 must be at least as severe as SEV1")
	}
	if SEV2.AtLeastAsSevereAs(SEV1) {
		t.Error("SEV2 must NOT be at least as severe as SEV1")
	}
	if !SEV1.AtLeastAsSevereAs(SEV1) {
		t.Error("SEV1 must be at least as severe as itself")
	}
	if Severity("bad").AtLeastAsSevereAs(SEV0) {
		t.Error("invalid severity must never be at-least-as-severe")
	}
	if SEV0.Rank() != 0 || SEV3.Rank() != 3 {
		t.Errorf("rank: SEV0=%d SEV3=%d want 0,3", SEV0.Rank(), SEV3.Rank())
	}
}

func TestParseSeverity(t *testing.T) {
	if s, err := ParseSeverity("SEV0"); err != nil || s != SEV0 {
		t.Errorf("ParseSeverity(SEV0) = %v,%v", s, err)
	}
	if _, err := ParseSeverity("SEV9"); err == nil {
		t.Error("ParseSeverity(SEV9) should error")
	}
}

func TestIncidentDeclaredV1_Validate(t *testing.T) {
	now := time.Now()
	good := NewIncidentDeclaredV1("INC-1", SEV0, "db down", "summary", "alert:x", true, []string{"gateway"}, now, "ic-1")
	if err := good.Validate(); err != nil {
		t.Fatalf("good declared event should validate: %v", err)
	}
	if good.Type != TypeIncidentDeclaredV1 {
		t.Error("constructor must stamp type")
	}

	cases := map[string]IncidentDeclaredV1{
		"missing id":   {Type: TypeIncidentDeclaredV1, Severity: SEV0, Title: "x", DeclaredAt: now},
		"bad sev":      {Type: TypeIncidentDeclaredV1, IncidentID: "i", Severity: "SEVX", Title: "x", DeclaredAt: now},
		"missing time": {Type: TypeIncidentDeclaredV1, IncidentID: "i", Severity: SEV0, Title: "x"},
		"bad type":     {Type: "wrong", IncidentID: "i", Severity: SEV0, Title: "x", DeclaredAt: now},
	}
	for name, e := range cases {
		if err := e.Validate(); err == nil {
			t.Errorf("case %q should fail validation", name)
		}
	}
}

func TestIncidentClosedV1_Validate_TimeOrder(t *testing.T) {
	declared := time.Now()
	bad := IncidentClosedV1{
		Type: TypeIncidentClosedV1, IncidentID: "i", Severity: SEV1,
		DeclaredAt: declared, ResolvedAt: declared.Add(-time.Hour),
	}
	if err := bad.Validate(); err == nil {
		t.Error("resolved_at before declared_at must fail")
	}
	good := bad
	good.ResolvedAt = declared.Add(time.Hour)
	if err := good.Validate(); err != nil {
		t.Errorf("valid closed event failed: %v", err)
	}
}

func TestIncidentUpdatedV1_Validate_Status(t *testing.T) {
	now := time.Now()
	for _, st := range []string{"investigating", "identified", "monitoring"} {
		e := IncidentUpdatedV1{Type: TypeIncidentUpdatedV1, IncidentID: "i", Severity: SEV1, Status: st, UpdatedAt: now}
		if err := e.Validate(); err != nil {
			t.Errorf("status %q should be valid: %v", st, err)
		}
	}
	bad := IncidentUpdatedV1{Type: TypeIncidentUpdatedV1, IncidentID: "i", Severity: SEV1, Status: "resolved", UpdatedAt: now}
	if err := bad.Validate(); err == nil {
		t.Error("status=resolved should be invalid (use IncidentClosedV1)")
	}
}

func matrixPath(t *testing.T) string {
	t.Helper()
	return filepath.Join(".", "severity_matrix.yaml")
}

func TestLoadSeverityMatrix(t *testing.T) {
	m, err := LoadSeverityMatrix(matrixPath(t))
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	if len(m.Severities) != 4 {
		t.Fatalf("want 4 severities, got %d", len(m.Severities))
	}
	for _, sev := range AllSeverities() {
		if _, ok := m.Row(sev); !ok {
			t.Errorf("matrix missing row for %s", sev)
		}
	}
}

func TestSeverityMatrix_TTA_AlignsWithPagerDuty(t *testing.T) {
	m, err := LoadSeverityMatrix(matrixPath(t))
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	want := map[Severity]int{SEV0: 5, SEV1: 15, SEV2: 30}
	for sev, mins := range want {
		got, ok := m.TTAMinutes(sev)
		if !ok || got != mins {
			t.Errorf("%s TTA = %d (ok=%v) want %d (must match pagerduty services.yaml)", sev, got, ok, mins)
		}
	}
}

func TestSeverityMatrix_TriggerClassification(t *testing.T) {
	m, err := LoadSeverityMatrix(matrixPath(t))
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	cases := map[string]Severity{
		"data_integrity_loss":  SEV0,
		"audit_hash_mismatch":  SEV0,
		"personal_data_breach": SEV0,
		"canon_injection":      SEV1,
		"degraded_feature":     SEV2,
		"cosmetic":             SEV3,
	}
	for trig, wantSev := range cases {
		got, ok := m.SeverityForTrigger(trig)
		if !ok || got != wantSev {
			t.Errorf("trigger %q → %s (ok=%v) want %s", trig, got, ok, wantSev)
		}
	}
	if _, ok := m.SeverityForTrigger("unknown_trigger"); ok {
		t.Error("unknown trigger should not classify")
	}
}

func TestSeverityMatrix_CommsObligation(t *testing.T) {
	m, err := LoadSeverityMatrix(matrixPath(t))
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	// SEV0 user-visible → status page + auto-banner.
	if !m.RequiresStatusPage(SEV0, true) {
		t.Error("SEV0 user-visible must require status page")
	}
	if m.RequiresStatusPage(SEV0, false) {
		t.Error("SEV0 NOT user-visible must not raise public page")
	}
	if !m.RequiresAutoBanner(SEV1, true) {
		t.Error("SEV1 user-visible must auto-banner")
	}
	// SEV3 never raises a public page.
	if m.RequiresStatusPage(SEV3, true) {
		t.Error("SEV3 must never require status page")
	}
	if m.RequiresAutoBanner(SEV2, true) {
		t.Error("SEV2 must not auto-banner")
	}
}

func TestSeverityMatrix_GDPRBreachCheck(t *testing.T) {
	m, err := LoadSeverityMatrix(matrixPath(t))
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	row, _ := m.Row(SEV0)
	if !row.CommsObligation.GDPRBreachCheck {
		t.Error("SEV0 must enable gdpr_breach_check (personal-data-breach class lives in SEV0)")
	}
}
