package tasks

import (
	"context"
	"strings"
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/observability/obstest"
)

// capturePublisher records the last Publish call so the test can inspect the
// amqp.Publishing headers without a live broker. Satisfies amqpPublisher.
type capturePublisher struct{ last amqp.Publishing }

func (c *capturePublisher) Publish(_, _ string, _, _ bool, msg amqp.Publishing) error {
	c.last = msg
	return nil
}

// TestPublishWSEvent_InjectsTraceparent — §9 #5. publishWSEvent wraps the
// publish in a PRODUCER span and injects a W3C traceparent carrying the active
// trace into the AMQP headers, so a downstream consumer continues the trace.
func TestPublishWSEvent_InjectsTraceparent(t *testing.T) {
	sr := obstest.RecordingProvider(t)
	pub := &capturePublisher{}
	ip := &ImportProcessor{amqpCh: pub}

	ctx, span := otel.Tracer("test").Start(context.Background(), "import")
	defer span.End()
	ip.publishWSEvent(ctx, "user-1", "job-1", "completed", 3, nil)

	tp, ok := pub.last.Headers["traceparent"].(string)
	if !ok || tp == "" {
		t.Fatalf("publishWSEvent did not inject a traceparent header: %#v", pub.last.Headers)
	}
	if want := span.SpanContext().TraceID().String(); !strings.Contains(tp, want) {
		t.Fatalf("traceparent %q does not carry the active trace_id %q", tp, want)
	}

	spans := sr.Ended()
	if len(spans) != 1 {
		t.Fatalf("want 1 PRODUCER span, got %d", len(spans))
	}
	if spans[0].Name() != "import.ws-event" {
		t.Fatalf("span name = %q, want \"import.ws-event\"", spans[0].Name())
	}
	if spans[0].SpanKind() != trace.SpanKindProducer {
		t.Fatalf("span kind = %v, want Producer", spans[0].SpanKind())
	}
}
