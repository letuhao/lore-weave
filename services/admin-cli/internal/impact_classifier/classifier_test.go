package impact_classifier

import (
	"errors"
	"testing"
)

func TestOf_Tier1(t *testing.T) {
	p, err := Of("tier-1-destructive")
	if err != nil {
		t.Fatal(err)
	}
	if p.Tier != Tier1Destructive || !p.RequireDryRun || !p.RequireDoubleApproval || !p.RequireTypedConfirm {
		t.Fatalf("tier-1 policy wrong: %+v", p)
	}
	if p.AuditSensitivity != "high" {
		t.Fatalf("want audit high, got %q", p.AuditSensitivity)
	}
}

func TestOf_Tier2(t *testing.T) {
	p, err := Of("tier-2-griefing")
	if err != nil {
		t.Fatal(err)
	}
	if p.RequireDryRun || p.RequireDoubleApproval {
		t.Fatalf("tier-2 should not require dry-run / approval: %+v", p)
	}
	if p.AuditSensitivity != "med" {
		t.Fatalf("want audit med, got %q", p.AuditSensitivity)
	}
}

func TestOf_Tier3(t *testing.T) {
	p, err := Of("tier-3-informational")
	if err != nil {
		t.Fatal(err)
	}
	if p.RequireDryRun || p.RequireDoubleApproval || p.RequireTypedConfirm {
		t.Fatalf("tier-3 should be loose: %+v", p)
	}
}

func TestOf_Unknown(t *testing.T) {
	_, err := Of("tier-99-imaginary")
	if !errors.Is(err, ErrTier) {
		t.Fatalf("want ErrTier, got %v", err)
	}
}
