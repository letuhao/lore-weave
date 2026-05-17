package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"

	"github.com/loreweave/usage-billing-service/internal/config"
)

// TestRouter_EmitsServerSpan regression-locks observability.ChiMiddleware
// being wired into Router(): if someone drops r.Use(ChiMiddleware()) this
// fails. ChiMiddleware's own behaviour is unit-tested in the observability
// module — this only proves usage-billing actually mounts it.
func TestRouter_EmitsServerSpan(t *testing.T) {
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

	srv := NewServer(nil, &config.Config{JWTSecret: "test-secret"})
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/health")
	if err != nil {
		t.Fatalf("GET /health: %v", err)
	}
	_ = resp.Body.Close()

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 SERVER span from ChiMiddleware, got %d", len(spans))
	}
	if got := spans[0].Name(); got != "GET /health" {
		t.Fatalf("span name = %q, want \"GET /health\" (route pattern)", got)
	}
}
