package observability

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

// recordingProvider installs a real (recording) TracerProvider + the W3C
// propagator as the globals, and returns a SpanRecorder. Span-producing
// tests MUST use this rather than InitTracer: with no OTLP endpoint set
// InitTracer yields a non-recording no-op provider, under which trace_id /
// parent-child assertions pass vacuously (Phase 6c /review-impl MED#3).
func recordingProvider(t *testing.T) *tracetest.SpanRecorder {
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

// §7 #1 — no endpoint → no-op provider, but the W3C propagator is still set.
func TestInitTracer_NoEndpoint_PropagatorStillInstalled(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	shutdown, err := InitTracer(context.Background(), "test-svc")
	if err != nil {
		t.Fatalf("InitTracer: %v", err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("no-op shutdown must return nil: %v", err)
	}
	// The propagator must work even though no exporter is configured.
	sc := trace.NewSpanContext(trace.SpanContextConfig{
		TraceID:    trace.TraceID{0x11},
		SpanID:     trace.SpanID{0x22},
		TraceFlags: trace.FlagsSampled,
	})
	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(
		trace.ContextWithSpanContext(context.Background(), sc), carrier)
	if carrier["traceparent"] == "" {
		t.Fatal("no-op mode must still install the W3C propagator")
	}
}

// §7 #2 — endpoint set → real provider; shutdown is idempotent.
func TestInitTracer_WithEndpoint_ShutdownIdempotent(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
	shutdown, err := InitTracer(context.Background(), "test-svc")
	if err != nil {
		t.Fatalf("InitTracer: %v", err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown #1: %v", err)
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown #2 must be nil (idempotent): %v", err)
	}
}

// §7 #3 — Inject→Extract round-trips a traceparent (recording provider, so
// the SpanContext is real — IsValid() makes an empty==empty pass impossible).
func TestInjectExtract_RoundTrip(t *testing.T) {
	recordingProvider(t)
	ctx, span := Tracer("test").Start(context.Background(), "producer")
	defer span.End()

	carrier := propagation.MapCarrier{}
	Inject(ctx, carrier)
	got := trace.SpanContextFromContext(Extract(context.Background(), carrier))

	if !got.IsValid() {
		t.Fatal("extracted span context is not valid")
	}
	if got.TraceID() != span.SpanContext().TraceID() {
		t.Fatalf("trace_id not preserved: got %s want %s",
			got.TraceID(), span.SpanContext().TraceID())
	}
}

// TestAMQPCarrier_RoundTrip — a traceparent written into a map[string]any by
// Inject must Extract back to the same trace_id (the RabbitMQ broker hop).
func TestAMQPCarrier_RoundTrip(t *testing.T) {
	recordingProvider(t)
	ctx, span := Tracer("test").Start(context.Background(), "producer")
	defer span.End()

	headers := map[string]any{}
	Inject(ctx, AMQPCarrier(headers))
	if _, ok := headers["traceparent"]; !ok {
		t.Fatal("Inject did not write traceparent into the map")
	}
	got := trace.SpanContextFromContext(Extract(context.Background(), AMQPCarrier(headers)))
	if !got.IsValid() {
		t.Fatal("extracted span context is not valid")
	}
	if got.TraceID() != span.SpanContext().TraceID() {
		t.Fatalf("trace_id lost through AMQPCarrier: got %s want %s",
			got.TraceID(), span.SpanContext().TraceID())
	}
}

// TestAMQPCarrier_GetKeys — Get is string-typed (an amqp.Table value is `any`);
// Keys lists every header.
func TestAMQPCarrier_GetKeys(t *testing.T) {
	c := AMQPCarrier{"traceparent": "abc", "retry_count": 7}
	if c.Get("traceparent") != "abc" {
		t.Fatalf("Get(traceparent) = %q", c.Get("traceparent"))
	}
	if c.Get("retry_count") != "" {
		t.Fatal("Get must return \"\" for a non-string header value")
	}
	if c.Get("missing") != "" {
		t.Fatal("Get must return \"\" for an absent key")
	}
	if len(c.Keys()) != 2 {
		t.Fatalf("Keys() = %v, want 2", c.Keys())
	}
}

// §7 #5 — DetachedContext carries the trace but NOT the source's cancellation.
func TestDetachedContext_CarriesTraceNotCancellation(t *testing.T) {
	recordingProvider(t)
	src, cancel := context.WithCancel(context.Background())
	reqCtx, span := Tracer("test").Start(src, "request")
	defer span.End()

	worker := DetachedContext(reqCtx)
	cancel() // the originating request ends

	// The real regression-lock: a detached worker context must survive the
	// request being cancelled. This fails the moment someone hands the
	// worker r.Context() instead of a DetachedContext.
	if err := worker.Err(); err != nil {
		t.Fatalf("detached context must survive source cancellation, got %v", err)
	}
	_, child := Tracer("test").Start(worker, "job")
	defer child.End()
	if child.SpanContext().TraceID() != span.SpanContext().TraceID() {
		t.Fatal("detached worker span lost the parent trace_id")
	}
}

// §7 #6 — ChiMiddleware: one SERVER span named by the chi route pattern.
func TestChiMiddleware_ServerSpanNamedByRoutePattern(t *testing.T) {
	sr := recordingProvider(t)
	r := chi.NewRouter()
	r.Use(ChiMiddleware())
	r.Get("/v1/things/{id}", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	srv := httptest.NewServer(r)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/v1/things/abc")
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	_ = resp.Body.Close()

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 server span, got %d", len(spans))
	}
	if got := spans[0].Name(); got != "GET /v1/things/{id}" {
		t.Fatalf("span name = %q, want the route pattern (not the raw path)", got)
	}
}

// TestChiMiddleware_SubRouterRoutePattern locks span naming for a route
// mounted under chi's r.Route(...) — the span name must be the FULL joined
// pattern, not just the leaf, and not the raw path.
func TestChiMiddleware_SubRouterRoutePattern(t *testing.T) {
	sr := recordingProvider(t)
	r := chi.NewRouter()
	r.Use(ChiMiddleware())
	r.Route("/internal", func(r chi.Router) {
		r.Get("/imports/{id}", func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		})
	})
	srv := httptest.NewServer(r)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/internal/imports/abc")
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	_ = resp.Body.Close()

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 server span, got %d", len(spans))
	}
	if got := spans[0].Name(); got != "GET /internal/imports/{id}" {
		t.Fatalf("sub-router span name = %q, want the full mounted route pattern", got)
	}
}

// §7 #6 — ChiMiddleware continues an inbound trace (no new root).
func TestChiMiddleware_ContinuesInboundTrace(t *testing.T) {
	sr := recordingProvider(t)
	r := chi.NewRouter()
	r.Use(ChiMiddleware())
	r.Get("/x", func(w http.ResponseWriter, _ *http.Request) {})
	srv := httptest.NewServer(r)
	defer srv.Close()

	parent := trace.NewSpanContext(trace.SpanContextConfig{
		TraceID:    trace.TraceID{0xAB},
		SpanID:     trace.SpanID{0xCD},
		TraceFlags: trace.FlagsSampled,
		Remote:     true,
	})
	req, _ := http.NewRequest(http.MethodGet, srv.URL+"/x", nil)
	Inject(trace.ContextWithSpanContext(context.Background(), parent),
		propagation.HeaderCarrier(req.Header))

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	_ = resp.Body.Close()

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 span, got %d", len(spans))
	}
	if spans[0].SpanContext().TraceID() != parent.TraceID() {
		t.Fatal("server span started a new root instead of continuing the inbound trace")
	}
}

// TestChiMiddleware_PreservesFlusher locks the property the entire SSE
// streaming UX depends on: ChiMiddleware wraps the ResponseWriter (chi's
// WrapResponseWriter), and an SSE handler type-asserts w.(http.Flusher) to
// flush each event. If the wrap ever stopped preserving Flusher, every
// POST /v1/llm/stream would silently buffer — this test goes red first.
func TestChiMiddleware_PreservesFlusher(t *testing.T) {
	var sawFlusher bool
	r := chi.NewRouter()
	r.Use(ChiMiddleware())
	r.Get("/stream", func(w http.ResponseWriter, _ *http.Request) {
		_, sawFlusher = w.(http.Flusher)
	})
	srv := httptest.NewServer(r)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/stream")
	if err != nil {
		t.Fatalf("GET /stream: %v", err)
	}
	_ = resp.Body.Close()

	if !sawFlusher {
		t.Fatal("ChiMiddleware's wrapped writer must preserve http.Flusher (SSE streaming)")
	}
}

// §7 #7 — HTTPTransport injects a traceparent carrying the active trace_id.
func TestHTTPTransport_InjectsActiveTraceparent(t *testing.T) {
	recordingProvider(t)
	var gotTraceparent string
	srv := httptest.NewServer(http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		gotTraceparent = r.Header.Get("traceparent")
	}))
	defer srv.Close()

	ctx, span := Tracer("test").Start(context.Background(), "client-op")
	defer span.End()

	client := &http.Client{Transport: HTTPTransport(nil)}
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, srv.URL, nil)
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	_ = resp.Body.Close()

	if gotTraceparent == "" {
		t.Fatal("HTTPTransport did not inject a traceparent header")
	}
	if want := span.SpanContext().TraceID().String(); !strings.Contains(gotTraceparent, want) {
		t.Fatalf("traceparent %q does not carry the active trace_id %q", gotTraceparent, want)
	}
}
