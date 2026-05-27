package llmgw

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// TestNewClient_DefaultTransportInjectsTraceparent locks Phase 6c: the SDK's
// nil-Transport default is the otelhttp-instrumented transport, so a gateway
// call carries the caller's W3C traceparent. Internal test — it reaches the
// unexported c.http to exercise the transport without driving submit→poll.
func TestNewClient_DefaultTransportInjectsTraceparent(t *testing.T) {
	tp := sdktrace.NewTracerProvider()
	prevTP, prevProp := otel.GetTracerProvider(), otel.GetTextMapPropagator()
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	t.Cleanup(func() {
		_ = tp.Shutdown(context.Background())
		otel.SetTracerProvider(prevTP)
		otel.SetTextMapPropagator(prevProp)
	})

	var gotTraceparent string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotTraceparent = r.Header.Get("traceparent")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	c, err := NewClient(Options{
		BaseURL:       srv.URL,
		AuthMode:      AuthInternal,
		InternalToken: "tok",
	})
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}

	ctx, span := otel.Tracer("test").Start(context.Background(), "op")
	defer span.End()
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, srv.URL, nil)
	resp, err := c.http.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	_ = resp.Body.Close()

	if gotTraceparent == "" {
		t.Fatal("the SDK's default transport did not inject a traceparent")
	}
	if want := span.SpanContext().TraceID().String(); !strings.Contains(gotTraceparent, want) {
		t.Fatalf("traceparent %q does not carry the active trace_id %q", gotTraceparent, want)
	}
}
