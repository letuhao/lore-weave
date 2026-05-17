package jobs

import (
	"context"
	"testing"

	rabbitmq "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/observability"
)

// TestAMQPHeaderCarrier_RoundTrip — §7 #4. A traceparent written into an
// amqp.Table by observability.Inject must Extract back to the same trace_id,
// so the notification-service consumer (6c-β) continues the producer's trace.
func TestAMQPHeaderCarrier_RoundTrip(t *testing.T) {
	tp := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(tracetest.NewSpanRecorder()))
	prevTP, prevProp := otel.GetTracerProvider(), otel.GetTextMapPropagator()
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	t.Cleanup(func() {
		_ = tp.Shutdown(context.Background())
		otel.SetTracerProvider(prevTP)
		otel.SetTextMapPropagator(prevProp)
	})

	ctx, span := otel.Tracer("test").Start(context.Background(), "producer")
	defer span.End()

	headers := rabbitmq.Table{}
	observability.Inject(ctx, amqpHeaderCarrier(headers))
	if _, ok := headers["traceparent"]; !ok {
		t.Fatal("Inject did not write traceparent into the amqp.Table headers")
	}

	got := trace.SpanContextFromContext(
		observability.Extract(context.Background(), amqpHeaderCarrier(headers)))
	if !got.IsValid() {
		t.Fatal("extracted span context is not valid")
	}
	if got.TraceID() != span.SpanContext().TraceID() {
		t.Fatalf("trace_id lost through the amqp.Table: got %s want %s",
			got.TraceID(), span.SpanContext().TraceID())
	}
}

// TestAMQPHeaderCarrier_Keys covers the carrier's Keys() — exercised by some
// propagators and by Extract; a missing key must not break it.
func TestAMQPHeaderCarrier_Keys(t *testing.T) {
	c := amqpHeaderCarrier(rabbitmq.Table{"traceparent": "x", "other": 7})
	if c.Get("traceparent") != "x" {
		t.Fatalf("Get(traceparent) = %q", c.Get("traceparent"))
	}
	if c.Get("other") != "" {
		t.Fatal("Get must return empty for a non-string header value")
	}
	if len(c.Keys()) != 2 {
		t.Fatalf("Keys() = %v, want 2 entries", c.Keys())
	}
}
