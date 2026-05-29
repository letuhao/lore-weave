package dry_run

import (
	"errors"
	"strings"
	"testing"
)

func TestEnforceGate_NotRequired_AlwaysOK(t *testing.T) {
	if err := EnforceGate("cmd", false, false, false); err != nil {
		t.Fatal("non-required gate should pass with no flags")
	}
}

func TestEnforceGate_RequiredNeedsFlag(t *testing.T) {
	err := EnforceGate("reality force-close", true, false, false)
	if err == nil || !errors.Is(err, ErrDryRun) {
		t.Fatalf("want ErrDryRun, got %v", err)
	}
	if !strings.Contains(err.Error(), "--dry-run") {
		t.Fatalf("want --dry-run message, got %v", err)
	}
}

func TestEnforceGate_DryRunAccepted(t *testing.T) {
	if err := EnforceGate("x", true, true, false); err != nil {
		t.Fatalf("--dry-run should pass gate: %v", err)
	}
}

func TestEnforceGate_ConfirmAccepted(t *testing.T) {
	if err := EnforceGate("x", true, false, true); err != nil {
		t.Fatalf("--confirm should pass gate: %v", err)
	}
}

func TestPlan_FormatContainsCoreFields(t *testing.T) {
	p := Plan{
		Command:        "reality force-close",
		PredictedRows:  42,
		PredictedSteps: []string{"freeze writes", "emit audit"},
		Warnings:       []string{"reality has 3 open sessions"},
		WriteBlockedOK: true,
	}
	out := p.Format()
	for _, want := range []string{"reality force-close", "42", "freeze writes", "open sessions", "write-blocked: true"} {
		if !strings.Contains(out, want) {
			t.Errorf("Format missing %q in %q", want, out)
		}
	}
}
