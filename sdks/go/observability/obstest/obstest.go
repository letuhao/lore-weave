// Package obstest provides test helpers for OpenTelemetry-instrumented
// LoreWeave services (Phase 6c). It lets a service's tracing_test.go assert
// on real spans without re-inlining the recording-provider setup.
package obstest

import (
	"context"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

// RecordingProvider installs a recording TracerProvider (backed by an
// in-memory SpanRecorder) + the W3C TraceContext propagator as the global
// OTel state, and returns the recorder. The previous globals are restored on
// t.Cleanup.
//
// Tests MUST use this rather than observability.InitTracer: with no
// OTEL_EXPORTER_OTLP_ENDPOINT set InitTracer installs a no-op provider whose
// spans are non-recording and carry an invalid SpanContext — under which
// trace_id / parent-child assertions pass vacuously.
//
// NOT parallel-safe: it sets process-global OTel state (SetTracerProvider /
// SetTextMapPropagator). A test that calls RecordingProvider must NOT call
// t.Parallel() — two such tests running concurrently would stomp each other.
func RecordingProvider(t *testing.T) *tracetest.SpanRecorder {
	t.Helper()
	sr := tracetest.NewSpanRecorder()
	tp := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(sr))
	prevTP, prevProp := otel.GetTracerProvider(), otel.GetTextMapPropagator()
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	t.Cleanup(func() {
		_ = tp.Shutdown(context.Background())
		otel.SetTracerProvider(prevTP)
		otel.SetTextMapPropagator(prevProp)
	})
	return sr
}
