package consumer

// Phase 2d (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). RabbitMQ consumer for
// async LLM job terminal events. Binds a durable queue to
// `loreweave.events` (topic) with key `user.*.llm.#` so any user, any
// operation, any status flows in. Each event is translated into a
// notifications row so the FE's existing notification stream surfaces
// "chat completed", "extraction failed", etc. without per-feature
// wiring.
//
// Provider-registry is the publisher (services/provider-registry-service/
// internal/jobs/notifier.go). Stay binary-compatible with its
// TerminalEvent struct.

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	rabbitmq "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/loreweave/foundation/contracts/notifyevent"
	"github.com/loreweave/observability"

	"github.com/loreweave/notification-service/internal/category"
)

const (
	exchangeName = notifyevent.EventsExchange
	queueName    = "notification-service.llm-jobs"
	bindingKey   = "user.*.llm.#"
)

// terminalEvent is the SHARED wire contract (contracts/notifyevent), aliased so
// this consumer's existing references keep working. The producer
// (provider-registry jobs.Notifier) imports the same type, so the struct can no
// longer drift between the two services (it used to be a hand-maintained copy).
type terminalEvent = notifyevent.TerminalEvent

// notificationArgs is the row-shape transformer output. Decoupled from
// the SQL itself so unit tests can verify shape without a DB.
type notificationArgs struct {
	UserID   uuid.UUID
	Category string
	Title    string
	Body     string
	Metadata []byte // JSON-encoded
}

// transformTerminalEvent converts a parsed event into the args we'll
// INSERT. Pure function — testable without a broker.
func transformTerminalEvent(ev terminalEvent) notificationArgs {
	title := titleFor(ev.Operation, ev.Status)
	body := bodyFor(ev)
	meta, _ := json.Marshal(map[string]any{
		"job_id":        ev.JobID.String(),
		"operation":     ev.Operation,
		"status":        ev.Status,
		"trace_id":      ev.TraceID,
		"finish_reason": ev.FinishReason,
		"error_code":    ev.ErrorCode,
	})
	return notificationArgs{
		UserID:   ev.OwnerUserID,
		Category: "llm_job",
		Title:    title,
		Body:     body,
		Metadata: meta,
	}
}

// titleFor produces a short human-readable label per (operation, status).
// Operation strings come straight from the openapi enum.
func titleFor(operation, status string) string {
	op := opLabel(operation)
	switch status {
	case "completed":
		return op + " completed"
	case "failed":
		return op + " failed"
	case "cancelled":
		return op + " cancelled"
	default:
		return op + " " + status
	}
}

// opLabel turns the JobOperation enum (`entity_extraction`, `image_gen`,
// `video_gen`, etc.) into a human-readable label. Underscores become
// spaces; first letter capitalised. Generic — new operation names just
// need the consumer_test.go fixture to add an explicit assertion.
func opLabel(operation string) string {
	if operation == "" {
		return "Job"
	}
	s := strings.ReplaceAll(operation, "_", " ")
	return strings.ToUpper(s[:1]) + s[1:]
}

// bodyFor produces a one-sentence body summary. Empty string for
// successes (the title is enough); errors include code/message snippet.
func bodyFor(ev terminalEvent) string {
	if ev.Status == "failed" && ev.ErrorMessage != "" {
		// Cap message length so a verbose upstream doesn't blow up
		// the notifications table or the FE's truncated render.
		msg := ev.ErrorMessage
		if len(msg) > 240 {
			msg = msg[:240] + "..."
		}
		if ev.ErrorCode != "" {
			return fmt.Sprintf("[%s] %s", ev.ErrorCode, msg)
		}
		return msg
	}
	return ""
}

// Consumer owns the connection + channel + queue lifecycle for the LLM
// jobs subscription. Construct via Start.
type Consumer struct {
	conn   *rabbitmq.Connection
	ch     *rabbitmq.Channel
	pool   *pgxpool.Pool
	logger *slog.Logger
}

// Start dials the broker, declares the topic exchange + queue + binding,
// and spawns a goroutine that consumes deliveries until ctx is cancelled
// (or the connection drops). Caller owns the returned Consumer's Close
// lifecycle.
func Start(ctx context.Context, amqpURL string, pool *pgxpool.Pool, logger *slog.Logger) (*Consumer, error) {
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
	if err := ch.ExchangeDeclare(exchangeName, "topic", true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("declare exchange: %w", err)
	}
	if _, err := ch.QueueDeclare(queueName, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("declare queue: %w", err)
	}
	if err := ch.QueueBind(queueName, bindingKey, exchangeName, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("bind queue: %w", err)
	}
	deliveries, err := ch.Consume(queueName, "notification-service", false, false, false, false, nil)
	if err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return nil, fmt.Errorf("consume: %w", err)
	}

	c := &Consumer{conn: conn, ch: ch, pool: pool, logger: logger}
	go c.run(ctx, deliveries)
	logger.Info("llm-jobs consumer started",
		"exchange", exchangeName, "queue", queueName, "binding", bindingKey)
	return c, nil
}

func (c *Consumer) run(ctx context.Context, deliveries <-chan rabbitmq.Delivery) {
	for {
		select {
		case <-ctx.Done():
			return
		case d, ok := <-deliveries:
			if !ok {
				c.logger.Warn("llm-jobs consumer delivery channel closed")
				return
			}
			c.handle(ctx, d)
		}
	}
}

func (c *Consumer) handle(ctx context.Context, d rabbitmq.Delivery) {
	// Phase 6c — continue the producer's trace across the RabbitMQ hop.
	// Extract reads the traceparent provider-registry's notifier injected;
	// a delivery with no headers just starts a fresh root (no failure).
	ctx = observability.Extract(ctx, observability.AMQPCarrier(d.Headers))
	ctx, span := observability.Tracer("consumer").Start(ctx, "llm-event.consume",
		trace.WithSpanKind(trace.SpanKindConsumer),
		trace.WithAttributes(
			attribute.String("messaging.system", "rabbitmq"),
			attribute.String("messaging.rabbitmq.routing_key", d.RoutingKey),
		))
	defer span.End()

	var ev terminalEvent
	if err := json.Unmarshal(d.Body, &ev); err != nil {
		c.logger.Warn("malformed llm-job event — discarding", "err", err)
		span.RecordError(err)
		span.SetStatus(codes.Error, "malformed event body")
		// Don't requeue malformed messages; would just loop forever.
		_ = d.Nack(false, false)
		return
	}
	if ev.OwnerUserID == uuid.Nil || ev.JobID == uuid.Nil {
		c.logger.Warn("event missing owner or job_id — discarding", "routing_key", d.RoutingKey)
		span.SetStatus(codes.Error, "event missing owner or job_id")
		_ = d.Nack(false, false)
		return
	}
	span.SetAttributes(
		attribute.String("job.id", ev.JobID.String()),
		attribute.String("llm.operation", ev.Operation),
	)
	args := transformTerminalEvent(ev)
	// Route the consumer insert through the SAME validation the HTTP
	// ingress path uses (audit P0-4 / NOTIF-2): the consumer previously
	// inserted its category via raw SQL, bypassing validCategory. A
	// category not in the single source-of-truth set is a poison message —
	// discard without requeue so it can't loop forever.
	if !category.Valid(args.Category) {
		c.logger.Error("invalid notification category — discarding",
			"category", args.Category, "job_id", ev.JobID.String())
		span.SetStatus(codes.Error, "invalid notification category")
		_ = d.Nack(false, false)
		return
	}
	_, err := c.pool.Exec(ctx, `
INSERT INTO notifications (user_id, category, title, body, metadata)
VALUES ($1, $2, $3, $4, $5)
`, args.UserID, args.Category, args.Title, args.Body, args.Metadata)
	if err != nil {
		c.logger.Error("notification insert failed — requeueing",
			"err", err, "job_id", ev.JobID.String())
		span.RecordError(err)
		span.SetStatus(codes.Error, "notification insert failed")
		// Requeue so a transient DB hiccup doesn't lose the event.
		_ = d.Nack(false, true)
		return
	}
	_ = d.Ack(false)
}

func (c *Consumer) Close() error {
	if c.ch != nil {
		_ = c.ch.Close()
	}
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}
