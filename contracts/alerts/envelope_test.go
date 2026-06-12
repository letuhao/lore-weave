package alerts

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
)

func validEnvelope() Envelope {
	return Envelope{
		Version:       EnvelopeVersion,
		AlertID:       uuid.New(),
		RuleID:        "LWMetaPostgresPrimaryDown",
		Severity:      SeverityPage,
		Action:        ActionPagerDuty,
		Summary:       "Meta-Postgres PRIMARY down",
		Description:   "Patroni primary failover in progress",
		FiredAtNanos:  1700000000000000000,
		CorrelationID: "trace-123",
		Labels: map[string]string{
			"team": "sre",
			"db":   "meta",
		},
		Annotations: map[string]string{
			"runbook": "runbooks/meta/failover.md",
		},
	}
}

func TestEnvelope_Validate_Happy(t *testing.T) {
	env := validEnvelope()
	if err := env.Validate(); err != nil {
		t.Fatalf("happy: %v", err)
	}
}

func TestEnvelope_Validate_Rejects(t *testing.T) {
	cases := map[string]func(*Envelope){
		"nil envelope":           nil, // handled separately
		"bad version":            func(e *Envelope) { e.Version = 99 },
		"zero alert_id":          func(e *Envelope) { e.AlertID = uuid.Nil },
		"empty rule_id":          func(e *Envelope) { e.RuleID = "" },
		"invalid severity":       func(e *Envelope) { e.Severity = "loud" },
		"invalid action":         func(e *Envelope) { e.Action = "telegram" },
		"empty summary":          func(e *Envelope) { e.Summary = "" },
		"summary too long":       func(e *Envelope) { e.Summary = string(make([]byte, 121)) },
		"implausible fired_at":   func(e *Envelope) { e.FiredAtNanos = 1577836800000000000 },
		"fired_at far future":    func(e *Envelope) { e.FiredAtNanos = time.Now().Add(2 * time.Hour).UnixNano() },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			if mutate == nil {
				var env *Envelope
				if err := env.Validate(); err == nil {
					t.Fatal("nil envelope must reject")
				}
				return
			}
			env := validEnvelope()
			mutate(&env)
			if err := env.Validate(); err == nil {
				t.Fatalf("%s: Validate must reject", name)
			}
		})
	}
}

func TestEnvelope_JSON_RoundTrip(t *testing.T) {
	in := validEnvelope()
	raw, err := json.Marshal(in)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var out Envelope
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out.AlertID != in.AlertID {
		t.Fatal("alert_id round-trip")
	}
	if out.Version != in.Version || out.Severity != in.Severity || out.Action != in.Action {
		t.Fatal("enums round-trip")
	}
	if out.CorrelationID != in.CorrelationID {
		t.Fatal("correlation_id round-trip")
	}
}

func TestEnvelope_JSON_Wire_StableFieldNames(t *testing.T) {
	env := validEnvelope()
	raw, err := json.Marshal(env)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	s := string(raw)
	// Field names are part of the wire contract — any rename is a
	// breaking change. Lock the spelling.
	for _, want := range []string{
		`"v":1`, `"alert_id":`, `"rule_id":`, `"severity":`,
		`"action":`, `"summary":`, `"correlation_id":`, `"fired_at_nanos":`,
	} {
		if !contains(s, want) {
			t.Errorf("wire shape missing %q in: %s", want, s)
		}
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && stringContains(haystack, needle)
}

// stdlib strings.Contains avoided to keep the test small; the loop is
// fast for the assertion sizes here.
func stringContains(haystack, needle string) bool {
	if needle == "" {
		return true
	}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}

func TestSeverityActionIsValid(t *testing.T) {
	for _, s := range []Severity{SeverityPage, SeverityWarn, SeverityInfo, SeveritySilence} {
		if !s.IsValid() {
			t.Errorf("%q must be valid", s)
		}
	}
	if Severity("loud").IsValid() {
		t.Error("loud must be invalid")
	}
	for _, a := range []Action{ActionPagerDuty, ActionSlack, ActionEmail, ActionLogOnly} {
		if !a.IsValid() {
			t.Errorf("%q must be valid", a)
		}
	}
	if Action("telegram").IsValid() {
		t.Error("telegram must be invalid")
	}
}

// ─────────────────────────────────────────────────────────────────────
// AlertEmitter
// ─────────────────────────────────────────────────────────────────────

func TestEmitter_Emit_Happy(t *testing.T) {
	sink := &InMemorySink{}
	em := NewAlertEmitter(sink).WithClock(func() time.Time {
		return time.Unix(0, 1700000000000000000)
	})
	id, err := em.Emit(
		context.Background(),
		"LWMetaPostgresPrimaryDown",
		SeverityPage,
		ActionPagerDuty,
		"Primary down",
		EmitOptions{
			Description:   "patroni",
			CorrelationID: "trace-1",
			Labels:        map[string]string{"team": "sre"},
		},
	)
	if err != nil {
		t.Fatalf("Emit: %v", err)
	}
	if id == uuid.Nil {
		t.Fatal("alert_id zero")
	}
	if sink.Len() != 1 {
		t.Fatalf("sink len: %d", sink.Len())
	}
	got := sink.Sent()[0]
	if got.AlertID != id {
		t.Fatal("alert_id mismatch")
	}
	if got.CorrelationID != "trace-1" {
		t.Fatal("correlation_id propagated")
	}
	if got.Version != EnvelopeVersion {
		t.Fatal("version filled")
	}
	if got.FiredAtNanos != 1700000000000000000 {
		t.Fatal("clock injected")
	}
}

func TestEmitter_Emit_RejectsInvalid(t *testing.T) {
	sink := &InMemorySink{}
	em := NewAlertEmitter(sink).WithClock(func() time.Time {
		return time.Unix(0, 1700000000000000000)
	})

	// Empty rule_id pre-validates.
	if _, err := em.Emit(context.Background(), "", SeverityPage, ActionPagerDuty, "x", EmitOptions{}); !errors.Is(err, ErrInvalidEmit) {
		t.Fatalf("expected ErrInvalidEmit, got %v", err)
	}
	if sink.Len() != 0 {
		t.Fatal("sink must not see rejected emit")
	}

	// Bad severity → fails Validate after construction.
	_, err := em.Emit(context.Background(), "R", "loud", ActionPagerDuty, "x", EmitOptions{})
	if err == nil {
		t.Fatal("bad severity must reject")
	}
	if sink.Len() != 0 {
		t.Fatal("sink must not see invalid envelope")
	}
}

func TestEmitter_Emit_NilSinkOrEmitter(t *testing.T) {
	var em *AlertEmitter
	if _, err := em.Emit(context.Background(), "x", SeverityPage, ActionLogOnly, "x", EmitOptions{}); !errors.Is(err, ErrNoSink) {
		t.Fatalf("nil emitter must return ErrNoSink, got %v", err)
	}
	em = NewAlertEmitter(nil)
	if _, err := em.Emit(context.Background(), "x", SeverityPage, ActionLogOnly, "x", EmitOptions{}); !errors.Is(err, ErrNoSink) {
		t.Fatalf("nil sink must return ErrNoSink, got %v", err)
	}
}

type failSink struct{}

func (f failSink) Send(_ context.Context, _ Envelope) error { return errors.New("boom") }

func TestEmitter_Emit_SurfacesSinkError(t *testing.T) {
	em := NewAlertEmitter(failSink{}).WithClock(func() time.Time {
		return time.Unix(0, 1700000000000000000)
	})
	_, err := em.Emit(context.Background(), "R", SeverityWarn, ActionSlack, "summary", EmitOptions{})
	if err == nil || err.Error() != "boom" {
		t.Fatalf("sink error must propagate, got %v", err)
	}
}
