package severity_classifier

import (
	"path/filepath"
	"testing"

	"github.com/loreweave/foundation/contracts/incidents"
)

func loadMatrix(t *testing.T) *incidents.SeverityMatrix {
	t.Helper()
	// matrix lives in the contracts module; resolved via the worktree path.
	p := filepath.Join("..", "..", "..", "..", "contracts", "incidents", "severity_matrix.yaml")
	m, err := incidents.LoadSeverityMatrix(p)
	if err != nil {
		t.Fatalf("load matrix: %v", err)
	}
	return m
}

func TestNew_NilMatrix(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Error("New(nil) must error")
	}
}

func TestClassify_ExplicitTrigger(t *testing.T) {
	c, _ := New(loadMatrix(t))
	cases := map[string]incidents.Severity{
		"data_integrity_loss":  incidents.SEV0,
		"audit_hash_mismatch":  incidents.SEV0,
		"personal_data_breach": incidents.SEV0,
		"total_outage":         incidents.SEV0,
		"canon_injection":      incidents.SEV1,
		"security_exposure":    incidents.SEV1,
		"degraded_feature":     incidents.SEV2,
		"cosmetic":             incidents.SEV3,
	}
	for trig, want := range cases {
		got := c.Classify(Signal{Trigger: trig})
		if got.Severity != want {
			t.Errorf("trigger %q → %s want %s", trig, got.Severity, want)
		}
		if got.MatchedTrigger != trig {
			t.Errorf("trigger %q matched_trigger=%q", trig, got.MatchedTrigger)
		}
	}
}

func TestClassify_KeywordFallback(t *testing.T) {
	c, _ := New(loadMatrix(t))
	cases := map[string]incidents.Severity{
		"AuditHashMismatch":      incidents.SEV0,
		"DataIntegrityViolation": incidents.SEV0,
		"CanonInjectionDetected": incidents.SEV1,
		"ElevatedErrorRate":      incidents.SEV2,
	}
	for alert, want := range cases {
		got := c.Classify(Signal{AlertName: alert})
		if got.Severity != want {
			t.Errorf("alert %q → %s want %s (reason=%s)", alert, got.Severity, want, got.Reason)
		}
	}
}

func TestClassify_OperatorLabelOverride(t *testing.T) {
	c, _ := New(loadMatrix(t))
	got := c.Classify(Signal{AlertName: "SomeUnknownThing", Labels: map[string]string{"severity": "SEV0"}})
	if got.Severity != incidents.SEV0 {
		t.Errorf("operator label SEV0 should win, got %s", got.Severity)
	}
	// invalid label falls through to keyword/default
	got2 := c.Classify(Signal{AlertName: "SomeUnknownThing", Labels: map[string]string{"severity": "P1"}})
	if got2.Severity != incidents.SEV2 {
		t.Errorf("invalid label + unknown alert should default SEV2, got %s", got2.Severity)
	}
}

func TestClassify_KnownTriggerBeatsLabel(t *testing.T) {
	c, _ := New(loadMatrix(t))
	// A known SEV0 trigger must NOT be downgraded by a SEV3 operator label.
	got := c.Classify(Signal{Trigger: "audit_hash_mismatch", Labels: map[string]string{"severity": "SEV3"}})
	if got.Severity != incidents.SEV0 {
		t.Errorf("known SEV0 trigger must not be downgraded by label, got %s", got.Severity)
	}
}

func TestClassify_UnknownDefaultsSEV2(t *testing.T) {
	c, _ := New(loadMatrix(t))
	got := c.Classify(Signal{AlertName: "CompletelyNovelAlert"})
	if got.Severity != incidents.SEV2 {
		t.Errorf("unknown alert should default SEV2 (not silently SEV3), got %s", got.Severity)
	}
}

func TestClassify_PropagatesUserVisible(t *testing.T) {
	c, _ := New(loadMatrix(t))
	got := c.Classify(Signal{Trigger: "total_outage", UserVisible: true})
	if !got.UserVisible {
		t.Error("user_visible flag must propagate")
	}
}
