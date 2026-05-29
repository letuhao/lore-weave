package ic_role

import (
	"testing"
	"time"
)

var t0 = time.Unix(1700000000, 0).UTC()

func TestAssign_SeparationEnforced(t *testing.T) {
	if _, err := Assign("INC-1", "u1", "u1", t0); err == nil {
		t.Error("IC == fixer must be rejected (SR2 §12AE.2)")
	}
	a, err := Assign("INC-1", "ic-1", "fix-1", t0)
	if err != nil {
		t.Fatalf("valid assign failed: %v", err)
	}
	if a.ICUserID != "ic-1" || a.FixerUserID != "fix-1" {
		t.Errorf("assignment = %+v", a)
	}
}

func TestAssign_Validates(t *testing.T) {
	if _, err := Assign("", "ic", "fix", t0); err == nil {
		t.Error("empty incident id must error")
	}
	if _, err := Assign("INC-1", "ic", "fix", time.Time{}); err == nil {
		t.Error("zero time must error")
	}
}

func TestHandoff(t *testing.T) {
	a, _ := Assign("INC-1", "ic-1", "fix-1", t0)
	if err := a.Handoff("ic-2", "shift change", t0.Add(time.Hour)); err != nil {
		t.Fatalf("handoff: %v", err)
	}
	if a.ICUserID != "ic-2" {
		t.Errorf("IC after handoff = %q want ic-2", a.ICUserID)
	}
	if len(a.Handoffs) != 1 || a.Handoffs[0].FromUserID != "ic-1" {
		t.Errorf("handoff chain = %+v", a.Handoffs)
	}
}

func TestHandoff_CannotHandToFixer(t *testing.T) {
	a, _ := Assign("INC-1", "ic-1", "fix-1", t0)
	if err := a.Handoff("fix-1", "x", t0); err == nil {
		t.Error("handing IC to current fixer breaks separation — must error")
	}
}

func TestHandoff_AlreadyIC(t *testing.T) {
	a, _ := Assign("INC-1", "ic-1", "fix-1", t0)
	if err := a.Handoff("ic-1", "x", t0); err == nil {
		t.Error("handing to current IC must error")
	}
}

func TestAssignFixer_Separation(t *testing.T) {
	a, _ := Assign("INC-1", "ic-1", "", t0)
	if err := a.AssignFixer("ic-1"); err == nil {
		t.Error("fixer == IC must error")
	}
	if err := a.AssignFixer("fix-9"); err != nil {
		t.Errorf("valid fixer assign failed: %v", err)
	}
}

func TestLogDecision(t *testing.T) {
	a, _ := Assign("INC-1", "ic-1", "fix-1", t0)
	if err := a.LogDecision("rollback deploy 42", t0); err != nil {
		t.Fatalf("log decision: %v", err)
	}
	if err := a.LogDecision("", t0); err == nil {
		t.Error("empty decision must error")
	}
	if len(a.Decisions) != 1 || a.Decisions[0].By != "ic-1" {
		t.Errorf("decision log = %+v", a.Decisions)
	}
}
