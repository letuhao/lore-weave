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
)

const (
	exchangeName = "loreweave.events"
	queueName    = "notification-service.llm-jobs"
	bindingKey   = "user.*.llm.#"
)

// terminalEvent mirrors provider-registry's jobs.TerminalEvent. We
// duplicate the struct here to avoid importing across services.
type terminalEvent struct {
	JobID        uuid.UUID       `json:"job_id"`
	OwnerUserID  uuid.UUID       `json:"owner_user_id"`
	Operation    string          `json:"operation"`
	Status       string          `json:"status"`
	TraceID      string          `json:"trace_id,omitempty"`
	Result       json.RawMessage `json:"result,omitempty"`
	ErrorCode    string          `json:"error_code,omitempty"`
	ErrorMessage string          `json:"error_message,omitempty"`
	FinishReason string          `json:"finish_reason,omitempty"`
}

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
// etc.) into a human-readable label. Underscores become spaces; first
// letter capitalised.
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
	var ev terminalEvent
	if err := json.Unmarshal(d.Body, &ev); err != nil {
		c.logger.Warn("malformed llm-job event — discarding", "err", err)
		// Don't requeue malformed messages; would just loop forever.
		_ = d.Nack(false, false)
		return
	}
	if ev.OwnerUserID == uuid.Nil || ev.JobID == uuid.Nil {
		c.logger.Warn("event missing owner or job_id — discarding", "routing_key", d.RoutingKey)
		_ = d.Nack(false, false)
		return
	}
	args := transformTerminalEvent(ev)
	_, err := c.pool.Exec(ctx, `
INSERT INTO notifications (user_id, category, title, body, metadata)
VALUES ($1, $2, $3, $4, $5)
`, args.UserID, args.Category, args.Title, args.Body, args.Metadata)
	if err != nil {
		c.logger.Error("notification insert failed — requeueing",
			"err", err, "job_id", ev.JobID.String())
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
