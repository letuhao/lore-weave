package store

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/contracts/alerts"
)

func TestMemoryStore_WriteOutcome_RejectsMissingFields(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()

	if err := s.WriteOutcome(ctx, Outcome{}); err == nil {
		t.Error("want error for missing alert_id; got nil")
	}
	if err := s.WriteOutcome(ctx, Outcome{AlertID: uuid.New()}); err == nil {
		t.Error("want error for missing state; got nil")
	}
}

func TestMemoryStore_WriteOutcome_AssignsOutcomeID(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()
	err := s.WriteOutcome(ctx, Outcome{
		AlertID:  uuid.New(),
		RuleID:   "LWSLOBurnPageSessionAvailability",
		Severity: alerts.SeverityPage,
		Action:   alerts.ActionPagerDuty,
		State:    "received",
	})
	if err != nil {
		t.Fatalf("write: %v", err)
	}
	outs, err := s.ListOutcomes(ctx, 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(outs) != 1 {
		t.Fatalf("want 1 outcome; got %d", len(outs))
	}
	if outs[0].OutcomeID == uuid.Nil {
		t.Error("outcome_id should be auto-assigned when caller passes Nil")
	}
}

func TestMemoryStore_ListOutcomes_NewestFirst(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()
	for i := 0; i < 5; i++ {
		_ = s.WriteOutcome(ctx, Outcome{
			AlertID: uuid.New(),
			RuleID:  "rule-" + string(rune('a'+i)),
			State:   "received",
		})
	}
	outs, err := s.ListOutcomes(ctx, 3)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(outs) != 3 {
		t.Fatalf("want 3 outcomes; got %d", len(outs))
	}
	// Newest first → rule-e, rule-d, rule-c
	if outs[0].RuleID != "rule-e" {
		t.Errorf("newest first: outs[0]=%s; want rule-e", outs[0].RuleID)
	}
	if outs[2].RuleID != "rule-c" {
		t.Errorf("outs[2]=%s; want rule-c", outs[2].RuleID)
	}
}

func TestMemoryStore_WriteSilence_RequiresAuditFields(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()
	now := time.Now()

	cases := []struct {
		name string
		s    Silence
	}{
		{"no actor", Silence{Category: "deploy", Reason: "deploy", AlertMatcher: "x", CreatedAt: now, ExpiresAt: now.Add(1 * time.Hour)}},
		{"no category", Silence{Actor: "u", Reason: "deploy", AlertMatcher: "x", CreatedAt: now, ExpiresAt: now.Add(1 * time.Hour)}},
		{"no reason", Silence{Actor: "u", Category: "deploy", AlertMatcher: "x", CreatedAt: now, ExpiresAt: now.Add(1 * time.Hour)}},
		{"no matcher", Silence{Actor: "u", Category: "deploy", Reason: "r", CreatedAt: now, ExpiresAt: now.Add(1 * time.Hour)}},
	}
	for _, c := range cases {
		if err := s.WriteSilence(ctx, c.s); err == nil {
			t.Errorf("%s: want error; got nil", c.name)
		}
	}
}

func TestMemoryStore_WriteSilence_RejectsBackwardsExpiry(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()
	now := time.Now()
	err := s.WriteSilence(ctx, Silence{
		Actor:        "u",
		Category:     "deploy",
		Reason:       "r",
		AlertMatcher: "x",
		CreatedAt:    now,
		ExpiresAt:    now.Add(-1 * time.Hour), // expires BEFORE created
	})
	if err == nil {
		t.Error("want error for backwards expiry; got nil")
	}
}

func TestMemoryStore_ListActiveSilences_FiltersExpired(t *testing.T) {
	s := NewMemoryStore()
	ctx := context.Background()
	now := time.Now()
	// Active silence
	_ = s.WriteSilence(ctx, Silence{
		Actor: "u", Category: "deploy", Reason: "r", AlertMatcher: "active",
		CreatedAt: now, ExpiresAt: now.Add(1 * time.Hour),
	})
	// Expired silence
	_ = s.WriteSilence(ctx, Silence{
		Actor: "u", Category: "deploy", Reason: "r", AlertMatcher: "expired",
		CreatedAt: now.Add(-2 * time.Hour), ExpiresAt: now.Add(-1 * time.Hour),
	})

	active, err := s.ListActiveSilences(ctx, now)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(active) != 1 {
		t.Fatalf("want 1 active silence; got %d", len(active))
	}
	if active[0].AlertMatcher != "active" {
		t.Errorf("active[0].AlertMatcher=%q; want 'active'", active[0].AlertMatcher)
	}
}
