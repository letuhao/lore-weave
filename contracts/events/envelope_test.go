package events

import (
	"errors"
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
