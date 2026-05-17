// Package observability is the LoreWeave shared OpenTelemetry tracing helper
// (Phase 6c). One InitTracer call per service main(); ChiMiddleware on the
// chi router; HTTPTransport on outbound HTTP clients; Inject/Extract for
// non-HTTP carriers (RabbitMQ message headers).
//
// See docs/03_planning/LLM_PIPELINE_PHASE6C_DESIGN.md.
package observability

import (
	"context"
	"fmt"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

// InitTracer configures the global OpenTelemetry TracerProvider + W3C
// propagator and returns a shutdown func. The service name is the single
// source of truth for the `service.name` resource attribute — it is NOT
// read from OTEL_SERVICE_NAME.
//
// The W3C TraceContext + Baggage propagator is installed UNCONDITIONALLY —
// even when no exporter is configured. No-op mode degrades only the
// exporter; context propagation must never depend on whether OTLP is wired,
// or a partially-instrumented monorepo would drop trace continuity at every
// uninstrumented hop.
//
// With no OTEL_EXPORTER_OTLP_ENDPOINT set, the global TracerProvider is left
// as the SDK default (a no-op provider) so dev without the observability
// stack still boots. The returned shutdown is then a no-op. Otherwise an
// OTLP/HTTP exporter + batching provider is installed; the returned shutdown
// flushes and stops it, and is safe to call more than once.
func InitTracer(ctx context.Context, serviceName string) (func(context.Context) error, error) {
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	if os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == "" {
		return func(context.Context) error { return nil }, nil
	}

	exp, err := otlptracehttp.New(ctx) // reads OTEL_EXPORTER_OTLP_ENDPOINT
	if err != nil {
		return nil, fmt.Errorf("observability: otlp/http exporter: %w", err)
	}
	res := resource.NewSchemaless(attribute.String("service.name", serviceName))
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)

	// tp.Shutdown is idempotent: a second call after shutdown returns nil.
	return tp.Shutdown, nil
}

// Tracer returns the named tracer from the global provider, for hand-rolled
// spans (e.g. the detached worker's llm.job.process span).
func Tracer(name string) trace.Tracer {
	return otel.Tracer(name)
}

// HTTPTransport wraps base (nil → http.DefaultTransport) so outbound requests
// carry a W3C traceparent and emit a CLIENT span.
func HTTPTransport(base http.RoundTripper) http.RoundTripper {
	if base == nil {
		base = http.DefaultTransport
	}
	return otelhttp.NewTransport(base)
}

// ChiMiddleware is the inbound-HTTP server middleware. It extracts an inbound
// W3C traceparent, starts a SERVER span, and — AFTER the handler runs —
// names the span by the chi route pattern (`GET /v1/things/{id}`) and records
// the response status. The route pattern is unknown at span start (chi
// matches the route in its innermost handler, after every middleware), so the
// naming MUST happen post-routing.
//
// The response writer is wrapped with chi's own WrapResponseWriter, which
// preserves http.Flusher / http.Hijacker — so SSE streaming endpoints
// (POST /v1/llm/stream) keep working.
func ChiMiddleware() func(http.Handler) http.Handler {
	tracer := otel.Tracer("observability/http")
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := otel.GetTextMapPropagator().Extract(
				r.Context(), propagation.HeaderCarrier(r.Header))
			ctx, span := tracer.Start(ctx, r.Method+" "+r.URL.Path,
				trace.WithSpanKind(trace.SpanKindServer),
				trace.WithAttributes(
					attribute.String("http.request.method", r.Method),
					attribute.String("url.path", r.URL.Path),
				))
			defer span.End()

			ww := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
			next.ServeHTTP(ww, r.WithContext(ctx))

			if rc := chi.RouteContext(r.Context()); rc != nil {
				if pattern := rc.RoutePattern(); pattern != "" {
					span.SetName(r.Method + " " + pattern)
					span.SetAttributes(attribute.String("http.route", pattern))
				}
			}
			status := ww.Status()
			if status == 0 {
				status = http.StatusOK
			}
			span.SetAttributes(attribute.Int("http.response.status_code", status))
			if status >= 500 {
				span.SetStatus(codes.Error, http.StatusText(status))
			}
		})
	}
}

// DetachedContext returns a fresh context.Background()-rooted context that
// carries ONLY src's span context (trace_id, span_id, sampled flag) — not
// src's cancellation or deadline. Use it to hand trace continuity to a
// goroutine that must outlive the originating request: the async job worker
// and the streaming spend-settle both detach this way, and without the
// bridge their spans would form a disconnected second trace.
func DetachedContext(src context.Context) context.Context {
	return trace.ContextWithSpanContext(
		context.Background(), trace.SpanContextFromContext(src))
}

// Inject writes the span context of ctx into any TextMapCarrier — the
// amqp-free seam used by the RabbitMQ producer. Extract is its dual.
func Inject(ctx context.Context, carrier propagation.TextMapCarrier) {
	otel.GetTextMapPropagator().Inject(ctx, carrier)
}

// Extract reads a span context out of carrier and returns a context carrying
// it (as a remote parent). Used by RabbitMQ consumers.
func Extract(ctx context.Context, carrier propagation.TextMapCarrier) context.Context {
	return otel.GetTextMapPropagator().Extract(ctx, carrier)
}

// AMQPCarrier adapts a map[string]any to a propagation.TextMapCarrier so
// Inject/Extract can move a W3C traceparent through message headers. An
// amqp091 amqp.Table IS a map[string]interface{}, so callers convert at the
// call site: observability.AMQPCarrier(amqp.Table{...}). This keeps the
// observability module free of an amqp091 dependency.
//
// Set writes into the map — the caller MUST pass a non-nil map (Inject on a
// nil map panics). Get/Keys only read, so Extract from a nil-header delivery
// is safe.
type AMQPCarrier map[string]any

// Get returns the string-typed header value, or "" (absent or non-string).
func (c AMQPCarrier) Get(key string) string {
	if v, ok := c[key].(string); ok {
		return v
	}
	return ""
}

// Set writes a header value.
func (c AMQPCarrier) Set(key, value string) { c[key] = value }

// Keys lists the header keys.
func (c AMQPCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for k := range c {
		keys = append(keys, k)
	}
	return keys
}
