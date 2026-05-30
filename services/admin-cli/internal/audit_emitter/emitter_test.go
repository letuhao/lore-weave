package audit_emitter

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestMemorySink_RecordsAll(t *testing.T) {
	s := NewMemorySink()
	for i := 0; i < 5; i++ {
		_ = s.Write(context.Background(), Action{CommandName: "x"})
	}
	if s.Count() != 5 {
		t.Fatalf("want 5, got %d", s.Count())
	}
	rows := s.All()
	if len(rows) != 5 {
		t.Fatalf("All() len = %d", len(rows))
	}
}

func TestEmitter_BeforeAfterSequence(t *testing.T) {
	now := time.Unix(1700000000, 0)
	sink := NewMemorySink()
	e := New(sink, func() time.Time { now = now.Add(time.Second); return now })
	a, err := e.Before(context.Background(), Action{CommandName: "reality stats"})
	if err != nil {
		t.Fatalf("Before: %v", err)
	}
	if a.Outcome != "started" {
		t.Fatalf("want started, got %q", a.Outcome)
	}
	if err := e.After(context.Background(), a); err != nil {
		t.Fatalf("After: %v", err)
	}
	if sink.Count() != 2 {
		t.Fatalf("want 2 rows, got %d", sink.Count())
	}
	rows := sink.All()
	if rows[1].Outcome != "succeeded" {
		t.Fatalf("want succeeded, got %q", rows[1].Outcome)
	}
}

func TestEmitter_ScrubsReason_PRR45(t *testing.T) {
	sink := NewMemorySink()
	e := New(sink, func() time.Time { return time.Unix(1700000000, 0) })

	raw := "user complained from alice@example.com about card 4111 1111 1111 1111"
	a, err := e.Before(context.Background(), Action{CommandName: "erasure user-erasure", Reason: raw})
	if err != nil {
		t.Fatalf("Before: %v", err)
	}
	// Returned Action keeps the RAW reason for the caller's local use.
	if a.Reason != raw {
		t.Errorf("returned Action.Reason should be raw, got %q", a.Reason)
	}
	// Persisted row must be PII-redacted.
	persisted := sink.All()[0].Reason
	if strings.Contains(persisted, "alice@example.com") || strings.Contains(persisted, "4111") {
		t.Errorf("persisted reason leaked PII: %q", persisted)
	}
	if !strings.Contains(persisted, "[EMAIL]") || !strings.Contains(persisted, "[CC]") {
		t.Errorf("persisted reason not redacted: %q", persisted)
	}
}

func TestEmitter_Failure(t *testing.T) {
	sink := NewMemorySink()
	e := New(sink, nil)
	a, _ := e.Before(context.Background(), Action{CommandName: "reality force-close"})
	if err := e.Failure(context.Background(), a, "abc123"); err != nil {
		t.Fatalf("Failure: %v", err)
	}
	rows := sink.All()
	if rows[1].Outcome != "failed" || rows[1].ErrorDetailHash != "abc123" {
		t.Fatalf("failure row wrong: %+v", rows[1])
	}
}
