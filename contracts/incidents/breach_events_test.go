package incidents

import (
	"testing"
	"time"
)

func TestGDPRBreachOpenedV1_Validate(t *testing.T) {
	det := time.Date(2026, 5, 31, 0, 0, 0, 0, time.UTC)
	ok := NewGDPRBreachOpenedV1("INC-1", det, det.Add(72*time.Hour), "email", 10)
	if err := ok.Validate(); err != nil {
		t.Fatalf("valid event rejected: %v", err)
	}
	bad := []GDPRBreachOpenedV1{
		{Type: "wrong", IncidentID: "INC-1", DetectedAt: det, Deadline: det.Add(time.Hour)},
		NewGDPRBreachOpenedV1("", det, det.Add(72*time.Hour), "email", 1),       // empty id
		NewGDPRBreachOpenedV1("INC-1", time.Time{}, det, "email", 1),            // zero detected
		NewGDPRBreachOpenedV1("INC-1", det, det.Add(-time.Hour), "email", 1),    // deadline before detected
		NewGDPRBreachOpenedV1("INC-1", det, det.Add(72*time.Hour), "email", -1), // negative count
	}
	for i, e := range bad {
		if err := e.Validate(); err == nil {
			t.Errorf("bad event #%d should be rejected", i)
		}
	}
}

func TestGDPRDPONoticeRequiredV1_Validate(t *testing.T) {
	ok := NewGDPRDPONoticeRequiredV1("INC-1", "subj", "body", time.Now())
	if err := ok.Validate(); err != nil {
		t.Fatalf("valid event rejected: %v", err)
	}
	for i, e := range []GDPRDPONoticeRequiredV1{
		{Type: "wrong", IncidentID: "INC-1", Subject: "s", Body: "b"},
		NewGDPRDPONoticeRequiredV1("", "s", "b", time.Now()),
		NewGDPRDPONoticeRequiredV1("INC-1", "", "b", time.Now()),
		NewGDPRDPONoticeRequiredV1("INC-1", "s", "", time.Now()),
	} {
		if err := e.Validate(); err == nil {
			t.Errorf("bad dpo-notice #%d should be rejected", i)
		}
	}
}

func TestGDPRBreachDeadlineV1_Validate(t *testing.T) {
	for _, st := range []string{BreachDeadlineApproaching, BreachDeadlineMissed} {
		if err := NewGDPRBreachDeadlineV1("INC-1", st, time.Hour).Validate(); err != nil {
			t.Errorf("state %q should be valid: %v", st, err)
		}
	}
	for i, e := range []GDPRBreachDeadlineV1{
		{Type: "wrong", IncidentID: "INC-1", State: BreachDeadlineMissed},
		NewGDPRBreachDeadlineV1("", BreachDeadlineMissed, 0),
		NewGDPRBreachDeadlineV1("INC-1", "exploded", 0),
	} {
		if err := e.Validate(); err == nil {
			t.Errorf("bad deadline #%d should be rejected", i)
		}
	}
}
