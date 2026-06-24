package tracing

import (
	"context"
	"errors"
	"regexp"
	"sync"
	"time"
)

// SpanKind classifies the span's role in the request flow. Mirrors OTel.
type SpanKind int

const (
	// SpanKindInternal — work inside the service (default).
	SpanKindInternal SpanKind = iota
	// SpanKindServer — request inbound from a client/upstream.
	SpanKindServer
	// SpanKindClient — RPC outbound to a downstream service.
	SpanKindClient
	// SpanKindProducer — sent to a queue/topic (Redis Streams, NATS).
	SpanKindProducer
	// SpanKindConsumer — read from a queue/topic.
	SpanKindConsumer
)

// String returns the lowercase wire-form.
func (k SpanKind) String() string {
	switch k {
	case SpanKindInternal:
		return "internal"
	case SpanKindServer:
		return "server"
	case SpanKindClient:
		return "client"
	case SpanKindProducer:
		return "producer"
	case SpanKindConsumer:
		return "consumer"
	}
	return "unknown"
}

// Status is the span outcome. Mirrors OTel.
type Status int

const (
	StatusUnset Status = iota
	StatusOK
	StatusError
)

func (s Status) String() string {
	switch s {
	case StatusUnset:
		return "unset"
	case StatusOK:
		return "ok"
	case StatusError:
		return "error"
	}
	return "invalid"
}

// spanNameRegex enforces the cycle 19 L4.H trace span-naming convention:
// snake_case segments joined by dots. E.g., `auth_service.handler.login`.
//
// Each segment: lowercase ASCII letter/digit/underscore.
var spanNameRegex = regexp.MustCompile(`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`)

// ErrInvalidSpanName is returned by StartSpan when the name fails the
// cycle-19 convention. Forced via Tracer to keep emit-time discipline.
var ErrInvalidSpanName = errors.New("tracing: span name must match cycle-19 convention `^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$`")

// Span is the typed span surface. Methods are safe to call concurrently
// from multiple goroutines on the same Span value.
type Span interface {
	// SpanContext returns the TraceContext for this span (TraceID +
	// THIS span's SpanID — not the parent's).
	SpanContext() TraceContext

	// SetAttribute sets a key/value attribute. The value flows through
	// the Redactor (if configured) when the key is in the PII allow-list
	// (auth.user_id, http.user.email, etc.) — services bind a redactor
	// via Tracer config (see tracer.go).
	SetAttribute(key string, value any)

	// RecordError attaches an error to the span and sets Status=Error.
	RecordError(err error)

	// SetStatus updates the span status.
	SetStatus(s Status)

	// End closes the span and submits to the Exporter. Calling End more
	// than once is a no-op (defensive).
	End()
}

// InMemorySpan is the test/reference impl of Span.
type InMemorySpan struct {
	mu         sync.Mutex
	ctx        TraceContext
	name       string
	kind       SpanKind
	startedAt  time.Time
	endedAt    time.Time
	ended      bool
	status     Status
	errs       []error
	attrs      map[string]any
	exporter   Exporter
	redactor   Redactor
	piiAllowed map[string]struct{}
}

// SpanContext returns the TraceContext for this span.
func (s *InMemorySpan) SpanContext() TraceContext { return s.ctx }

// SetAttribute sets a key/value attribute. PII allow-listed keys route
// the value through the Redactor.
func (s *InMemorySpan) SetAttribute(key string, value any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.ended {
		return
	}
	if s.attrs == nil {
		s.attrs = make(map[string]any, 4)
	}
	if s.redactor != nil {
		if _, isPII := s.piiAllowed[key]; isPII {
			masked, applied := s.redactor.Redact(value)
			if applied {
				s.attrs[key] = masked
				return
			}
		}
	}
	s.attrs[key] = value
}

// RecordError attaches err to the span and sets Status=Error.
func (s *InMemorySpan) RecordError(err error) {
	if err == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.ended {
		return
	}
	s.errs = append(s.errs, err)
	s.status = StatusError
}

// SetStatus updates the span status (rejected after End).
func (s *InMemorySpan) SetStatus(st Status) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.ended {
		return
	}
	s.status = st
}

// End closes the span and exports it. Multiple End calls are no-ops.
func (s *InMemorySpan) End() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.ended {
		return
	}
	s.endedAt = time.Now().UTC()
	s.ended = true
	if s.exporter != nil {
		// Snapshot the span state for the exporter — defensive copy.
		snap := SpanSnapshot{
			TraceID:    s.ctx.TraceID,
			SpanID:     s.ctx.SpanID,
			Name:       s.name,
			Kind:       s.kind,
			Status:     s.status,
			StartedAt:  s.startedAt,
			EndedAt:    s.endedAt,
			Attributes: copyAttrs(s.attrs),
			Errors:     append([]error(nil), s.errs...),
		}
		s.exporter.Export(snap)
	}
}

// Ended returns true after End has been called. Test helper.
func (s *InMemorySpan) Ended() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.ended
}

// Attributes returns a snapshot of the current attribute map. Test helper.
func (s *InMemorySpan) Attributes() map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	return copyAttrs(s.attrs)
}

func copyAttrs(in map[string]any) map[string]any {
	if in == nil {
		return nil
	}
	out := make(map[string]any, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

// spanContextKey is the typed context.Context key for the active span.
type spanContextKey struct{}

// SpanFromContext returns the Span attached to ctx, or nil if none.
func SpanFromContext(ctx context.Context) Span {
	if ctx == nil {
		return nil
	}
	v := ctx.Value(spanContextKey{})
	if v == nil {
		return nil
	}
	s, _ := v.(Span)
	return s
}

// ContextWithSpan returns a derived context that carries s as the active
// span. Downstream calls retrieve it via SpanFromContext.
func ContextWithSpan(ctx context.Context, s Span) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, spanContextKey{}, s)
}

// ValidateSpanName returns nil iff name matches the cycle-19 convention.
// Exposed so cycle-32 tracing-completeness-lint can call it from CI.
func ValidateSpanName(name string) error {
	if !spanNameRegex.MatchString(name) {
		return ErrInvalidSpanName
	}
	return nil
}
