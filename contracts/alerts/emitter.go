package alerts

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
)

// AlertSink is the abstraction over the actual emission target —
// typically a wrapper around the alertmanager push HTTP API, or a stub
// that records to a buffered channel in tests.
//
// Implementations MUST be safe for concurrent use. They MAY drop on
// back-pressure but MUST signal the drop via an error so dashboards can
// surface "alerts not delivered" as itself an alert.
type AlertSink interface {
	Send(ctx context.Context, env Envelope) error
}

// AlertEmitter is the runtime helper services use to fire alerts. It
// auto-fills version + alert_id + fired_at_nanos so the call-site
// becomes a 4-field assertion (rule_id + severity + action + summary).
type AlertEmitter struct {
	sink AlertSink
	now  func() time.Time
	mu   sync.Mutex
}

// NewAlertEmitter wraps a sink. Pass NewClockOverride for deterministic
// tests; nil = wall-clock time.
func NewAlertEmitter(sink AlertSink) *AlertEmitter {
	return &AlertEmitter{sink: sink, now: time.Now}
}

// WithClock overrides the time source for tests.
func (e *AlertEmitter) WithClock(now func() time.Time) *AlertEmitter {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.now = now
	return e
}

// EmitOptions carries optional fields the helper does not require but
// callers usually want to set.
type EmitOptions struct {
	Description   string
	Labels        map[string]string
	Annotations   map[string]string
	CorrelationID string
}

// Emit builds + sends an Envelope. Returns the alert_id on success so
// the caller can correlate.
//
// REJECTS invalid input BEFORE calling sink.Send (Validate runs first)
// so a malformed alert never lands in the pipeline. ErrInvalidEmit is
// the sentinel returned on validation failures (callers may wrap it).
func (e *AlertEmitter) Emit(
	ctx context.Context,
	ruleID string,
	severity Severity,
	action Action,
	summary string,
	opts EmitOptions,
) (uuid.UUID, error) {
	if e == nil || e.sink == nil {
		return uuid.Nil, ErrNoSink
	}
	if ruleID == "" {
		return uuid.Nil, ErrInvalidEmit
	}
	env := Envelope{
		Version:       EnvelopeVersion,
		AlertID:       uuid.New(),
		RuleID:        ruleID,
		Severity:      severity,
		Action:        action,
		Summary:       summary,
		Description:   opts.Description,
		Labels:        opts.Labels,
		Annotations:   opts.Annotations,
		CorrelationID: opts.CorrelationID,
		FiredAtNanos:  e.now().UnixNano(),
	}
	if err := env.Validate(); err != nil {
		return uuid.Nil, err
	}
	if err := e.sink.Send(ctx, env); err != nil {
		return uuid.Nil, err
	}
	return env.AlertID, nil
}

// ErrNoSink is returned when Emit is called on an AlertEmitter that has
// no AlertSink bound (programmer bug — caller forgot to wire a sink).
var ErrNoSink = errors.New("alerts: AlertEmitter has no sink bound")

// ErrInvalidEmit is returned for emit-time precondition failures (empty
// rule_id, etc.) BEFORE the envelope is constructed.
var ErrInvalidEmit = errors.New("alerts: emit precondition failed")

// ─────────────────────────────────────────────────────────────────────
// InMemorySink — test-only reference implementation.
// ─────────────────────────────────────────────────────────────────────

// InMemorySink records every Send for test assertions. Safe for
// concurrent use.
type InMemorySink struct {
	mu   sync.Mutex
	sent []Envelope
}

// Send implements AlertSink. Records env into the in-memory buffer.
func (s *InMemorySink) Send(_ context.Context, env Envelope) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sent = append(s.sent, env)
	return nil
}

// Sent returns a copy of the recorded envelopes.
func (s *InMemorySink) Sent() []Envelope {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Envelope, len(s.sent))
	copy(out, s.sent)
	return out
}

// Len returns the number of recorded envelopes.
func (s *InMemorySink) Len() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.sent)
}
