package events

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestEnvelope_Validate_Happy(t *testing.T) {
	e := goodEnvelope()
	if err := e.Validate(); err != nil {
		t.Fatalf("happy envelope rejected: %v", err)
	}
}

func TestEnvelope_Validate_RejectsBadFields(t *testing.T) {
	tests := []struct {
		name    string
		mutate  func(*Envelope)
		matches string
	}{
		{"zero event_id", func(e *Envelope) { e.EventID = uuid.Nil }, "event_id"},
		{"empty event_type", func(e *Envelope) { e.EventType = "" }, "event_type"},
		{"version 0", func(e *Envelope) { e.EventVersion = 0 }, "event_version"},
		{"empty aggregate_id", func(e *Envelope) { e.AggregateID = "" }, "aggregate_id"},
		{"empty aggregate_type", func(e *Envelope) { e.AggregateType = "" }, "aggregate_type"},
		{"zero reality_id", func(e *Envelope) { e.RealityID = uuid.Nil }, "reality_id"},
		{"zero recorded_at", func(e *Envelope) { e.RecordedAt = time.Time{} }, "recorded_at"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			e := goodEnvelope()
			tt.mutate(&e)
			err := e.Validate()
			if err == nil {
				t.Fatalf("expected error for %s", tt.name)
			}
			var typed ErrInvalidEnvelopeText
			if !errors.As(err, &typed) {
				t.Errorf("expected ErrInvalidEnvelopeText, got %T", err)
			}
			if !contains2(string(typed), tt.matches) {
				t.Errorf("error %q does not contain %q", string(typed), tt.matches)
			}
		})
	}
}

func goodEnvelope() Envelope {
	now := time.Now().UTC()
	return Envelope{
		EventID:          uuid.New(),
		EventType:        "npc.said",
		EventVersion:     2,
		AggregateID:      uuid.New().String(),
		AggregateType:    "npc",
		AggregateVersion: 1,
		RealityID:        uuid.New(),
		OccurredAt:       now,
		RecordedAt:       now,
		Payload:          map[string]any{"text": "hello"},
	}
}

// The RLS-A13 ruleset pin is OPTIONAL by presence and STRICT by format.
//
// Optional because this envelope is the whole platform's wire shape: canon
// writes, Forge edits and admin actions have no ruleset governing them, and a
// required field would break every existing producer (I14 additive rule). The
// obligation to always stamp it belongs to the game writer, where it is
// enforced, not to the shared validator.
//
// Strict about format because the digest is compared and joined as TEXT. A
// mixed-case or truncated value silently fails to equal the same digest written
// by another producer — RLS-D5's "worse than no digest, because it fails loudly
// and WRONGLY", where every replay reports a mismatch that isn't one.
func TestEnvelopeRulesetDigestFormat(t *testing.T) {
	base := func() Envelope {
		return Envelope{
			EventID:          uuid.New(),
			EventType:        "turn.resolved",
			EventVersion:     1,
			AggregateID:      "enc-1",
			AggregateType:    "combat_session",
			AggregateVersion: 1,
			RealityID:        uuid.New(),
			RecordedAt:       time.Now(),
		}
	}
	valid := "807d5b5213f0707ff1e0f2e359d1b22463ce074d914ab98646440a4f62f4fe01"

	cases := []struct {
		name   string
		digest string
		ok     bool
	}{
		{"absent is legal — not every event comes from a pinned island", "", true},
		{"64 lowercase hex", valid, true},
		{"uppercase would not match the same digest written lowercase", strings.ToUpper(valid), false},
		{"truncated", valid[:63], false},
		{"too long", valid + "0", false},
		{"non-hex", strings.Repeat("z", 64), false},
	}
	for _, c := range cases {
		e := base()
		e.RulesetDigest = c.digest
		err := e.Validate()
		if c.ok && err != nil {
			t.Errorf("%s: want valid, got %v", c.name, err)
		}
		if !c.ok && err == nil {
			t.Errorf("%s: want rejected, got nil", c.name)
		}
	}
}
