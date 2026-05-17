package billing

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

// TestGuardrailClient_DefaultTransportInjectsTraceparent regression-locks
// NewGuardrailClient's default client using observability.HTTPTransport:
// every reserve/reconcile/release/record call must carry a W3C traceparent
// so usage-billing's SERVER span joins the same trace.
func TestGuardrailClient_DefaultTransportInjectsTraceparent(t *testing.T) {
	tp := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(tracetest.NewSpanRecorder()))
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

	// nil hc → the default client, which must carry the traced transport.
	c := NewGuardrailClient(srv.URL, "tok", nil)
	ctx, span := otel.Tracer("test").Start(context.Background(), "op")
	defer span.End()
	if err := c.Release(ctx, uuid.New()); err != nil {
		t.Fatalf("Release: %v", err)
	}
	if gotTraceparent == "" {
		t.Fatal("the default GuardrailClient transport did not inject a traceparent")
	}
}
