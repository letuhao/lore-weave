package jobs

// notifier.go — Phase 2c (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Emits a
// terminal-state event to RabbitMQ topic `loreweave.events` whenever a
// job finishes (completed / failed / cancelled). Consumers route by
// the topic key:
//
//   user.{user_id}.llm.{operation}.{status}
//
// Notification-service (Phase 2d) consumes these and persists them to
// the user_notifications outbox; api-gateway-bff (Phase 2e) bridges
// from notifications → SSE so FE sees job-done events live.
//
// Webhook callbacks (callback.kind="webhook" with HMAC sig) are
// deferred to a Phase 2c-followup cycle.

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"

	rabbitmq "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/foundation/contracts/notifyevent"
	"github.com/loreweave/observability"
)

const (
	// Shared platform topic exchange. Mirrors translation-service's
	// broker.publish_event() pattern (services/translation-service/app/broker.py).
	llmEventsExchange = notifyevent.EventsExchange
)

// TerminalEvent is the shared wire contract (contracts/notifyevent), aliased here
// so the jobs package's existing `jobs.TerminalEvent` references keep working while
// the STRUCT + its RoutingKey method live in the one place the consumer imports too
// — no more hand-maintained duplicate that can drift.
type TerminalEvent = notifyevent.TerminalEvent

// Notifier publishes TerminalEvents. Implementations:
//   - rabbitMQNotifier:  amqp091 publish to loreweave.events topic
//   - NoopNotifier:      no-op; used when RABBITMQ_URL is unset (dev/tests)
type Notifier interface {
	PublishTerminal(ctx context.Context, ev TerminalEvent) error
	Close() error
}

// NoopNotifier discards events. Constructed when RABBITMQ_URL is empty
// so dev/test runs without a broker keep working.
type NoopNotifier struct{}

func (NoopNotifier) PublishTerminal(_ context.Context, _ TerminalEvent) error { return nil }
func (NoopNotifier) Close() error                                             { return nil }

// rabbitMQNotifier holds a connection + channel. Both are reused across
// PublishTerminal calls; we re-declare the topic exchange on construction
// so the broker has it cached after the first cold-start round-trip.
type rabbitMQNotifier struct {
	conn   *rabbitmq.Connection
	ch     *rabbitmq.Channel
	logger *slog.Logger
	mu     sync.Mutex // serialize publishes; amqp091 channels are NOT goroutine-safe
}

// NewRabbitMQNotifier opens a connection + channel, declares the topic
// exchange (idempotent — durable + same name as translation-service),
// and returns a notifier ready for publishing.
func NewRabbitMQNotifier(amqpURL string, logger *slog.Logger) (Notifier, error) {
	if logger == nil {
		logger = slog.Default()
	}
	conn, err := rabbitmq.Dial(amqpURL)
	if err != nil {
		return nil, fmt.Errorf("amqp dial: %w", err)
	}
	ch, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("amqp channel: %w", err)
	}
	if err := ch.ExchangeDeclare(
		llmEventsExchange,
		"topic",
		true,  // durable — survives broker restart
		false, // auto-delete
		false, // internal
		false, // no-wait
		nil,
	); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("amqp declare exchange: %w", err)
	}
	return &rabbitMQNotifier{conn: conn, ch: ch, logger: logger}, nil
}

func (n *rabbitMQNotifier) PublishTerminal(ctx context.Context, ev TerminalEvent) error {
	body, err := json.Marshal(ev)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}

	// Phase 6c — PRODUCER span + W3C traceparent in the message headers, so
	// the notification-service consumer (6c-β) continues this trace instead
	// of starting a disconnected one.
	ctx, span := observability.Tracer("notifier").Start(ctx, "llm.job.terminal-event",
		trace.WithSpanKind(trace.SpanKindProducer),
		trace.WithAttributes(
			attribute.String("job.id", ev.JobID.String()),
			attribute.String("messaging.system", "rabbitmq"),
			attribute.String("messaging.destination.name", llmEventsExchange),
			attribute.String("messaging.rabbitmq.routing_key", ev.RoutingKey()),
		))
	defer span.End()
	headers := rabbitmq.Table{}
	observability.Inject(ctx, observability.AMQPCarrier(headers))

	n.mu.Lock()
	defer n.mu.Unlock()
	err = n.ch.PublishWithContext(
		ctx,
		llmEventsExchange,
		ev.RoutingKey(),
		false, // mandatory
		false, // immediate
		rabbitmq.Publishing{
			ContentType:  "application/json",
			DeliveryMode: rabbitmq.Persistent,
			Headers:      headers,
			Body:         body,
		},
	)
	if err != nil {
		span.RecordError(err)
		n.logger.Warn("publish terminal event failed",
			"job_id", ev.JobID.String(), "status", ev.Status, "err", err)
		return fmt.Errorf("amqp publish: %w", err)
	}
	return nil
}

func (n *rabbitMQNotifier) Close() error {
	if n.ch != nil {
		_ = n.ch.Close()
	}
	if n.conn != nil {
		return n.conn.Close()
	}
	return nil
}
