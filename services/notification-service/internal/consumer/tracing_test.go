package consumer

import (
	"context"
	"io"
	"log/slog"
	"testing"

	rabbitmq "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/observability"
	"github.com/loreweave/observability/obstest"
)

// noopAck satisfies rabbitmq.Acknowledger so a hand-built Delivery can be
// Ack/Nack'd in a test without a live broker.
type noopAck struct{}

func (noopAck) Ack(uint64, bool) error        { return nil }
func (noopAck) Nack(uint64, bool, bool) error { return nil }
func (noopAck) Reject(uint64, bool) error     { return nil }

// TestHandle_ConsumerSpanContinuesTraceAndRecordsError covers §9 #4: a
// delivery whose Headers carry a traceparent produces a CONSUMER span on that
// trace_id, and a malformed body marks the span codes.Error. The malformed
// path returns before the DB Exec, so no pool is needed.
func TestHandle_ConsumerSpanContinuesTraceAndRecordsError(t *testing.T) {
	sr := obstest.RecordingProvider(t)
	c := &Consumer{logger: slog.New(slog.NewTextHandler(io.Discard, nil))}

	// Craft an inbound traceparent (as provider-registry's notifier injects).
	parent := trace.NewSpanContext(trace.SpanContextConfig{
		TraceID:    trace.TraceID{0x9, 0x9},
		SpanID:     trace.SpanID{0x7, 0x7},
		TraceFlags: trace.FlagsSampled,
		Remote:     true,
	})
	headers := rabbitmq.Table{}
	observability.Inject(
		trace.ContextWithSpanContext(context.Background(), parent),
		observability.AMQPCarrier(headers))

	c.handle(context.Background(), rabbitmq.Delivery{
		Acknowledger: noopAck{},
		Headers:      headers,
		Body:         []byte("{not valid json"),
	})

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 CONSUMER span, got %d", len(spans))
	}
	s := spans[0]
	if s.SpanContext().TraceID() != parent.TraceID() {
		t.Fatal("consumer span did not continue the producer's trace")
	}
	if s.SpanKind() != trace.SpanKindConsumer {
		t.Fatalf("span kind = %v, want Consumer", s.SpanKind())
	}
	if s.Status().Code != codes.Error {
		t.Fatalf("a malformed event must mark the span Error, got %v", s.Status().Code)
	}
}
