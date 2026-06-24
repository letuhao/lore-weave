package tracing

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"time"
)

// Tracer is the typed surface services use to start spans.
type Tracer interface {
	// StartSpan starts a new span and returns it + a derived context
	// that carries the span. Caller MUST call Span.End() to finalize.
	//
	// If ctx carries a parent span, the new span inherits the parent's
	// TraceID (cross-service trace continuity). If ctx carries a
	// TraceContext via WithRemoteParent, the new span's parent is THAT
	// context (server-side propagation entry point).
	//
	// Returns ErrInvalidSpanName if name fails the cycle-19 convention.
	StartSpan(ctx context.Context, name string, opts SpanOptions) (Span, context.Context, error)
}

// SpanOptions is the per-StartSpan config.
type SpanOptions struct {
	// Kind classifies the span (internal/server/client/producer/consumer).
	Kind SpanKind

	// Hint overrides the sampler decision (force/drop). Used for SEV0/SEV1
	// (Force=true) and noisy health checks (Drop=true).
	Hint SamplingHint

	// Attributes seeded at span start. Per-Tracer PII allow-list applies.
	Attributes map[string]any
}

// TracerConfig is the constructor input for a real Tracer.
type TracerConfig struct {
	// ServiceName is prepended to span names if they don't already have
	// a `<service>.` prefix. Defaults to empty (no prefix).
	ServiceName string

	// Sampler decides whether to export the span. nil → AlwaysOnSampler.
	Sampler Sampler

	// Exporter receives finished spans. nil → NoopExporter.
	Exporter Exporter

	// Redactor masks PII attributes. nil → NoopRedactor.
	Redactor Redactor

	// PIIAttributeKeys is the explicit allow-list of attribute keys that
	// route through Redactor.Redact. Empty = no PII filtering applied.
	// Production binds keys like `auth.user.email`, `user.profile.name`.
	PIIAttributeKeys []string
}

// ErrInvalidConfig is returned by NewTracer for invalid config.
var ErrInvalidConfig = errors.New("tracing: invalid TracerConfig")

// NewTracer constructs the production Tracer.
func NewTracer(cfg TracerConfig) (Tracer, error) {
	if cfg.Sampler == nil {
		cfg.Sampler = AlwaysOnSampler{}
	}
	if cfg.Exporter == nil {
		cfg.Exporter = NoopExporter{}
	}
	if cfg.Redactor == nil {
		cfg.Redactor = NoopRedactor{}
	}
	allowed := make(map[string]struct{}, len(cfg.PIIAttributeKeys))
	for _, k := range cfg.PIIAttributeKeys {
		if k == "" {
			return nil, fmt.Errorf("%w: PIIAttributeKeys must not contain empty string", ErrInvalidConfig)
		}
		allowed[k] = struct{}{}
	}
	return &tracer{
		serviceName: cfg.ServiceName,
		sampler:     cfg.Sampler,
		exporter:    cfg.Exporter,
		redactor:    cfg.Redactor,
		piiAllowed:  allowed,
	}, nil
}

// remoteParentKey is the typed context key for a remote-parent
// TraceContext (extracted from a `traceparent` header in middleware).
type remoteParentKey struct{}

// WithRemoteParent returns a derived context that carries `tc` as the
// remote-parent context for the next StartSpan call. Used by HTTP/gRPC
// middleware that calls Extract → WithRemoteParent → handler.
func WithRemoteParent(ctx context.Context, tc TraceContext) context.Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return context.WithValue(ctx, remoteParentKey{}, tc)
}

// RemoteParentFromContext returns the remote-parent TraceContext attached
// to ctx, or (zero, false) if none.
func RemoteParentFromContext(ctx context.Context) (TraceContext, bool) {
	if ctx == nil {
		return TraceContext{}, false
	}
	v := ctx.Value(remoteParentKey{})
	if v == nil {
		return TraceContext{}, false
	}
	tc, ok := v.(TraceContext)
	return tc, ok
}

// tracer is the canonical Tracer impl.
type tracer struct {
	serviceName string
	sampler     Sampler
	exporter    Exporter
	redactor    Redactor
	piiAllowed  map[string]struct{}
}

// StartSpan starts a span and returns it plus a derived context.
func (t *tracer) StartSpan(ctx context.Context, name string, opts SpanOptions) (Span, context.Context, error) {
	if err := ValidateSpanName(name); err != nil {
		return nil, ctx, err
	}

	// Determine parent context.
	var parent TraceContext
	if remote, ok := RemoteParentFromContext(ctx); ok {
		parent = remote
	} else if existing := SpanFromContext(ctx); existing != nil {
		parent = existing.SpanContext()
	}

	// Sampling decision.
	dec := t.sampler.ShouldSample(parent, name, opts.Hint)

	// Build the new span context.
	tc := parent
	if tc.IsZero() {
		// Brand new trace.
		if _, err := rand.Read(tc.TraceID[:]); err != nil {
			return nil, ctx, fmt.Errorf("tracing: trace_id rand: %w", err)
		}
	}
	// Always generate a fresh span_id for this span.
	if _, err := rand.Read(tc.SpanID[:]); err != nil {
		return nil, ctx, fmt.Errorf("tracing: span_id rand: %w", err)
	}
	// Apply sampling decision to the flags.
	if dec == SamplingRecordAndSample {
		tc.Flags |= 0x01
	} else {
		tc.Flags &^= 0x01
	}

	// If sampling drops, we still return a Span (the API contract
	// requires non-nil) but bind it to a NoopExporter so End is a no-op.
	exporter := t.exporter
	if dec == SamplingDrop {
		exporter = NoopExporter{}
	}

	s := &InMemorySpan{
		ctx:        tc,
		name:       name,
		kind:       opts.Kind,
		startedAt:  time.Now().UTC(),
		exporter:   exporter,
		redactor:   t.redactor,
		piiAllowed: t.piiAllowed,
	}
	for k, v := range opts.Attributes {
		s.SetAttribute(k, v)
	}

	return s, ContextWithSpan(ctx, s), nil
}

// NoopTracer is a Tracer that performs no work — useful as the zero
// value for services that haven't wired a real tracer yet.
type NoopTracer struct{}

// StartSpan returns a span that exports nowhere.
func (NoopTracer) StartSpan(ctx context.Context, name string, _ SpanOptions) (Span, context.Context, error) {
	if err := ValidateSpanName(name); err != nil {
		return nil, ctx, err
	}
	tc, err := NewTraceContext()
	if err != nil {
		return nil, ctx, err
	}
	s := &InMemorySpan{
		ctx:       tc,
		name:      name,
		startedAt: time.Now().UTC(),
		exporter:  NoopExporter{},
	}
	return s, ContextWithSpan(ctx, s), nil
}
